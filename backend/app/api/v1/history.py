from __future__ import annotations

from fastapi import APIRouter

from backend.app.schemas.history import AnalysisHistoryResponse
from backend.app.services.history_service import (
  load_analysis_history,
  save_analysis_history,
)

router = APIRouter(prefix="/api/v1", tags=["history"])

@router.get("/history", response_model=AnalysisHistoryResponse)
def get_history() -> AnalysisHistoryResponse:
  return AnalysisHistoryResponse(history=load_analysis_history())

@router.put("/history", response_model=AnalysisHistoryResponse)
def update_history(req: AnalysisHistoryResponse) -> AnalysisHistoryResponse:
  return AnalysisHistoryResponse(history=save_analysis_history(req.history))
