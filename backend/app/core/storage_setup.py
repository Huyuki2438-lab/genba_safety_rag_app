"""初回起動時/設定変更時の「データ保存先」設定ロジック。

config.json の書き込み・検証・Windowsフォルダ選択ダイアログを扱う。
APIキー等の秘密情報はここでは一切扱わない(secrets.envは対象外)。
"""
from __future__ import annotations

import ctypes
import json
import logging
import subprocess
import sys
from pathlib import Path

from backend.app.core.shared_storage import HistoryStorageUnavailable, check_writable, require_root

logger = logging.getLogger("genba_safety_rag_app.storage_setup")

CONNECTION_OK_MESSAGE = "保存先への接続を確認しました。"
CONNECTION_NG_MESSAGE = "保存先にアクセスできません。ネットワーク接続またはフォルダのアクセス権を確認してください。"


def _is_network_path(path: Path) -> bool:
    text = str(path)
    if text.startswith("\\\\") or text.startswith("//"):
        return True
    if sys.platform == "win32" and path.drive:
        try:
            DRIVE_REMOTE = 4
            return ctypes.windll.kernel32.GetDriveTypeW(path.drive + "\\") == DRIVE_REMOTE
        except Exception:
            return False
    return False


def normalize_path(raw: str) -> Path:
    """先頭・末尾の空白を除去し、Windowsパスとして扱う。"""
    return Path(raw.strip().rstrip("\\/"))


def validate_data_root(raw_path: str) -> tuple[bool, str]:
    """保存先候補を検証する。

    戻り値: (成功したか, 利用者向け日本語メッセージ)
    確認内容: フォルダの存在・読み取り可否・書き込み(テストファイル作成/削除)可否。
    """
    text = (raw_path or "").strip()
    if not text:
        return False, "データ保存先を入力または選択してください。"
    path = normalize_path(text)
    if not path.is_absolute():
        return False, "データ保存先は絶対パスで指定してください（例: C:\\KYデータ　または　\\\\NAS\\共有\\フォルダ）。"
    try:
        require_root(path)
        check_writable(path)
    except HistoryStorageUnavailable as exc:
        return False, f"{CONNECTION_NG_MESSAGE}\n詳細: {exc}"
    return True, CONNECTION_OK_MESSAGE


def read_raw_config(config_file: Path) -> dict:
    if not config_file.is_file():
        return {}
    try:
        text = config_file.read_text(encoding="utf-8-sig")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_data_root(config_file: Path, raw_path: str) -> None:
    """既存のconfig.jsonのproject_id/project_nameは保持し、data_rootのみ更新する。

    project_id/project_nameが未設定(初回・installerless起動)の場合は
    利用者に手動編集させないため、既定値を補う。
    """
    path = normalize_path(raw_path)
    current = read_raw_config(config_file)
    project_id = str(current.get("project_id") or "001").strip() or "001"
    project_name = str(current.get("project_name") or "現場").strip() or "現場"
    storage_type = "network" if _is_network_path(path) else "local"
    payload = {
        "project_id": project_id,
        "project_name": project_name,
        "data_root": str(path),
        "storage_type": storage_type,
    }
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8-sig")


def current_data_root(config_file: Path) -> str | None:
    data_root = str(read_raw_config(config_file).get("data_root") or "").strip()
    return data_root or None


_FOLDER_DIALOG_TITLE = "データ保存先フォルダを選択してください（ローカルフォルダ・NAS共有フォルダのどちらも可）"


