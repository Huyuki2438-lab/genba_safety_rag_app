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
  project_id: str | None = None
  project_name: str | None = None
  # project_idが既に設定済み(配布時にセット済み、または過去に保存済み)で、
  # 以後変更するとその現場の既存履歴が別IDとして扱われ表示されなくなるため
  # 変更不可であることを示す。
  project_id_locked: bool = False


class DataRootRequest(BaseModel):
  path: str
  # project_idは初回(未設定)の場合のみ有効。既に設定済みの場合はサーバー側で無視される。
  project_id: str | None = None
  project_name: str | None = None


class DataRootCheckResponse(BaseModel):
  ok: bool
  message: str
  # この保存先に既に別PCが設定した現場ID/現場名が見つかった場合に返す。
  # フロントエンドはこれを使い、現場ID/現場名欄を自動入力・ロックできる。
  detected_project_id: str | None = None
  detected_project_name: str | None = None


class BrowseFolderResponse(BaseModel):
  path: str | None = None
  available: bool


class NetworkCredentialsRequest(BaseModel):
  path: str
  username: str
  password: str
