from __future__ import annotations
from backend.app.core.ai.base import AIBase
from backend.app.core.ai.providers.vertex import VertexProvider
from backend.app.core.config import settings


class AIFactory:
    @staticmethod
    def get_provider() -> AIBase:
        return VertexProvider(
            api_key=settings.VERTEX_API_KEY,
            model=settings.GEMINI_MODEL,
            project_id=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        )
