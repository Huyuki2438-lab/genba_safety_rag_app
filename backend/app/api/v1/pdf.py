from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.app.schemas.pdf import PdfGenerateRequest
from backend.app.services.template_service import render_template_for_pdf

router = APIRouter(prefix="/api/v1", tags=["pdf"])


def _content_disposition(filename: str) -> str:
  encoded = quote(filename, safe="")
  return f"attachment; filename*=UTF-8''{encoded}"


def _html_to_pdf_bytes(html: str) -> bytes:
  try:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415
  except ImportError as exc:
    raise RuntimeError(
      "playwright is not installed. Run: pip install playwright"
    ) from exc

  with sync_playwright() as p:
    try:
      browser = p.chromium.launch()
    except Exception as exc:
      raise RuntimeError(
        f"Chromium not found. Run: .venv\\Scripts\\playwright.exe install chromium ({exc})"
      ) from exc

    try:
      page = browser.new_page()
      page.set_content(html, wait_until="networkidle")
      pdf_bytes = page.pdf(
        format="A4",
        print_background=True,
        margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
      )
    finally:
      browser.close()

  return pdf_bytes


@router.post("/pdf")
def generate_pdf(req: PdfGenerateRequest) -> Response:
  html = render_template_for_pdf(req.template_name, req.context)

  try:
    pdf_bytes = _html_to_pdf_bytes(html)
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}") from exc

  return Response(
    content=pdf_bytes,
    media_type="application/pdf",
    headers={"Content-Disposition": _content_disposition(req.output_filename)},
  )
