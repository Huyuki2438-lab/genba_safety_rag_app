from __future__ import annotations
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from backend.app.core.config import settings
from backend.app.api.router import api_router
from backend.app.core.shared_storage import require_root, HistoryStorageUnavailable

def create_app():
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in {"127.0.0.1", "localhost", "testserver"}:
            return JSONResponse({"detail": "このPCからアクセスしてください。"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "接続元を確認してください。"}, status_code=403)
        if request.method == "POST" and not request.headers.get("content-type", "").startswith("application/json"):
            return JSONResponse({"detail": "入力形式を確認してください。"}, status_code=415)
        return await call_next(request)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({"detail": "入力内容を確認してください。"}, status_code=422)
    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        return JSONResponse({"detail": "処理できませんでした。接続と設定を確認して再試行してください。"}, status_code=500)
    assets = settings.BASE_DIR / "frontend_build" / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
    app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")
    def shared_file(folder, relative, suffixes):
        root = settings.DATA_DIR / folder
        path = root / relative
        try:
            require_root(root)
            if not path.resolve().is_relative_to(root.resolve()) or path.suffix.lower() not in suffixes:
                raise HTTPException(status_code=404, detail="ファイルが見つかりません。")
            if not path.is_file():
                raise HTTPException(status_code=404, detail="ファイルが見つかりません。管理者へ連絡してください。")
            return FileResponse(path)
        except (OSError, HistoryStorageUnavailable):
            raise HTTPException(status_code=503, detail="共有フォルダに接続できません。NASの接続と権限を確認してください。") from None
    @app.get("/history/{relative:path}")
    def photo(relative: str):
        return shared_file("images", relative, {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"})
    @app.get("/reports/{relative:path}")
    def report(relative: str):
        return shared_file("reports", relative, {".pdf"})
    @app.get("/api/v1/project")
    def project():
        return {"project_id": settings.PROJECT_ID, "project_name": settings.PROJECT_NAME}
    app.include_router(api_router)
    return app

app = create_app()
