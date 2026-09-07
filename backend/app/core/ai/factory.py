from __future__ import annotations
from backend.app.core.ai.base import AIBase
from backend.app.core.ai.providers.gemini import GeminiProvider
from backend.app.core.ai.providers.vertex import VertexProvider
from backend.app.core.config import settings, TargetConfig

class AIFactory:
    @staticmethod
    def get_provider(target_id: str | None = None) -> AIBase:
        target_id = target_id or settings.DEFAULT_AI_TARGET
        config = settings.TARGETS.get(target_id)
        
        if not config:
            raise ValueError(f"Unknown AI target: {target_id}")
            
        if config.kind == "gemini":
            return GeminiProvider(
                api_key=config.get_api_key(),
                model=config.get_model()
            )
        elif config.kind == "vertex":
            return VertexProvider(
                api_key=config.get_api_key(),
                model=config.get_model(),
                project_id=config.get_project_id(),
                location=config.get_location()
            )
        else:
            raise ValueError(f"Unsupported AI kind: {config.kind}")
