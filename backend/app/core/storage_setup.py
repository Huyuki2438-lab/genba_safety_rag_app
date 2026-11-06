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

CONNECTION_OK_MESSAGE = "保存先に接続できました。"
CONNECTION_NG_MESSAGE = "保存先にアクセスできません。パスまたはネットワーク接続を確認してください。"

STORAGE_TYPES = ("local", "nas")

DEFAULT_PROJECT_NAME = "現場"
PROJECT_ID_MAX_LEN = 50
PROJECT_NAME_MAX_LEN = 200
PROJECT_ID_FORBIDDEN_CHARS = '\\/:*?"<>|'

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
    if any(ord(ch) < 32 or ch in PROJECT_ID_FORBIDDEN_CHARS for ch in text):
        return False, (
            "現場ID（project_id）に使えない文字が含まれています。"
            f"{' '.join(PROJECT_ID_FORBIDDEN_CHARS)} や改行を除いた、英数字・日本語・ハイフン等で入力してください（例: 001）。"
        )
    return True, ""


def validate_project_name(raw: str) -> tuple[bool, str]:
    text = (raw or "").strip()
    if not text:
        return False, "現場名（工事名）を入力してください。"
    if len(text) > PROJECT_NAME_MAX_LEN:
        return False, f"現場名（工事名）は{PROJECT_NAME_MAX_LEN}文字以内で入力してください。"
    return True, ""


def normalize_storage_type(raw: str | None) -> str:
    """保存先種別を正規化する。旧バージョンの"network"は"nas"として扱う。未指定・不正は空文字。"""
    value = str(raw or "").strip().lower()
    if value == "network":
        value = "nas"
    return value if value in STORAGE_TYPES else ""


def validate_storage_type(raw: str | None) -> tuple[bool, str]:
    if not normalize_storage_type(raw):
        return False, "保存先種別は「ローカル」または「社内NAS」から選択してください。"
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


PERMISSION_NG_MESSAGE = "保存先に書き込む権限がありません。"
NETWORK_NG_MESSAGE = "保存先に接続できません。ネットワークまたはNASの状態を確認してください。"


def _ensure_directory(path: Path) -> None:
    """保存先フォルダが無ければ親フォルダごと作成する。失敗時は原因別のメッセージで例外にする。

    UNCパスは共有名(\\サーバー\共有)自体が存在しない場合に作成を試みない
    (NAS未接続・共有名の誤りを、誤ったフォルダの自動作成で隠さないため)。
    """
    network = _is_network_path(path)
    try:
        if path.is_dir():
            return
    except OSError:
        if network:
            raise HistoryStorageUnavailable(NETWORK_NG_MESSAGE) from None
        raise HistoryStorageUnavailable(PERMISSION_NG_MESSAGE) from None
    share = _unc_share_root(path)
    if share and not Path(share).is_dir():
        raise HistoryStorageUnavailable(NETWORK_NG_MESSAGE)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise HistoryStorageUnavailable(PERMISSION_NG_MESSAGE) from None
    except OSError as exc:
        if network:
            raise HistoryStorageUnavailable(NETWORK_NG_MESSAGE) from None
        raise HistoryStorageUnavailable(
            f"保存先フォルダを作成できません。ドライブ名・パスを確認してください。詳細: {exc.strerror or exc}"
        ) from None


def validate_data_root(raw_path: str, create_missing: bool = False) -> tuple[bool, str]:
    """保存先候補を検証する。

    戻り値: (成功したか, 利用者向け日本語メッセージ)
    確認内容: フォルダの存在・読み取り可否・書き込み(テストファイル作成/削除)可否。
    create_missing=True の場合、存在しないフォルダは親フォルダごと作成してから確認する
    (利用者が明示的に「確認」「設定」を実行したときのみ。起動時の到達確認では作成しない)。
    原因別メッセージ: 権限なし / NAS未接続 / その他(パス誤り等)を区別する。
    """
    text = (raw_path or "").strip()
    if not text:
        return False, "データ保存先を入力または選択してください。"
    path = normalize_path(text)
    if not path.is_absolute():
        return False, "データ保存先は絶対パスで指定してください（例: C:\\KYデータ　または　\\\\NAS\\共有\\フォルダ）。"
    try:
        if create_missing:
            _ensure_directory(path)
        require_root(path)
        check_writable(path)
    except HistoryStorageUnavailable as exc:
        detail = str(exc)
        if detail in (PERMISSION_NG_MESSAGE, NETWORK_NG_MESSAGE) or detail.startswith("保存先フォルダを作成できません"):
            return False, detail
        if _is_network_path(path):
            return False, f"{NETWORK_NG_MESSAGE}\n詳細: {detail}"
        if "権限がありません" in detail:
            return False, f"{PERMISSION_NG_MESSAGE}\n詳細: {detail}"
        return False, f"{CONNECTION_NG_MESSAGE}\n詳細: {detail}"
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
    storage_type: str | None = None,
) -> tuple[str, str]:
    """config.jsonの project_id / project_name / data_root / storage_type を更新する。

    既存のconfig.jsonを読み込み、対象の項目だけを書き換える(将来追加された
    別の項目は削除しない)。引数が空の項目は既存値、それも無ければ既定値を使う。
    storage_typeが未指定/不正な場合は data_root の形から自動判定する。
    戻り値は実際に書き込まれた(project_id, project_name)。
    """
    path = normalize_path(raw_path)
    current = read_raw_config(config_file)
    project_id = (str(project_id or "").strip()
                  or str(current.get("project_id") or "").strip()
                  or "001")
    project_name = (str(project_name or "").strip()
                     or str(current.get("project_name") or "").strip()
                     or DEFAULT_PROJECT_NAME)
    storage_type = normalize_storage_type(storage_type) or ("nas" if _is_network_path(path) else "local")
    payload = dict(current)
    payload.update({
        "project_id": project_id,
        "project_name": project_name,
        "data_root": str(path),
        "storage_type": storage_type,
        # 全ての初期化が終わった後にだけ書かれる「セットアップ完了」印。
        # 過去バージョンのconfig.jsonにはこの項目が無いため、読み込み側は
        # 「項目なし=完了済み」として扱う(後方互換)。
        "setup_completed": True,
    })
    config_file.parent.mkdir(parents=True, exist_ok=True)
    # 書き込み途中で失敗/中断しても既存のconfig.jsonを壊さないよう、一時ファイル経由で置き換える。
    temp = config_file.with_name(f".{uuid.uuid4().hex}.config.tmp")
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8-sig")
        os.replace(temp, config_file)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
    return project_id, project_name


