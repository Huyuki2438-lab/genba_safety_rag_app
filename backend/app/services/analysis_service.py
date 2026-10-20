from __future__ import annotations
from datetime import datetime
import logging
import uuid

from backend.app.core.ai.factory import AIFactory
from backend.app.core.prompts.manager import prompt_manager
from backend.app.core.parser.analysis_parser import AnalysisParser
from backend.app.schemas.analysis import (
    AnalyzeSafetyRequest,
    AnalyzeSafetyResponse,
    SafetyAnalysisResult,
)
from backend.app.core.config import settings
from backend.app.core.secrets import redact
from backend.app.core.ai.base import AIResponse, UpstreamExecutionError


class AIConfigurationError(RuntimeError):
    """Raised when required Vertex AI settings are missing."""


logger = logging.getLogger("genba_safety_rag_app.analysis")


def _safe_usage_metadata(value: dict) -> dict[str, int]:
    """Only token counters are allowed into logs; never text or image data."""
    return {
        key: item for key, item in value.items()
        if isinstance(key, str) and "token" in key.casefold() and isinstance(item, int)
    }


class AnalysisService:
    def __init__(self):
        self.ai_factory = AIFactory()
        self.prompt_manager = prompt_manager
        self.parser = AnalysisParser()

    def run_analysis(self, req: AnalyzeSafetyRequest) -> AnalyzeSafetyResponse:
        if not (settings.VERTEX_API_KEY and settings.GEMINI_MODEL and settings.GOOGLE_CLOUD_PROJECT):
            raise AIConfigurationError("AI分析の設定が不足しています。管理者へ連絡してください。")

        # 1. Prompt generation (backend-driven; user values are context only)
        system_instruction = self.prompt_manager.render("kiken_yochi_system.jinja2")
        user_prompt = self.prompt_manager.render(
            "kiken_yochi_user.jinja2",
            work_content=req.work_content.strip(),
            main_risk=req.main_risk.strip(),
        )

        # 2. Get AI provider and run inference (req is NOT mutated)
        provider = self.ai_factory.get_provider()
        prediction = provider.predict(
            image_base64=req.image_base64,
            image_mime_type=req.image_mime_type,
            system_instruction=system_instruction,
            prompt=user_prompt,
        )

        if isinstance(prediction, AIResponse):
            markdown = redact(prediction.text)
            used_model = prediction.model_version.strip() if prediction.model_version and prediction.model_version.strip() else settings.GEMINI_MODEL
            logger.info(
                "Vertex response accepted: model_version=%s finish_reason=%s response_id=%s usage=%s finish_message_present=%s",
                used_model,
                prediction.finish_reason,
                prediction.response_id,
                _safe_usage_metadata(prediction.usage_metadata),
                bool(prediction.finish_message),
            )
        else:
            raise UpstreamExecutionError("AIの応答形式が不正です。再解析してください。")

        # 3. Parse response (extract structured data)
        try:
            factors = self.parser.validate_complete(markdown)
        except ValueError as exc:
            raise UpstreamExecutionError(str(exc)) from exc

        # 4. Build intermediate result
        result_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        analysis_result = SafetyAnalysisResult(
            id=result_id,
            timestamp=timestamp,
            markdown=markdown,
            factors=factors,
            used_model=used_model,
            is_inference=True,
        )

        return AnalyzeSafetyResponse(
            markdown=markdown,
            used_model=used_model,
            result=analysis_result,
        )


analysis_service = AnalysisService()
