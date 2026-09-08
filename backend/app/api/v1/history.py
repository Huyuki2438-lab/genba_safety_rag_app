from __future__ import annotations

import getpass
from datetime import date

from fastapi import APIRouter, HTTPException, Query, Response

from backend.app.core.config import settings
from backend.app.repositories.history_repository import HistoryStorageUnavailable
from backend.app.schemas.history import AnalysisHistoryEntry, AnalysisHistoryResponse, CreateAnalysisHistoryRequest
from backend.app.services.history_service import history_service

router = APIRouter(prefix="/api/v1", tags=["history"])
NETWORK_MESSAGE = "共有データへ接続できません。ネットワーク接続を確認してください。"


def _unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


@router.get("/history", response_model=AnalysisHistoryResponse)
def get_history(date_from: date | None = Query(default=None), date_to: date | None = Query(default=None),
                site_name: str | None = Query(default=None), work_content: str | None = Query(default=None),
                created_by: str | None = Query(default=None), keyword: str | None = Query(default=None),
                offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=200)) -> AnalysisHistoryResponse:
    try:
        return AnalysisHistoryResponse(history=history_service.list(
            date_from=date_from, date_to=date_to, site_name=site_name, work_content=work_content,
            created_by=created_by, keyword=keyword, offset=offset, limit=limit,
        ))
    except HistoryStorageUnavailable as exc:
        raise _unavailable(exc)


@router.get("/history/{entry_id}", response_model=AnalysisHistoryEntry)
def get_history_entry(entry_id: str) -> AnalysisHistoryEntry:
    try:
        entry = history_service.get(entry_id)
    except HistoryStorageUnavailable as exc:
        raise _unavailable(exc)
    if entry is None:
        raise HTTPException(status_code=404, detail="履歴が見つかりません。")
    return entry


@router.post("/history", response_model=AnalysisHistoryEntry, status_code=201)
def create_history(request: CreateAnalysisHistoryRequest) -> AnalysisHistoryEntry:
    try:
        return history_service.create(request, fallback_created_by=settings.DEFAULT_CREATED_BY.strip() or getpass.getuser())
    except (HistoryStorageUnavailable, OSError) as exc:
        raise _unavailable(exc)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/history/{entry_id}", status_code=204)
def delete_history(entry_id: str) -> Response:
    try:
        if not history_service.soft_delete(entry_id):
            raise HTTPException(status_code=404, detail="履歴が見つかりません。")
    except HistoryStorageUnavailable as exc:
        raise _unavailable(exc)
    return Response(status_code=204)


@router.get("/history/{entry_id}/reports")
def list_reports(entry_id: str):
    from uuid import UUID
    from backend.app.core.shared_storage import require_root
    try:
        require_root(settings.DATA_DIR / "reports")
        folder = settings.DATA_DIR / "reports" / str(UUID(entry_id))
        return {"reports": [{"name": p.name, "url": f"/reports/{entry_id}/{p.name}"}
                            for p in sorted(folder.glob("*.pdf"))]}
    except (OSError, HistoryStorageUnavailable):
        raise HTTPException(status_code=503, detail=NETWORK_MESSAGE) from None
    except ValueError:
        raise HTTPException(status_code=404, detail="履歴が見つかりません。") from None


@router.post("/history/{entry_id}/export")
def export_history(entry_id: str):
    import io
    import json
    import zipfile
    from uuid import uuid4
    from fastapi.responses import Response
    from backend.app.repositories.history_repository import history_repository
    from backend.app.core.shared_storage import require_root, publish
    try:
        record = history_repository.get(entry_id)
        if not record:
            raise HTTPException(status_code=404, detail="履歴が見つかりません。")
        require_root(settings.DATA_DIR / "export")
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("record.json", json.dumps({"schema_version": 1, "project_id": settings.PROJECT_ID,
                "record_id": record.id, "analysis": record.model_dump(mode="json")}, ensure_ascii=False))
            photo = settings.PHOTO_STORAGE_DIR / record.photo_relative_path
            z.write(photo, "images/" + photo.name)
            for pdf in (settings.DATA_DIR / "reports" / record.id).glob("*.pdf"):
                z.write(pdf, "reports/" + pdf.name)
        content = archive.getvalue()
        name = f"{uuid4()}.zip"
        publish(settings.DATA_DIR / "export" / name, content)
        return Response(content, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})
    except (HistoryStorageUnavailable, OSError):
        raise HTTPException(status_code=503, detail="書き出しできませんでした。写真・PDFの有無、NASの接続・権限・空き容量を確認してください。") from None