def current_data_root(config_file: Path) -> str | None:
    data_root = str(read_raw_config(config_file).get("data_root") or "").strip()
    return data_root or None


SITE_MARKER_FILENAME = ".ky_site.json"

MARKER_MISSING = "missing"
MARKER_INVALID = "invalid"
MARKER_VALID = "valid"


def inspect_site_marker(root: Path) -> tuple[str, dict[str, str] | None]:
    """マーカーの正常・欠損・破損を区別して読み取る。"""
    marker = root / SITE_MARKER_FILENAME
    if not marker.exists():
        return MARKER_MISSING, None
    try:
        if not marker.is_file():
            return MARKER_INVALID, None
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return MARKER_INVALID, None
    if not isinstance(data, dict):
        return MARKER_INVALID, None
    project_id = str(data.get("project_id") or "").strip()
    if not project_id:
        return MARKER_INVALID, None
    project_name = str(data.get("project_name") or "").strip()
    if project_name == DEFAULT_PROJECT_NAME:
        project_name = ""
    return MARKER_VALID, {"project_id": project_id, "project_name": project_name}


def inspect_record_project_ids(root: Path) -> tuple[bool, set[str]]:
    """records内に履歴JSONがあるかと、読み取れた工事IDの集合を返す。

    読み取り専用の検査であり、履歴ファイルの移動・修復・上書きは行わない。
    """
    records = root / "records"
    if not records.is_dir():
        return False, set()
    has_records = False
    project_ids: set[str] = set()
    try:
        paths = records.rglob("*.json")
        for path in paths:
            has_records = True
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                project_id = data.get("project_id")
                if isinstance(project_id, str) and project_id.strip():
                    project_ids.add(project_id.strip())
    except OSError:
        # recordsの列挙自体に失敗した場合も「空」とはみなさず保護側へ倒す。
        return True, project_ids
    return has_records, project_ids


def storage_protection_issue(root: Path) -> tuple[str | None, dict[str, str] | None]:
    """既存データを自動変更してはいけない状態なら、利用者向け理由を返す。"""
    marker_status, marker = inspect_site_marker(root)
    has_records, record_project_ids = inspect_record_project_ids(root)
    if len(record_project_ids) > 1:
        return (
            "この保存先の既存履歴に複数の工事IDが混在しています。自動判定や変更は行いません。"
            "既存データを保護するため、管理者に確認してください。",
            marker,
        )
    if marker_status == MARKER_INVALID:
        return (
            ".ky_site.jsonが破損しているため設定を保存できません。自動上書きは行いません。"
            "既存データを保護するため、管理者に確認してください。",
            None,
        )
    if marker_status == MARKER_MISSING and has_records:
        found = next(iter(record_project_ids), "不明")
        return (
            f".ky_site.jsonが見つかりませんが、既存の解析履歴があります（履歴の工事ID: {found}）。"
            "新しい工事IDでマーカーは作成しません。管理者に確認してください。",
            None,
        )
    if marker and record_project_ids and marker["project_id"] not in record_project_ids:
        return (
            f".ky_site.jsonの工事ID（{marker['project_id']}）と既存履歴の工事ID"
            f"（{next(iter(record_project_ids))}）が一致しません。自動修正は行いません。管理者に確認してください。",
            marker,
        )
    return None, marker


