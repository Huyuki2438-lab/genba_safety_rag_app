from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.core.config import settings
from backend.app.api.router import api_router


def create_app() -> FastAPI:
    app = FastAPI()


    # React build assets (JS/CSS)
    dist_assets_dir = settings.BASE_DIR / "dist" / "assets"
    if dist_assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=dist_assets_dir), name="assets")

    # Legacy static files (pdf.css used by template_service)
    app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")

    # Original photos are held in the shared NAS directory, never in PostgreSQL.
    # check_dir=False lets the desktop app start even when the NAS is temporarily offline.
    app.mount("/history", StaticFiles(directory=settings.PHOTO_STORAGE_DIR, check_dir=False), name="history")

    app.include_router(api_router)
    return app


if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)


app = create_app()
