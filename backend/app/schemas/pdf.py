from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PdfGenerateRequest(BaseModel):
  template_name: str = "report.html"
  context: dict[str, Any] = Field(default_factory=dict)
  engine: Literal["playwright", "wkhtmltopdf"] = "playwright"
  output_filename: str = "report.pdf"
  history_folder: str | None = None
