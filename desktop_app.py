"""Local browser launcher; NAS contains data only, never executable files."""

from __future__ import annotations

import ctypes
import json
import webbrowser
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from backend.app.core.app_paths import APP_NAME, local_data_root as _local_data_root, restart_flag_path

CONTROL_PORT = int(os.environ.get("KY_CONTROL_PORT", "51837"))  # 同一PC二重起動検知専用のローカルポート (mutex代わり)
APP_PORT = int(os.environ.get("KY_APP_PORT", "51838"))  # 画面(API)用の優先ポート。使用中のときだけ空きポートへ退避する
STARTUP_TIMEOUT_SEC = 20


def _app_dir() -> Path:
    """exe (またはスクリプト) が置かれているフォルダ。UNC/日本語/空白パス対応。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _setup_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)

    # 複数PC/複数プロセスが同じファイルへ同時書き込みしないよう、
    # 実行ごとに一意なファイル名にする。古いログは起動時に間引く。
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{stamp}_{os.getpid()}.log"

    logger = logging.getLogger("desktop_app")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)

    _cleanup_old_logs(log_dir, keep_days=14)

    return logger


def _cleanup_old_logs(log_dir: Path, keep_days: int) -> None:
    threshold = datetime.now() - timedelta(days=keep_days)
    try:
        for f in log_dir.glob("*.log"):
            try:
                if datetime.fromtimestamp(f.stat().st_mtime) < threshold:
                    f.unlink(missing_ok=True)
            except OSError:
                continue
    except OSError:
        pass


def _fatal_message_box(title: str, message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)  # MB_ICONERROR
    except Exception:
        pass


def _find_free_port() -> int:
    """優先ポートが空いていればそれを使う。

    起動ごとにポートが変わると、再起動前から開いたままの古いブラウザタブが
    存在しないポートへ通信して「Failed to fetch」になるため、同じポートを使い回す。
    """
    for candidate in (APP_PORT, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", candidate))
            except OSError:
                continue
            return s.getsockname()[1]
    raise OSError("利用できるローカルポートがありません。")


class SingleInstanceGuard:
    """127.0.0.1 の固定ポートbindを使った簡易多重起動防止。

    先に起動したプロセスがそのポートをbindし続ける。後から起動した
    プロセスはbindに失敗するので、既存プロセスへ接続して「前面に出して」
    と通知してから自分は何もせず終了する。
    """

    def __init__(self, port: int, logger: logging.Logger) -> None:
        self._port = port
        self._logger = logger
        self._sock: socket.socket | None = None
        self._on_show: list = []

    def try_become_primary(self) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            sock.bind(("127.0.0.1", self._port))
        except OSError:
            sock.close()
            return False
        sock.listen(4)
        self._sock = sock
        threading.Thread(target=self._accept_loop, daemon=True).start()
        return True

    def notify_existing_instance(self) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", self._port), timeout=2) as c:
                c.sendall(b"SHOW\n")
            return True
        except OSError:
            return False

    def set_show_callback(self, callback) -> None:
        self._on_show.append(callback)

    def _accept_loop(self) -> None:
        assert self._sock is not None
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            try:
                conn.settimeout(2)
                conn.recv(64)
            except OSError:
                pass
            finally:
                conn.close()
            for cb in list(self._on_show):
                try:
                    cb()
                except Exception:
                    self._logger.error("failed to open browser")

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass


def _import_app_with_retry(logger: logging.Logger):
    """`from main import app` の遅延インポートをリトライ付きで行う。

    onefile化したEXEは起動のたびに同梱データを一時フォルダへ展開する。
    設定変更後の自動再起動のように短時間で連続起動すると、ディスクI/O
    (ウイルス対策ソフトのスキャン等)の混雑で展開完了前にモジュール読込が
    始まり、一時的に "static" 等のフォルダが見つからないことがある。
    数回だけ短い間隔で再試行し、それでも失敗する場合のみエラーとする。
    """
    last_exc: Exception | None = None
    attempts = 8
    for attempt in range(attempts):
        if attempt:
            time.sleep(0.5)
        try:
            from main import app
            return app
        except (RuntimeError, OSError, ImportError) as exc:
            last_exc = exc
            logger.warning("App import failed (attempt %s/%s), retrying: %s", attempt + 1, attempts, exc)
    raise last_exc


def main() -> int:
    app_dir = _app_dir()
    # Reject UNC and mapped network drives: secrets and runtime stay on PC.
    if str(app_dir).startswith("\\\\") or ctypes.windll.kernel32.GetDriveTypeW(str(app_dir.anchor)) == 4:
        _fatal_message_box(APP_NAME, "フォルダを各PCのローカルディスクへコピーしてから起動してください。")
        return 1
    logger = _setup_logging(_local_data_root() / "logs")
    guard = SingleInstanceGuard(CONTROL_PORT, logger)
    if not guard.try_become_primary():
        guard.notify_existing_instance()
        return 0
    server = None
    server_thread = None
    result = 0
    try:
        app = _import_app_with_retry(logger)
        import uvicorn
        @app.post("/api/v1/shutdown")
        def shutdown():
            threading.Timer(0.3, lambda: setattr(server, "should_exit", True)).start()
            return {"stopping": True}
        port = _find_free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=port,
                                log_config=None, access_log=False, log_level="critical",
                                loop="asyncio", http="h11", ws="none")
        server = uvicorn.Server(config)
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()
        deadline = time.monotonic() + 30
        while not server.started and server_thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.1)
        if not server.started:
            raise RuntimeError()
        url = f"http://127.0.0.1:{port}/"
        def show():
            if os.environ.get("KY_NO_BROWSER") != "1":
                webbrowser.open(url)
        guard.set_show_callback(show)
        logger.info("Application started on local port %s", port)
        show()
        # Wait for the user's explicit in-app exit. Closing an ordinary browser
        # tab is not a reliable application-lifecycle signal.
        while server_thread.is_alive():
            server_thread.join(timeout=0.5)
    except Exception as exc:
        logger.error("Startup or runtime failed (%s): %s", type(exc).__name__, exc)
        detail = str(exc).strip()
        message = f"起動できませんでした。\n\n{detail}" if detail else "起動できませんでした。"
        message += "\n\nconfig.json、secrets.envがEXEと同じフォルダにあることを確認してください。"
        _fatal_message_box(APP_NAME, message)
        result = 1
    finally:
        if server:
            server.should_exit = True
        if server_thread:
            server_thread.join(timeout=100)
        guard.close()
        logger.info("Application stopped")

    if result == 0 and restart_flag_path().exists():
        # 初期設定/保存先変更の完了直後の再起動要求。新しい config.json を
        # 反映させるため、設定を使い回さずプロセス自体を作り直す。
        try:
            restart_flag_path().unlink()
        except OSError:
            pass
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            # PyInstaller onefile builds set _MEIPASS2 so a child of the same exe
            # reuses the parent's extraction folder. That folder is torn down when
            # this (exiting) process's bootloader cleans up, racing the new
            # process's startup. Drop it so the relaunched exe extracts its own.
            restart_env = {k: v for k, v in os.environ.items() if not k.upper().startswith("_MEI")}
            subprocess.Popen([sys.executable, *sys.argv[1:]], close_fds=True, creationflags=creationflags, env=restart_env)
            logger.info("Restarting application to apply new settings.")
            # Give the new process's own onefile extraction a head start before
            # this (exiting) process's bootloader starts tearing down its own
            # extraction folder; avoids disk I/O contention between the two.
            time.sleep(1.5)
        except OSError as exc:
            logger.error("Failed to restart application: %s", exc)
            _fatal_message_box(APP_NAME, "設定を反映するための再起動に失敗しました。手動でアプリを再起動してください。")
    return result


if __name__ == "__main__":
    sys.exit(main())
