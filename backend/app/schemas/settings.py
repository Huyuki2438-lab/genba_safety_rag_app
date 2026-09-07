from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TargetSetting(BaseModel):
  target: str
  label: str
  enabled: bool
  kind: Literal["gemini", "vertex"]
  model: str | None = None
  missing_keys: list[str] = Field(default_factory=list)


class SettingsResponse(BaseModel):
  default_target: str
  targets: list[TargetSetting]
