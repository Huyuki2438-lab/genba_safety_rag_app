"""初回起動時/設定変更時の「データ保存先」設定ロジック。

config.json の書き込み・検証・Windowsフォルダ選択ダイアログを扱う。
APIキー等の秘密情報はここでは一切扱わない(secrets.envは対象外)。
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from backend.app.core.shared_storage import HistoryStorageUnavailable, check_writable, require_root

logger = logging.getLogger("genba_safety_rag_app.storage_setup")

CONNECTION_OK_MESSAGE = "保存先への接続を確認しました。"
CONNECTION_NG_MESSAGE = "保存先にアクセスできません。ネットワーク接続またはフォルダのアクセス権を確認してください。"

PROJECT_ID_MAX_LEN = 50
PROJECT_NAME_MAX_LEN = 200

# この空き容量を下回ったら注意喚起する(写真等の保存が失敗し始める前に気づけるように)。
LOW_SPACE_WARNING_BYTES = 5 * 1024 ** 3  # 5GB


def _free_space_note(path: Path) -> str:
    """保存先の空き容量を確認し、利用者向けの注記文字列を返す(失敗時は空文字)。"""
    try:
        free_bytes = shutil.disk_usage(path).free
    except OSError:
        return ""
    free_gb = free_bytes / (1024 ** 3)
    if free_bytes < LOW_SPACE_WARNING_BYTES:
        return (
            f"\n\n⚠ 保存先の空き容量が少なくなっています（残り約{free_gb:.1f}GB）。"
            "このままでは写真等が保存できなくなるおそれがあります。空き容量の確保をご検討ください。"
        )
    return f"\n（保存先の空き容量：約{free_gb:.1f}GB）"


def validate_project_id(raw: str) -> tuple[bool, str]:
    text = (raw or "").strip()
    if not text:
        return False, "現場ID（project_id）を入力してください。"
    if len(text) > PROJECT_ID_MAX_LEN:
        return False, f"現場ID（project_id）は{PROJECT_ID_MAX_LEN}文字以内で入力してください。"
    return True, ""


def validate_project_name(raw: str) -> tuple[bool, str]:
    text = (raw or "").strip()
    if not text:
        return False, "現場名（工事名）を入力してください。"
    if len(text) > PROJECT_NAME_MAX_LEN:
        return False, f"現場名（工事名）は{PROJECT_NAME_MAX_LEN}文字以内で入力してください。"
    return True, ""


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
    return True, CONNECTION_OK_MESSAGE + _free_space_note(path)


def read_raw_config(config_file: Path) -> dict:
    if not config_file.is_file():
        return {}
    try:
        text = config_file.read_text(encoding="utf-8-sig")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_data_root(
    config_file: Path,
    raw_path: str,
    project_id: str | None = None,
    project_name: str | None = None,
) -> tuple[str, str]:
    """data_root(・project_name)を更新する。戻り値は実際に書き込まれた(project_id, project_name)。

    project_idは一度設定されたら変更しない(既存履歴が別IDとして扱われ
    表示されなくなるのを防ぐため)。未設定の場合のみ引数の値、それも
    無ければ既定値"001"を補う。project_nameはいつでも変更可能。
    """
    path = normalize_path(raw_path)
    current = read_raw_config(config_file)
    existing_project_id = str(current.get("project_id") or "").strip()
    project_id = existing_project_id or (str(project_id or "").strip()) or "001"
    project_name = (str(project_name or "").strip()
                     or str(current.get("project_name") or "").strip()
                     or "現場")
    storage_type = "network" if _is_network_path(path) else "local"
    payload = {
        "project_id": project_id,
        "project_name": project_name,
        "data_root": str(path),
        "storage_type": storage_type,
    }
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8-sig")
    return project_id, project_name


def current_data_root(config_file: Path) -> str | None:
    data_root = str(read_raw_config(config_file).get("data_root") or "").strip()
    return data_root or None


SITE_MARKER_FILENAME = ".ky_site.json"


def read_site_marker(root: Path) -> dict[str, str] | None:
    """保存先(NAS等)に既に記録されている現場情報(現場ID・現場名)を読み取る。

    複数PCが同じ保存先を指定した際、2台目以降が現場ID・現場名を手入力し直して
    値がずれてしまう(誤入力・表記ゆれ)のを防ぐため、最初にその保存先を設定した
    PCが書き込む目印ファイルを参照する。見つからない/壊れている場合はNone。
    """
    marker = root / SITE_MARKER_FILENAME
    try:
        if not marker.is_file():
            return None
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    project_id = str(data.get("project_id") or "").strip()
    if not project_id:
        return None
    return {"project_id": project_id, "project_name": str(data.get("project_name") or "").strip()}


def write_site_marker(root: Path, project_id: str, project_name: str) -> None:
    """保存先へ現場情報の目印ファイルを書き込む(既存なら上書き)。

    他PCの現場ID/現場名の自動検出のためだけの補助情報であり、失敗しても
    アプリの動作に支障はないため、書き込めなくてもログのみで握り潰す。
    """
    marker = root / SITE_MARKER_FILENAME
    payload = json.dumps({"project_id": project_id, "project_name": project_name}, ensure_ascii=False, indent=2) + "\n"
    temp = root / f".{uuid.uuid4().hex}.ky_site.tmp"
    try:
        temp.write_text(payload, encoding="utf-8")
        os.replace(temp, marker)
    except OSError as exc:
        logger.warning("現場情報マーカー（%s）の書き込みに失敗しました: %s", marker, exc)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def _unc_share_root(path: Path) -> str | None:
    """UNCパスから接続対象の共有部分（\\\\サーバー名\\共有名）だけを取り出す。

    `net use` はサブフォルダ単位ではなく共有単位で認証するため。
    """
    text = str(path)
    if not (text.startswith("\\\\") or text.startswith("//")):
        return None
    parts = [p for p in text.replace("/", "\\").split("\\") if p]
    if len(parts) < 2:
        return None
    return "\\\\" + parts[0] + "\\" + parts[1]


def connect_network_credentials(raw_path: str, username: str, password: str) -> tuple[bool, str]:
    """社内NASが現在のWindowsログオンと異なる資格情報を要求する場合に、
    `net use` で別の資格情報として接続する。

    パスワードはコマンドライン引数には渡さず標準入力経由で `net use` に渡し、
    プロセス一覧等に平文表示されないようにする。接続情報はWindowsの資格情報
    マネージャーに保存させる(/savecred)ため、本アプリ自身はパスワードを一切
    保存しない。
    """
    if sys.platform != "win32":
        return False, "この機能はWindows専用です。"
    username = (username or "").strip()
    if not username:
        return False, "ユーザー名を入力してください。"
    if not password:
        return False, "パスワードを入力してください。"
    share = _unc_share_root(normalize_path(raw_path))
    if not share:
        return False, "NASの共有フォルダのパス（例: \\\\サーバー名\\共有名\\フォルダ）を確認してください。"
    try:
        proc = subprocess.Popen(
            ["net", "use", share, "*", f"/user:{username}", "/persistent:yes", "/savecred"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        stdout, stderr = proc.communicate(input=password + "\n", timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        return False, "NASへの接続がタイムアウトしました。ネットワーク接続を確認してください。"
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("net use failed to launch: %s", exc)
        return False, f"資格情報の設定に失敗しました。詳細: {exc}"
    if proc.returncode != 0:
        detail = (stderr or stdout or "").strip()
        logger.warning("net use exited with code %s: %s", proc.returncode, detail)
        return False, f"資格情報でのNAS接続に失敗しました。ユーザー名・パスワード・共有名をご確認ください。詳細: {detail}"
    return True, f"{share} への接続情報を設定しました。このまま「接続を確認」をお試しください。"


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
