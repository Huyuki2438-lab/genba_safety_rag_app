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
  from playwright.sync_api import sync_playwright
  with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True, timeout=30000)
    try:
      page = browser.new_page(java_script_enabled=False)
      # Reports may only load embedded images. No network or local file reads.
      page.route("**/*", lambda route: route.abort())
      page.set_content(html, wait_until="load", timeout=30000)
      return page.pdf(format="A4", print_background=True,
                      margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"})
    finally:
      browser.close()


@router.post("/pdf")
def generate_pdf(req: PdfGenerateRequest) -> Response:
  from uuid import UUID, uuid4
  from backend.app.core.secrets import redact
  from backend.app.core.config import settings
  from backend.app.core.shared_storage import require_root, publish, HistoryStorageUnavailable
  from backend.app.repositories.history_repository import history_repository
  try:
    require_root(settings.DATA_DIR / "reports")
    record_id = str(UUID(req.record_id)) if req.record_id else "standalone"
    if req.record_id and not history_repository.get(record_id):
      raise HTTPException(status_code=404, detail="対象の履歴が見つかりません。")
    html = render_template_for_pdf("report.html", redact(req.context))
    pdf_bytes = _html_to_pdf_bytes(html)
    filename = f"{uuid4()}.pdf"
    publish(settings.DATA_DIR / "reports" / record_id / filename, pdf_bytes)
  except HistoryStorageUnavailable as exc:
    raise HTTPException(status_code=503, detail=str(exc)) from None
  except HTTPException:
    raise
  except Exception:
    raise HTTPException(status_code=500, detail="PDFを保存できませんでした。Microsoft EdgeとNASの接続・書き込み権限を確認してください。") from None
  return Response(content=pdf_bytes, media_type="application/pdf",
    headers={"Content-Disposition": _content_disposition(req.output_filename),
             "X-Report-Url": f"/reports/{record_id}/{filename}"})
