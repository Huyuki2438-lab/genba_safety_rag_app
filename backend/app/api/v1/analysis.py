from __future__ import annotations
import logging
from typing import Literal
from fastapi import APIRouter, HTTPException
from backend.app.schemas.analysis import AnalyzeSafetyRequest, AnalyzeSafetyResponse, AnalyzeSafetyErrorResponse
from backend.app.services.analysis_service import analysis_service

logger = logging.getLogger("genba_safety_rag_app.api")
router = APIRouter(prefix="/api/v1", tags=["analysis"])

def _build_error_detail(
  *,
  error_type: Literal[
    "invalid_target",
    "configuration_error",
    "upstream_error",
    "internal_error",
  ],
  error_category: Literal["target不正", "設定不足", "API呼び出し失敗", "内部エラー"],
  error_message: str,
  metadata: dict[str, str | None] | None = None,
) -> dict:
  safe_metadata = metadata or {}
  payload = AnalyzeSafetyErrorResponse(
    error_type=error_type,
    error_category=error_category,
    error_message=error_message,
    used_target=safe_metadata.get("used_target"),
    used_label=safe_metadata.get("used_label"),
    used_kind=safe_metadata.get("used_kind"),  # type: ignore[arg-type]
    used_model=safe_metadata.get("used_model"),
  )
  return payload.model_dump()

@router.post("/analyze", response_model=AnalyzeSafetyResponse)
def analyze_safety(req: AnalyzeSafetyRequest) -> AnalyzeSafetyResponse:
    try:
        return analysis_service.run_analysis(req)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_build_error_detail(
                error_type="invalid_target",
                error_category="target不正",
                error_message=str(exc),
                metadata={"used_target": req.target},
            ),
        ) from exc
    except Exception as exc:
        logger.exception("Analysis failed")
        raise HTTPException(
            status_code=500,
            detail=_build_error_detail(
                error_type="internal_error",
                error_category="内部エラー",
                error_message=f"分析実行に失敗しました: {exc}",
                metadata={"used_target": req.target},
            ),
        ) from exc
