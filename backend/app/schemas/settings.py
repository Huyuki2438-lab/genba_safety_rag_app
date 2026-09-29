from __future__ import annotations

from pydantic import BaseModel


class SettingsResponse(BaseModel):
  """Read-only AI configuration summary for admin display.

  Never includes API keys, service account details, or other credentials.
  """
  ai_enabled: bool
  provider_label: str
  model: str | None = None
