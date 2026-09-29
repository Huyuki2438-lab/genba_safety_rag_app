from __future__ import annotations

from pydantic import BaseModel


class SetupStatusResponse(BaseModel):
  """データ保存先が設定済みかどうか。秘密情報は含めない。"""
  configured: bool
  data_root: str | None = None
  storage_type: str | None = None
  config_error: str | None = None
  # configured=True の場合のみ意味を持つ。設定済みの保存先に今この瞬間
  # 接続できるか(NAS切断等の検知用)。configured=Falseの間は常にFalse。
  reachable: bool = False
  reachable_message: str | None = None


class DataRootRequest(BaseModel):
  path: str


class DataRootCheckResponse(BaseModel):
  ok: bool
  message: str


class BrowseFolderResponse(BaseModel):
  path: str | None = None
  available: bool
