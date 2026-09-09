from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PdfGenerateRequest(BaseModel):
  template_name: str = "report.html"
  context: dict[str, Any] = Field(default_factory=dict)
  engine: Literal["playwright", "wkhtmltopdf"] = "playwright"
  output_filename: str = "report.pdf"
  history_folder: str | None = None

  record_id: str | None = None


class ExcelGenerateRequest(BaseModel):
  """Data shared by the PDF and Excel report export actions."""

  title: str = "現場安全 危険分析レポート"
  generated_at: str
  markdown: str
  output_filename: str = "安全分析レポート.xlsx"
  record_id: str | None = None
  site_name: str = ""
  work_content: str = ""
  main_risk: str = ""
  created_by: str = ""
  image_data_url: str | None = None
