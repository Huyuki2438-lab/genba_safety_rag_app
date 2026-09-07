from __future__ import annotations

from fastapi import APIRouter

from backend.app.schemas.settings import SettingsResponse
from backend.app.services.target_service import get_runtime_settings

router = APIRouter(prefix="/api/v1", tags=["settings"])

@router.get("/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
  return get_runtime_settings()
