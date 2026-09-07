"""デスクトップアプリ版の起動エントリポイント。

`GenbaSafetyRAGApp.exe` (PyInstaller onedir) から実行される想定。
- 内部でFastAPIサーバーをバックグラウンドスレッドで起動
- pywebview (Edge WebView2) の専用ウィンドウでUIを表示
- ウィンドウを閉じるとサーバー・全スレッドを終了してプロセスを終了する
- コマンドプロンプト画面は表示しない (PyInstaller --windowed でビルドする前提)
- 同一PCでの二重起動を防止し、既存ウィンドウを前面に出す
- ネットワーク共有(UNC)上からの実行を考慮し、書き込み先はローカルPCの
  AppData配下に固定する (共有フォルダ上のJSON履歴への複数PC同時書き込みは
  破損リスクがあるため)
"""

from __future__ import annotations

import ctypes
import logging
import os
import socket
import sys
import threading
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "GenbaSafetyRAGApp"
CONTROL_PORT = 51837  # 同一PC二重起動検知専用のローカルポート (mutex代わり)
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
                conn.recv(64)
            except OSError:
                pass
            finally:
                conn.close()
            for cb in list(self._on_show):
                try:
                    cb()
                except Exception:
                    self._logger.exception("failed to bring window to front")

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass


def main() -> int:
    app_dir = _app_dir()
    local_root = _local_data_root()

    logger = _setup_logging(local_root / "logs")
    logger.info("=== %s starting (pid=%s) ===", APP_NAME, os.getpid())
    logger.info("app_dir=%s", app_dir)
    logger.info("local_root=%s", local_root)

    # 二重起動チェック (同一PC内)
    guard = SingleInstanceGuard(CONTROL_PORT, logger)
    if not guard.try_become_primary():
        logger.info("another instance is already running; notifying and exiting")
        guard.notify_existing_instance()
        return 0

    # 書き込み先をローカルPC固定にする (共有フォルダ上でのJSON同時書き込み破損を回避)
    os.environ.setdefault("HISTORY_DIR", str(local_root / "history"))
    os.environ.setdefault("DATA_DIR", str(local_root / "data"))

    # playwright(PDF生成用Chromium) はアプリ配布物に同梱したものを使う
    bundled_browsers = app_dir / "pw-browsers"
    if bundled_browsers.exists():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(bundled_browsers))

    try:
        sys.path.insert(0, str(app_dir))
        from main import app as fastapi_app  # noqa: PLC0415  (env設定後にimportする必要がある)
        import uvicorn  # noqa: PLC0415
    except Exception:
        logger.exception("failed to import backend application")
        _fatal_message_box(APP_NAME, "アプリの初期化に失敗しました。logsフォルダを確認してください。")
        guard.close()
        return 1

    port = _find_free_port()
    logger.info("selected local port: %s", port)

    config = uvicorn.Config(
        fastapi_app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    waited = 0.0
    while not server.started and waited < STARTUP_TIMEOUT_SEC:
        time.sleep(0.1)
        waited += 0.1

    if not server.started:
        logger.error("web server failed to start within %ss", STARTUP_TIMEOUT_SEC)
        _fatal_message_box(APP_NAME, "内部サーバーの起動に失敗しました。logsフォルダを確認してください。")
        server.should_exit = True
        guard.close()
        return 1

    logger.info("web server started at http://127.0.0.1:%s", port)

    try:
        import webview  # noqa: PLC0415
    except Exception:
        logger.exception("failed to import webview")
        _fatal_message_box(APP_NAME, "画面表示の初期化に失敗しました。logsフォルダを確認してください。")
        server.should_exit = True
        guard.close()
        return 1

    window = webview.create_window(
        "現場安全AI (KY)",
        url=f"http://127.0.0.1:{port}/",
        width=1400,
        height=900,
        min_size=(1000, 700),
    )

    icon_path = app_dir / "static" / "icons" / "app_icon.ico"

    def _bring_to_front() -> None:
        try:
            window.restore()
        except Exception:
            pass
        try:
            window.on_top = True
            window.on_top = False
        except Exception:
            pass

    guard.set_show_callback(_bring_to_front)

    try:
        webview.start(
            gui="edgechromium",
            private_mode=False,
            icon=str(icon_path) if icon_path.is_file() else None,
        )
    except Exception:
        logger.exception("webview terminated with an error")
    finally:
        logger.info("window closed; shutting down web server")
        server.should_exit = True
        server_thread.join(timeout=10)
        guard.close()
        logger.info("=== %s stopped ===", APP_NAME)

    return 0


if __name__ == "__main__":
    sys.exit(main())
