from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.core.app_paths import local_data_root

from backend.app.schemas.settings import SettingsResponse
from backend.app.services.target_service import get_runtime_settings

router = APIRouter(prefix="/api/v1", tags=["settings"])


class LastRegistrant(BaseModel):
  name: str = Field(default="", max_length=255)


def _last_registrant_file() -> Path:
  return local_data_root() / "last_registrant.json"


@router.get("/settings/last-registrant", response_model=LastRegistrant)
def get_last_registrant() -> LastRegistrant:
  """このPCで最後に使った登録者名(PCローカル保存。NASには置かない)。"""
  try:
    return LastRegistrant(name=str(json.loads(_last_registrant_file().read_text(encoding="utf-8")).get("name", ""))[:255])
  except (OSError, ValueError, AttributeError):
    return LastRegistrant()


@router.put("/settings/last-registrant", response_model=LastRegistrant)
def put_last_registrant(body: LastRegistrant) -> LastRegistrant:
  body = LastRegistrant(name=body.name.strip())
  path = _last_registrant_file()
  try:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": body.name}, ensure_ascii=False), encoding="utf-8")
  except OSError:
    pass  # 保持できなくても保存処理自体は妨げない
  return body

@router.get("/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
  return get_runtime_settings()
