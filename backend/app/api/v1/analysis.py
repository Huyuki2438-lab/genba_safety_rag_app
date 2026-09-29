from __future__ import annotations
import logging
from typing import Literal
from fastapi import APIRouter, HTTPException
from backend.app.schemas.analysis import AnalyzeSafetyRequest, AnalyzeSafetyResponse, AnalyzeSafetyErrorResponse
from backend.app.services.analysis_service import analysis_service, AIConfigurationError
from backend.app.core.ai.base import UpstreamExecutionError
from backend.app.core.secrets import redact

logger = logging.getLogger("genba_safety_rag_app.api")
router = APIRouter(prefix="/api/v1", tags=["analysis"])

def _build_error_detail(
  *,
  error_type: Literal[
    "configuration_error",
    "upstream_error",
    "internal_error",
  ],
  error_category: Literal["設定不足", "API呼び出し失敗", "内部エラー"],
  error_message: str,
) -> dict:
  payload = AnalyzeSafetyErrorResponse(
    error_type=error_type,
    error_category=error_category,
    error_message=error_message,
  )
  return redact(payload.model_dump())

@router.post("/analyze", response_model=AnalyzeSafetyResponse)
def analyze_safety(req: AnalyzeSafetyRequest) -> AnalyzeSafetyResponse:
    try:
        return analysis_service.run_analysis(req)
    except AIConfigurationError as exc:
        logger.error("AI configuration is incomplete")
        raise HTTPException(
            status_code=503,
            detail=_build_error_detail(
                error_type="configuration_error",
                error_category="設定不足",
                error_message="AI解析の設定が不足しています。管理者へ連絡してください。",
            ),
        ) from exc
    except UpstreamExecutionError as exc:
        logger.error("Analysis upstream call failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail=_build_error_detail(
                error_type="upstream_error",
                error_category="API呼び出し失敗",
                error_message="AI解析に失敗しました。しばらくしてから再度実行してください。",
            ),
        ) from exc
    except Exception as exc:
        logger.error("Analysis failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail=_build_error_detail(
                error_type="internal_error",
                error_category="内部エラー",
                error_message="AI解析に失敗しました。しばらくしてから再度実行してください。",
            ),
        ) from exc
