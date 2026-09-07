from fastapi import APIRouter
from backend.app.api.ui import router as ui_router
from backend.app.api.v1.analysis import router as analysis_router
from backend.app.api.v1.history import router as history_router
from backend.app.api.v1.pdf import router as pdf_router
from backend.app.api.v1.settings import router as settings_router

api_router = APIRouter()

# UI (root)
api_router.include_router(ui_router)

# V1 API
api_router.include_router(analysis_router)
api_router.include_router(history_router)
api_router.include_router(pdf_router)
api_router.include_router(settings_router)
