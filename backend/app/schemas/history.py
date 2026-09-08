from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AnalysisHistoryEntry(BaseModel):
    id: str
    createdAt: datetime
    updatedAt: datetime
    createdBy: str
    siteName: str = ""
    workContent: str = ""
    mainRisk: str = ""
    imageName: str
    imageMimeType: str | None = None
    imageUrl: str | None = None
    mode: Literal["gemini_a", "gemini_b", "vertex"]
    providerDisplayLabel: str
    model: str
    markdown: str


class CreateAnalysisHistoryRequest(BaseModel):
    imageName: str = Field(min_length=1, max_length=500)
    imageMimeType: str | None = Field(default=None, max_length=100)
    imageBase64: str = Field(min_length=1)
    mode: Literal["gemini_a", "gemini_b", "vertex"]
    providerDisplayLabel: str = Field(min_length=1, max_length=255)
    model: str = Field(min_length=1, max_length=255)
    markdown: str
    siteName: str = Field(default="", max_length=255)
    workContent: str = Field(default="", max_length=500)
    mainRisk: str = Field(default="", max_length=500)
    createdBy: str = Field(default="", max_length=255)


class AnalysisHistoryResponse(BaseModel):
    history: list[AnalysisHistoryEntry]
