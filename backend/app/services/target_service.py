from __future__ import annotations

from backend.app.core.config import settings
from backend.app.schemas.settings import SettingsResponse


def get_runtime_settings() -> SettingsResponse:
  """Read-only AI configuration summary (admin display only, no secrets)."""
  is_configured = bool(settings.VERTEX_API_KEY and settings.GEMINI_MODEL and settings.GOOGLE_CLOUD_PROJECT)
  return SettingsResponse(
    ai_enabled=is_configured,
    provider_label="Vertex AI",
    model=settings.GEMINI_MODEL or None,
  )
