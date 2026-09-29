from __future__ import annotations
from datetime import datetime
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


class AIConfigurationError(RuntimeError):
    """Raised when required Vertex AI settings are missing."""


class AnalysisService:
    def __init__(self):
        self.ai_factory = AIFactory()
        self.prompt_manager = prompt_manager
        self.parser = AnalysisParser()

    def run_analysis(self, req: AnalyzeSafetyRequest) -> AnalyzeSafetyResponse:
        if not (settings.VERTEX_API_KEY and settings.GEMINI_MODEL and settings.GOOGLE_CLOUD_PROJECT):
            raise AIConfigurationError("AI分析の設定が不足しています。管理者へ連絡してください。")

        # 1. Prompt generation (backend-driven; frontend values are ignored)
        system_instruction = self.prompt_manager.render("kiken_yochi_system.jinja2")
        user_prompt = self.prompt_manager.render("kiken_yochi_user.jinja2")

        # 2. Get AI provider and run inference (req is NOT mutated)
        provider = self.ai_factory.get_provider()
        markdown = provider.predict(
            image_base64=req.image_base64,
            image_mime_type=req.image_mime_type,
            system_instruction=system_instruction,
            prompt=user_prompt,
        )

        markdown = redact(markdown)

        # 3. Parse response (extract structured data)
        factors = self.parser.parse_markdown_table(markdown)

        # 4. Build intermediate result
        result_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        analysis_result = SafetyAnalysisResult(
            id=result_id,
            timestamp=timestamp,
            markdown=markdown,
            factors=factors,
            used_model=settings.GEMINI_MODEL,
            is_inference=True,
        )

        return AnalyzeSafetyResponse(
            markdown=markdown,
            used_model=settings.GEMINI_MODEL,
            result=analysis_result,
        )


analysis_service = AnalysisService()
