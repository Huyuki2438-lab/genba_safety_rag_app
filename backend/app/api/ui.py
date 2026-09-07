from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from backend.app.core.config import settings

router = APIRouter(tags=["ui"])

@router.get("/", response_class=HTMLResponse)
def render_index() -> HTMLResponse:
    dist_index = settings.BASE_DIR / "dist" / "index.html"
    return HTMLResponse(dist_index.read_text(encoding="utf-8"))
