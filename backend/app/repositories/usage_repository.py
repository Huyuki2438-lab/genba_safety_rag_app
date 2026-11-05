from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, Field, field_validator

from backend.app.core.config import settings
from backend.app.core.shared_storage import HistoryStorageUnavailable, publish, require_root


UsageStatus = Literal[
    "success",
    "max_tokens",
    "safety",
    "response_error",
    "markdown_validation_failed",
    "http_error",
    "communication_error",
    "upstream_error",
]

_USAGE_NAMESPACE = UUID("cce5563e-b11b-4b44-8ad8-94958e069acc")
_SAFE_METADATA_KEYS = {
    "promptTokenCount",
    "candidatesTokenCount",
    "thoughtsTokenCount",
    "totalTokenCount",
    "cachedContentTokenCount",
    "promptTokensDetails",
    "cacheTokensDetails",
    "candidatesTokensDetails",
    "toolUsePromptTokenCount",
    "toolUsePromptTokensDetails",
    "trafficType",
}


class UsageStorageUnavailable(RuntimeError):
    pass


class APIUsageRecord(BaseModel):
    usage_id: str
    request_id: str
    response_id: str | None = None
    created_at: datetime
    model: str
    status: UsageStatus
    prompt_token_count: int | None = Field(default=None, ge=0)
    candidates_token_count: int | None = Field(default=None, ge=0)
    thoughts_token_count: int | None = Field(default=None, ge=0)
    total_token_count: int | None = Field(default=None, ge=0)
    cached_content_token_count: int | None = Field(default=None, ge=0)
    prompt_tokens_details: list[dict[str, Any]] | None = None
    traffic_type: str | None = None
    usage_source: Literal["vertex_usage_metadata", "unavailable"]
    usage_metadata: dict[str, Any] | None = None

    @field_validator("usage_id", "request_id")
    @classmethod
    def _valid_uuid(cls, value: str) -> str:
        return str(UUID(value))

    @field_validator("created_at")
    @classmethod
    def _timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must include a timezone")
        return value


def _safe_metadata(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    safe: dict[str, Any] = {}
    for key in _SAFE_METADATA_KEYS:
        item = value.get(key)
        if isinstance(item, bool):
            continue
        if isinstance(item, (int, str)):
            safe[key] = item
        elif isinstance(item, list):
            details = [
                {str(k): v for k, v in detail.items() if isinstance(v, (str, int)) and not isinstance(v, bool)}
                for detail in item
                if isinstance(detail, dict)
            ]
            safe[key] = details
    return safe or None


def _token_count(metadata: dict[str, Any] | None, key: str) -> int | None:
    value = metadata.get(key) if metadata else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def build_usage_record(
    *,
    request_id: str,
    created_at: datetime,
    model: str,
    status: UsageStatus,
    response_id: str | None = None,
    usage_metadata: dict[str, Any] | None = None,
) -> APIUsageRecord:
    normalized_request_id = str(UUID(request_id))
    safe = _safe_metadata(usage_metadata)
    details = safe.get("promptTokensDetails") if safe else None
    traffic_type = safe.get("trafficType") if safe else None
    return APIUsageRecord(
        usage_id=str(uuid5(_USAGE_NAMESPACE, normalized_request_id)),
        request_id=normalized_request_id,
        response_id=response_id,
        created_at=created_at,
        model=model,
        status=status,
        prompt_token_count=_token_count(safe, "promptTokenCount"),
        candidates_token_count=_token_count(safe, "candidatesTokenCount"),
        thoughts_token_count=_token_count(safe, "thoughtsTokenCount"),
        total_token_count=_token_count(safe, "totalTokenCount"),
        cached_content_token_count=_token_count(safe, "cachedContentTokenCount"),
        prompt_tokens_details=details if isinstance(details, list) else None,
        traffic_type=traffic_type if isinstance(traffic_type, str) else None,
        usage_source="vertex_usage_metadata" if safe is not None else "unavailable",
        usage_metadata=safe,
    )


class UsageRepository:
    def __init__(self, root: Path | None = None, project_id: str | None = None):
        self.root = root or settings.DATA_DIR
        self.project_id = project_id or settings.PROJECT_ID

    def initialize_schema(self) -> None:
        require_root(self.root)
        try:
            (self.root / "usage").mkdir(exist_ok=True)
        except OSError as exc:
            raise UsageStorageUnavailable(f"API利用台帳フォルダを作成できません: {self.root / 'usage'} ({exc})") from None

    def add(self, record: APIUsageRecord) -> APIUsageRecord:
        record = APIUsageRecord.model_validate(record)
        path = self.root / "usage" / record.created_at.strftime("%Y-%m") / f"{record.usage_id}.json"
        payload = {
            "schema_version": 1,
            "usage_id": record.usage_id,
            "request_id": record.request_id,
            "project_id": self.project_id,
            "usage": record.model_dump(mode="json"),
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            publish(path, content)
            return record
        except HistoryStorageUnavailable as exc:
            existing = self._read_existing(path)
            if existing is not None and existing.request_id == record.request_id:
                return existing
            # exc text is a path + OS reason only (no payload / secrets).
            raise UsageStorageUnavailable(f"API利用台帳を保存できません: {path.parent} / {exc}") from None

    @staticmethod
    def _read_existing(path: Path) -> APIUsageRecord | None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("schema_version") != 1:
                return None
            record = APIUsageRecord.model_validate(raw["usage"])
            if raw.get("usage_id") != record.usage_id or raw.get("request_id") != record.request_id:
                return None
            return record
        except (OSError, ValueError, KeyError, TypeError):
            return None


usage_repository = UsageRepository()
