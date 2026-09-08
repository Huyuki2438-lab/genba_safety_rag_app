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
    return HTTPException(status_code=503, detail=NETWORK_MESSAGE)


@router.get("/history", response_model=AnalysisHistoryResponse)
def get_history(date_from: date | None = Query(default=None), date_to: date | None = Query(default=None),
                site_name: str | None = Query(default=None), work_content: str | None = Query(default=None),
                created_by: str | None = Query(default=None), keyword: str | None = Query(default=None)) -> AnalysisHistoryResponse:
    try:
        return AnalysisHistoryResponse(history=history_service.list(
            date_from=date_from, date_to=date_to, site_name=site_name, work_content=work_content,
            created_by=created_by, keyword=keyword,
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