def read_site_marker(root: Path) -> dict[str, str] | None:
    """保存先(NAS等)に既に記録されている現場情報(現場ID・現場名)を読み取る。

    複数PCが同じ保存先を指定した際、2台目以降が現場ID・現場名を手入力し直して
    値がずれてしまう(誤入力・表記ゆれ)のを防ぐため、最初にその保存先を設定した
    PCが書き込む目印ファイルを参照する。見つからない/壊れている場合はNone。
    """
    status, marker = inspect_site_marker(root)
    return marker if status == MARKER_VALID else None


def write_site_marker(root: Path, project_id: str, project_name: str) -> bool:
    """保存先へ現場情報の目印ファイルを書き込む（既存なら変更しない）。

    既存マーカーは正常・破損を問わず上書きしない。新規作成に失敗した場合は
    既存設定との互換性を保つためログへ記録し、呼び出し元には成否を返す。
    """
    marker = root / SITE_MARKER_FILENAME
    if marker.exists():
        return False
    payload = json.dumps({"project_id": project_id, "project_name": project_name}, ensure_ascii=False, indent=2) + "\n"
    temp = root / f".{uuid.uuid4().hex}.ky_site.tmp"
    try:
        temp.write_text(payload, encoding="utf-8")
        if marker.exists():
            return False
        os.replace(temp, marker)
        return True
    except OSError as exc:
        logger.warning("現場情報マーカー（%s）の書き込みに失敗しました: %s", marker, exc)
        return False
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def apply_setup(
    config_file: Path,
    raw_path: str,
    project_id: str | None,
    project_name: str | None,
    storage_type: str | None = None,
) -> tuple[bool, str]:
    """初回セットアップ・設定画面からの変更の両方で使う共通の保存処理。

    順序: 入力検証 → 保存先の確認 → 既存の現場情報との照合 → サブフォルダ/履歴保存領域の
    初期化(HistoryRepository.initialize_schemaを再利用) → config.json保存(完了フラグ付き)
    → 新規フォルダの場合のみ現場情報マーカー作成。config.jsonはアトミックに書くため、途中で失敗しても
    「セットアップ完了」状態にはならず、既存の設定も壊れない。
    戻り値: (成功したか, 利用者向け日本語メッセージ)
    """
    from backend.app.repositories.history_repository import HistoryRepository

    raw = read_raw_config(config_file)
    local_project_id = str(raw.get("project_id") or "").strip()
    previous_root = str(raw.get("data_root") or "").strip()
    project_id_locked = bool(local_project_id and previous_root and raw.get("setup_completed", True) is not False)

    ok, message = validate_project_name(project_name or "")
    if not ok:
        return False, message
    requested_id = (project_id or "").strip() or local_project_id
    ok, message = validate_project_id(requested_id)
    if not ok:
        return False, message
    if project_id_locked and requested_id != local_project_id:
        return False, (
            f"工事IDは設定確定後に変更できません（現在の工事ID: {local_project_id}）。"
            "既存履歴を保護するため、工事名のみ変更できます。"
        )
    if storage_type:
        ok, message = validate_storage_type(storage_type)
        if not ok:
            return False, message

    ok, message = validate_data_root(raw_path, create_missing=True)
    if not ok:
        return False, message

    target = normalize_path(raw_path)
    marker_status, marker = inspect_site_marker(target)
    protection_issue, marker = storage_protection_issue(target)
    if protection_issue:
        return False, protection_issue
    detected_note = ""
    project_id = requested_id
    if marker:
        if project_id_locked and requested_id != marker["project_id"]:
            return False, (
                f"この保存先には既に別の現場（現場ID: {marker['project_id']}、"
                f"現場名: {marker['project_name'] or '不明'}）のデータがあります。"
                f"入力された現場ID（{requested_id}）と一致しません。"
                "保存先のフォルダを間違えていないかご確認ください。"
            )
        if not project_id_locked:
            # 初回設定時は、手入力の値より保存先に既にある現場情報を優先する
            # (複数PCで現場ID・現場名がずれるのを防ぐため)。
            project_id = marker["project_id"]
            project_name = marker["project_name"] or project_name
            detected_note = (
                f"\n\nこの保存先の既存の現場情報（現場ID: {project_id}、"
                f"現場名: {project_name}）を使用しました。"
            )

    effective_id = str(project_id or "").strip() or "001"
    try:
        HistoryRepository(root=target, project_id=effective_id).initialize_schema()
    except HistoryStorageUnavailable as exc:
        return False, f"保存先に必要なフォルダを作成できませんでした。設定は保存していません。\n詳細: {exc}"

    try:
        final_id, final_name = save_data_root(config_file, raw_path, project_id, project_name, storage_type)
    except OSError as exc:
        logger.warning("config.json の保存に失敗しました: %s", exc)
        return False, (
            f"設定ファイル（{config_file}）を保存できませんでした。アプリのフォルダへの書き込み権限と"
            f"空き容量を確認してください。設定は変更されていません。詳細: {exc}"
        )
    if marker_status == MARKER_MISSING:
        write_site_marker(target, final_id, final_name)
    return True, message + detected_note


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
