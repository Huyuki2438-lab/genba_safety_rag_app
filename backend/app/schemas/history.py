from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AnalysisHistoryEntry(BaseModel):
  id: str = Field(min_length=1)
  createdAt: str = Field(min_length=1)
  imageName: str = Field(min_length=1)
  historyFolder: str | None = None
  imageFileName: str | None = None
  imageMimeType: str | None = None
  imageBase64: str | None = None
  imageUrl: str | None = None
  mode: Literal["gemini_a", "gemini_b", "vertex"]
  providerDisplayLabel: str = Field(min_length=1)
  model: str = Field(min_length=1)
  markdown: str


class AnalysisHistoryResponse(BaseModel):
  history: list[AnalysisHistoryEntry]