def _open_folder_dialog_powershell() -> tuple[bool, str | None]:
    """PowerShell の System.Windows.Forms.FolderBrowserDialog でフォルダ選択する。

    バックエンドはFastAPIのスレッドプールワーカー上で動くため、同一プロセス内で
    ctypesのSHBrowseForFolderWを呼ぶとCOMアパートメント/メッセージポンプまわりの
    制約で失敗することがある(社内ロックダウン端末等で特に起きやすい)。
    別プロセス(PowerShell)にダイアログ表示を任せることでこれを避ける。

    戻り値: (PowerShellでダイアログを実行できたか, 選択されたパス)。
    ユーザーがダイアログをキャンセルした場合も「実行はできた」ので
    (True, None) を返す。この場合はctypesフォールバックへは進まない
    (キャンセルしたのに別のダイアログが再度開くのを防ぐ)。
    """
    script = (
        "Add-Type -AssemblyName System.Windows.Forms | Out-Null;"
        "$owner = New-Object System.Windows.Forms.Form -Property @{"
        "  TopMost=$true; ShowInTaskbar=$false; StartPosition='CenterScreen'; Size=New-Object System.Drawing.Size(0,0)"
        "};"
        "$owner.Show();"
        # 別プロセス(PowerShell)のウィンドウはWindowsのフォアグラウンドロックにより
        # 他ウィンドウの裏に隠れて開くことがある。最小化→復元は、この制約を
        # 回避してウィンドウを前面化する標準的な手段。
        "$owner.WindowState = 'Minimized';"
        "$owner.WindowState = 'Normal';"
        "$owner.Activate();"
        "$f = New-Object System.Windows.Forms.FolderBrowserDialog;"
        f"$f.Description = '{_FOLDER_DIALOG_TITLE}';"
        "$f.ShowNewFolderButton = $true;"
        "$result = $f.ShowDialog($owner);"
        "$owner.Close();"
        "if ($result -eq [System.Windows.Forms.DialogResult]::OK) {"
        "  [Console]::Out.Write($f.SelectedPath)"
        "}"
    )
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Sta",
                "-ExecutionPolicy", "Bypass",
                "-WindowStyle", "Hidden",
                "-Command", script,
            ],
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("PowerShell folder dialog failed to launch: %s", exc)
        return False, None
    if result.returncode != 0:
        logger.warning("PowerShell folder dialog exited with code %s: %s", result.returncode, result.stderr.strip())
        return False, None
    return True, (result.stdout.strip() or None)


def open_folder_dialog(initial_dir: str | None = None) -> str | None:
    """Windows標準のフォルダ選択ダイアログを開く。UNCパスも入力可。

    利用不可(非Windows等)の場合はNoneを返し、呼び出し側はパス直接入力へ誘導する。
    """
    if sys.platform != "win32":
        return None
    ran, path = _open_folder_dialog_powershell()
    if ran:
        return path
    return _open_folder_dialog_ctypes()


def _open_folder_dialog_ctypes() -> str | None:
    """PowerShellが使えない環境向けのフォールバック実装。"""
    import ctypes.wintypes as wintypes

    BIF_RETURNONLYFSDIRS = 0x0001
    BIF_NEWDIALOGSTYLE = 0x0040
    BIF_USENEWUI = BIF_NEWDIALOGSTYLE | 0x0002
    MAX_PATH = 260

    class BROWSEINFO(ctypes.Structure):
        _fields_ = [
            ("hwndOwner", wintypes.HWND),
            ("pidlRoot", ctypes.c_void_p),
            ("pszDisplayName", ctypes.c_wchar_p),
            ("lpszTitle", ctypes.c_wchar_p),
            ("ulFlags", ctypes.c_uint),
            ("lpfn", ctypes.c_void_p),
            ("lParam", ctypes.c_void_p),
            ("iImage", ctypes.c_int),
        ]

    ole32 = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32
    ole32.CoInitialize(None)
    try:
        display_name = ctypes.create_unicode_buffer(MAX_PATH)
        bi = BROWSEINFO()
        bi.hwndOwner = None
        bi.pidlRoot = None
        bi.pszDisplayName = ctypes.cast(display_name, ctypes.c_wchar_p)
        bi.lpszTitle = "データ保存先フォルダを選択してください（ローカルフォルダ・NAS共有フォルダのどちらも可）"
        bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_USENEWUI
        bi.lpfn = None
        bi.lParam = None
        bi.iImage = 0
        pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
        if not pidl:
            return None
        try:
            path_buf = ctypes.create_unicode_buffer(MAX_PATH)
            if not shell32.SHGetPathFromIDListW(pidl, path_buf):
                return None
            return path_buf.value or None
        finally:
            ole32.CoTaskMemFree(pidl)
    except Exception as exc:
        logger.warning("ctypes folder dialog failed: %s", exc)
        return None
    finally:
        try:
            ole32.CoUninitialize()
        except Exception:
            pass
