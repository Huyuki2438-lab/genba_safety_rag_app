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


class AnalysisService:
    def __init__(self):
        self.ai_factory = AIFactory()
        self.prompt_manager = prompt_manager
        self.parser = AnalysisParser()

    def run_analysis(self, req: AnalyzeSafetyRequest) -> AnalyzeSafetyResponse:
        # 1. Target identification
        target_id = req.target or settings.DEFAULT_AI_TARGET
        target_config = settings.TARGETS.get(target_id)
        if not target_config:
            raise ValueError(f"Invalid target: {target_id}")

        # 2. Prompt generation (backend-driven; frontend values are ignored)
        system_instruction = self.prompt_manager.render("kiken_yochi_system.jinja2")
        user_prompt = self.prompt_manager.render("kiken_yochi_user.jinja2")

        # 3. Get AI provider and run inference (req is NOT mutated)
        provider = self.ai_factory.get_provider(target_id)
        markdown = provider.predict(
            image_base64=req.image_base64,
            image_mime_type=req.image_mime_type,
            system_instruction=system_instruction,
            prompt=user_prompt,
        )

        # 4. Parse response (extract structured data)
        factors = self.parser.parse_markdown_table(markdown)

        # 5. Build intermediate result
        result_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        analysis_result = SafetyAnalysisResult(
            id=result_id,
            timestamp=timestamp,
            markdown=markdown,
            factors=factors,
            used_target=target_id,
            used_model=target_config.get_model(),
            used_kind=target_config.kind,
            is_inference=True,
        )

        return AnalyzeSafetyResponse(
            markdown=markdown,
            used_target=target_id,
            used_label=target_config.label,
            used_kind=target_config.kind,
            used_model=target_config.get_model(),
            result=analysis_result,
        )


analysis_service = AnalysisService()
