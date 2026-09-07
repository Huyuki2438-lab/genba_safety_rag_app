from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AnalyzeSafetyRequest(BaseModel):
  # Backend generates prompts from Jinja2 templates, so frontend-supplied
  # prompt / system_instruction fields are not used. Kept for compatibility.
  prompt: str = ""
  system_instruction: str = ""
  image_base64: str = Field(min_length=1)
  image_mime_type: str = "image/jpeg"
  target: str | None = None


class KikenFactor(BaseModel):
  no: int
  item: str
  reason: str
  severity: Literal["高", "中", "低", "不明"]
  measures: str


class SafetyAnalysisResult(BaseModel):
  id: str
  timestamp: str
  markdown: str
  factors: list[KikenFactor] = Field(default_factory=list)
  used_target: str
  used_model: str
  used_kind: str
  is_inference: bool = True


class AnalyzeSafetyResponse(BaseModel):
  markdown: str
  used_target: str
  used_label: str
  used_kind: Literal["gemini", "vertex"]
  used_model: str
  result: SafetyAnalysisResult | None = None


class AnalyzeSafetyErrorResponse(BaseModel):
  error_type: Literal[
    "invalid_target",
    "configuration_error",
    "upstream_error",
    "internal_error",
  ]
  error_category: Literal["target不正", "設定不足", "API呼び出し失敗", "内部エラー"]
  error_message: str
  used_target: str | None = None
  used_label: str | None = None
  used_kind: Literal["gemini", "vertex"] | None = None
  used_model: str | None = None
  debug: dict[str, Any] | None = None
