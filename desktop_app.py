"""Local browser launcher; NAS contains data only, never executable files."""

from __future__ import annotations

import ctypes
import json
import webbrowser
import logging
import os
import socket
import sys
import threading
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "KY安全管理"
CONTROL_PORT = int(os.environ.get("KY_CONTROL_PORT", "51837"))  # 同一PC二重起動検知専用のローカルポート (mutex代わり)
STARTUP_TIMEOUT_SEC = 20


def _app_dir() -> Path:
    """exe (またはスクリプト) が置かれているフォルダ。UNC/日本語/空白パス対応。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _local_data_root() -> Path:
    """書き込み用データの保存先 (ローカルPC固定)。

    アプリ本体はネットワーク共有上に置かれるため、複数PCが同時に
    同じJSONファイルへ書き込むと破損する恐れがある。そのため履歴・
    データ・ログはPC毎の LOCALAPPDATA 配下に保存する。
    """
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


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
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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
    try:
        from main import app
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
        return 0
    except Exception as exc:
        logger.error("Startup or runtime failed (%s)", type(exc).__name__)
        _fatal_message_box(APP_NAME, "起動できませんでした。config.json、secrets.envがEXEと同じフォルダにあることと、設定内容を確認してください。")
        return 1
    finally:
        if server:
            server.should_exit = True
        if server_thread:
            server_thread.join(timeout=100)
        guard.close()
        logger.info("Application stopped")


if __name__ == "__main__":
    sys.exit(main())
