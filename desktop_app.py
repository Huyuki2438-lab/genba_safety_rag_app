"""Windows desktop launcher; NAS contains data only, never executable files."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from backend.app.core.app_paths import APP_NAME, local_data_root as _local_data_root, restart_flag_path

CONTROL_PORT = int(os.environ.get("KY_CONTROL_PORT", "51837"))  # 同一PC二重起動検知専用のローカルポート (mutex代わり)
APP_PORT = int(os.environ.get("KY_APP_PORT", "51838"))  # 画面(API)用の優先ポート。使用中のときだけ空きポートへ退避する
STARTUP_TIMEOUT_SEC = 20
GRACEFUL_SHUTDOWN_TIMEOUT_SEC = 120
WINDOW_TITLE = "建設現場安全管理AIアシスタント"


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
        self._accept_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def try_become_primary(self) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            sock.bind(("127.0.0.1", self._port))
        except OSError:
            sock.close()
            return False
        sock.listen(4)
        sock.settimeout(0.5)
        self._sock = sock
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True, name="single-instance-listener")
        self._accept_thread.start()
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
        sock = self._sock
        assert sock is not None
        while not self._stop_event.is_set():
            try:
                conn, _ = sock.accept()
            except socket.timeout:
                continue
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
                    self._logger.error("failed to show application window")

    def close(self) -> None:
        self._stop_event.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._accept_thread and self._accept_thread is not threading.current_thread():
            self._accept_thread.join(timeout=2)


def _edge_executable() -> Path:
    """Return the installed Microsoft Edge executable used as the desktop shell."""
    candidates: list[Path] = []
    on_path = shutil.which("msedge")
    if on_path:
        candidates.append(Path(on_path))
    for env_name in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        root = os.environ.get(env_name)
        if root:
            candidates.append(Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Microsoft Edgeが見つかりません。Edgeをインストールしてください。")


def _window_api():
    user32 = ctypes.windll.user32
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = wintypes.LPARAM
    return user32


def _process_api():
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _window_title(window_handle: int) -> str:
    user32 = _window_api()
    length = user32.GetWindowTextLengthW(window_handle)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(window_handle, buffer, length + 1)
    return buffer.value


def _visible_windows_for_executable(executable: Path) -> dict[int, int]:
    """Return visible top-level windows owned by the requested executable."""
    if sys.platform != "win32":
        return {}
    user32 = _window_api()
    kernel32 = _process_api()
    found: dict[int, int] = {}
    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [enum_proc_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    expected = str(executable).casefold()

    @enum_proc_type
    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindowTextLengthW(hwnd) <= 0:
            return True
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        handle = kernel32.OpenProcess(0x1000, False, owner.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return True
        try:
            size = wintypes.DWORD(32768)
            image_path = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, image_path, ctypes.byref(size)):
                if image_path.value.casefold() == expected:
                    found[int(hwnd)] = int(owner.value)
        finally:
            kernel32.CloseHandle(handle)
        return True

    user32.EnumWindows(visit, 0)
    return found


def _wait_for_process_exit(process_id: int, timeout_ms: int, *, terminate_on_timeout: bool) -> None:
    """Wait for a Windows process not represented by our Popen object."""
    kernel32 = _process_api()
    handle = kernel32.OpenProcess(0x00100001, False, process_id)  # SYNCHRONIZE | PROCESS_TERMINATE
    if not handle:
        return
    try:
        if kernel32.WaitForSingleObject(handle, timeout_ms) == 0x00000102 and terminate_on_timeout:
            kernel32.TerminateProcess(handle, 0)
            kernel32.WaitForSingleObject(handle, 5000)
    finally:
        kernel32.CloseHandle(handle)


class DesktopWindow:
    """A dedicated Edge app window whose lifetime owns the local backend."""

    def __init__(self, url: str, logger: logging.Logger) -> None:
        self._url = url
        self._logger = logger
        self._process: subprocess.Popen | None = None
        self._window_handle: int | None = None
        self._window_process_id: int | None = None
        self._profile = tempfile.TemporaryDirectory(prefix="ky-safety-window-", ignore_cleanup_errors=True)

    def open(self) -> None:
        edge = _edge_executable()
        existing_windows = set(_visible_windows_for_executable(edge))
        creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        self._process = subprocess.Popen(
            [
                str(edge),
                f"--app={self._url}",
                f"--user-data-dir={self._profile.name}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-mode",
                "--disable-extensions",
                "--start-maximized",
            ],
            close_fds=True,
            creationflags=creationflags,
        )
        deadline = time.monotonic() + STARTUP_TIMEOUT_SEC
        while time.monotonic() < deadline:
            new_windows = {
                hwnd: owner
                for hwnd, owner in _visible_windows_for_executable(edge).items()
                if hwnd not in existing_windows and _window_title(hwnd) == WINDOW_TITLE
            }
            if new_windows:
                self._window_handle, self._window_process_id = next(iter(new_windows.items()))
                return
            time.sleep(0.1)
        raise RuntimeError("Microsoft Edgeのアプリウィンドウの起動がタイムアウトしました。")

    def is_open(self) -> bool:
        if self._window_handle is None:
            return False
        return bool(_window_api().IsWindow(self._window_handle))

    def show(self) -> None:
        if not self.is_open():
            return
        # Restore a minimized window and bring it to the foreground on duplicate launch.
        user32 = _window_api()
        user32.ShowWindow(self._window_handle, 9)  # SW_RESTORE
        user32.SetForegroundWindow(self._window_handle)

    def close(self) -> None:
        process = self._process
        user32 = _window_api()
        if self._window_handle is not None and user32.IsWindow(self._window_handle):
            user32.SendMessageW(self._window_handle, 0x0010, 0, 0)  # WM_CLOSE
        if self._window_process_id is not None:
            _wait_for_process_exit(self._window_process_id, 10_000, terminate_on_timeout=True)
        if process is not None and process.poll() is None and process.pid != self._window_process_id:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self._process = None
        self._window_handle = None
        self._window_process_id = None
        try:
            self._profile.cleanup()
        except OSError as exc:
            self._logger.warning("Could not remove temporary desktop window profile: %s", exc)


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
    desktop_window = None
    result = 0
    try:
        app = _import_app_with_retry(logger)
        import uvicorn

        def request_server_shutdown(reason: str) -> None:
            if server is not None and not server.should_exit:
                logger.info("Graceful shutdown requested: %s", reason)
                server.should_exit = True

        @app.post("/api/v1/shutdown")
        def shutdown():
            # This endpoint remains only for setup-driven restart and automated
            # lifecycle tests. The normal user exit path is the window close event.
            timer = threading.Timer(0.3, request_server_shutdown, args=("internal lifecycle API",))
            timer.daemon = True
            timer.start()
            return {"stopping": True}

        port = _find_free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=port,
                                log_config=None, access_log=False, log_level="critical",
                                loop="asyncio", http="h11", ws="none",
                                timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_TIMEOUT_SEC)
        server = uvicorn.Server(config)
        server_thread = threading.Thread(target=server.run, daemon=True, name="local-web-server")
        server_thread.start()
        deadline = time.monotonic() + 30
        while not server.started and server_thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.1)
        if not server.started:
            raise RuntimeError()
        url = f"http://127.0.0.1:{port}/"
        logger.info("Application started on local port %s", port)
        if os.environ.get("KY_NO_BROWSER") != "1":
            desktop_window = DesktopWindow(url, logger)
            desktop_window.open()
            guard.set_show_callback(desktop_window.show)
            logger.info("Desktop window opened")

        while server_thread.is_alive():
            if desktop_window is not None and not desktop_window.is_open():
                request_server_shutdown("desktop window closed")
                break
            server_thread.join(timeout=0.25)
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
            server_thread.join(timeout=GRACEFUL_SHUTDOWN_TIMEOUT_SEC + 5)
            if server_thread.is_alive():
                logger.error("Graceful shutdown timed out; forcing the local server to stop")
                server.force_exit = True
                server_thread.join(timeout=10)
        if desktop_window:
            desktop_window.close()
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
            # PyInstaller 6 uses _PYI_* variables too; leaving them makes the child reuse the
            # parent's extraction folder, which is deleted on exit (the UI then fails with HTTP 500).
            restart_env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("_MEI", "_PYI"))}
            restart_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
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
