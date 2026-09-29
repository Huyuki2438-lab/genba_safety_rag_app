"""初期設定(データ保存先の選択・検証・保存)API。

secrets.env / APIキーはここでは一切扱わない。設定変更はconfig.jsonの
data_root(・project_id/project_nameの保持・storage_typeの自動判定)のみ行う。
"""
from __future__ import annotations

import logging
import sys

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from backend.app.core.app_paths import restart_flag_path
from backend.app.core.config import settings
from backend.app.core.storage_setup import (
    connect_network_credentials,
    current_data_root,
    normalize_path,
    open_folder_dialog,
    read_raw_config,
    read_site_marker,
    save_data_root,
    validate_data_root,
    validate_project_id,
    validate_project_name,
    write_site_marker,
)
from backend.app.schemas.setup import (
    BrowseFolderResponse,
    DataRootCheckResponse,
    DataRootRequest,
    NetworkCredentialsRequest,
    SetupStatusResponse,
)

logger = logging.getLogger("genba_safety_rag_app.api")

router = APIRouter(prefix="/api/v1/setup", tags=["setup"])


@router.get("/status", response_model=SetupStatusResponse)
async def get_status() -> SetupStatusResponse:
    raw = read_raw_config(settings.CONFIG_FILE)
    data_root = current_data_root(settings.CONFIG_FILE) or (str(settings.DATA_DIR) if not settings.SETUP_REQUIRED else None)
    # settings.SETUP_REQUIRED already reflects whether this run needs the
    # wizard (frozen/exe with no usable data_root yet); dev runs without
    # config.json are never SETUP_REQUIRED and must keep working as before.
    configured = not settings.SETUP_REQUIRED
    reachable = False
    reachable_message = None
    if configured:
        reachable, reachable_message = await run_in_threadpool(validate_data_root, str(settings.DATA_DIR))
    project_id = str(raw.get("project_id") or "").strip() or None
    return SetupStatusResponse(
        configured=configured,
        data_root=data_root,
        storage_type=(raw.get("storage_type") or None),
        config_error=None,
        reachable=reachable,
        reachable_message=reachable_message,
        project_id=project_id,
        project_name=(str(raw.get("project_name") or "").strip() or None),
        project_id_locked=project_id is not None,
    )


@router.post("/browse", response_model=BrowseFolderResponse)
async def browse_folder() -> BrowseFolderResponse:
    if sys.platform != "win32":
        return BrowseFolderResponse(path=None, available=False)
    path = await run_in_threadpool(open_folder_dialog)
    if path is None:
        logger.warning("Folder dialog returned no path (cancelled by user, or dialog unavailable on this PC).")
    return BrowseFolderResponse(path=path, available=True)


@router.post("/connect-credentials", response_model=DataRootCheckResponse)
async def connect_credentials(req: NetworkCredentialsRequest) -> DataRootCheckResponse:
    """社内NASが現在のWindowsログオンと別の資格情報を要求する場合に使う。

    パスワードはここで一度だけ使用し、アプリ側では保存しない
    (Windowsの資格情報マネージャーに委ねる)。
    """
    ok, message = await run_in_threadpool(connect_network_credentials, req.path, req.username, req.password)
    return DataRootCheckResponse(ok=ok, message=message)


@router.post("/validate", response_model=DataRootCheckResponse)
async def validate(req: DataRootRequest) -> DataRootCheckResponse:
    ok, message = await run_in_threadpool(validate_data_root, req.path)
    detected = None
    if ok:
        detected = await run_in_threadpool(read_site_marker, normalize_path(req.path))
    return DataRootCheckResponse(
        ok=ok,
        message=message,
        detected_project_id=(detected["project_id"] if detected else None),
        detected_project_name=(detected["project_name"] if detected else None),
    )


@router.post("/save", response_model=DataRootCheckResponse)
async def save(req: DataRootRequest) -> DataRootCheckResponse:
    raw = read_raw_config(settings.CONFIG_FILE)
    local_project_id = str(raw.get("project_id") or "").strip()
    project_id_locked = bool(local_project_id)

    ok, message = validate_project_name(req.project_name or "")
    if not ok:
        return DataRootCheckResponse(ok=False, message=message)
    if not project_id_locked:
        ok, message = validate_project_id(req.project_id or "")
        if not ok:
            return DataRootCheckResponse(ok=False, message=message)

    ok, message = await run_in_threadpool(validate_data_root, req.path)
    if not ok:
        return DataRootCheckResponse(ok=False, message=message)

    # 保存先に既に別PCが設定した現場情報がないか確認し、現場の混在を防ぐ。
    target_path = normalize_path(req.path)
    marker = await run_in_threadpool(read_site_marker, target_path)
    detected_note = ""
    request_project_id = req.project_id
    request_project_name = req.project_name
    if marker:
        if project_id_locked and marker["project_id"] != local_project_id:
            return DataRootCheckResponse(
                ok=False,
                message=(
                    f"この保存先には既に別の現場（現場ID: {marker['project_id']}、"
                    f"現場名: {marker['project_name'] or '不明'}）のデータがあります。"
                    f"このPCに設定されている現場ID（{local_project_id}）と一致しません。"
                    "保存先のフォルダを間違えていないかご確認ください。"
                ),
            )
        if not project_id_locked:
            # 初回設定時は、手入力の値より保存先に既にある現場情報を優先する
            # (複数PCで現場ID・現場名がずれるのを防ぐため)。
            request_project_id = marker["project_id"]
            request_project_name = marker["project_name"] or req.project_name
            detected_note = (
                f"\n\nこの保存先の既存の現場情報（現場ID: {request_project_id}、"
                f"現場名: {request_project_name}）を使用しました。"
            )

    final_project_id, final_project_name = await run_in_threadpool(
        save_data_root, settings.CONFIG_FILE, req.path, request_project_id, request_project_name
    )
    await run_in_threadpool(write_site_marker, target_path, final_project_id, final_project_name)
    return DataRootCheckResponse(ok=True, message=message + detected_note)


@router.post("/restart")
def restart() -> dict:
    """desktop_app.py へ再起動を要求する(EXE経由で起動していない場合は無効)。"""
    flag = restart_flag_path()
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1", encoding="utf-8")
    return {"restarting": True}
