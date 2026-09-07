from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from backend.app.core.config import settings, TargetConfig
from backend.app.schemas.settings import SettingsResponse, TargetSetting


class InvalidTargetError(ValueError):
  """リクエストされた target が定義一覧に存在しない場合のエラー。"""


class TargetConfigurationError(RuntimeError):
  """target 実行に必要な環境変数が不足している場合のエラー。"""


@dataclass(frozen=True)
class ResolvedTarget:
  target: str
  label: str
  kind: Literal["gemini", "vertex"]
  model: str
  api_key: str
  project_id: str | None = None
  location: str | None = None


def _missing_env_keys(config: TargetConfig) -> list[str]:
  missing = []
  if not config.get_api_key():
    missing.append(config.api_key_env)
  if not config.get_model():
    missing.append(config.model_env)
  if config.kind == "vertex":
    if config.project_id_env and not config.get_project_id():
      missing.append(config.project_id_env)
    if config.location_env and not config.get_location():
      missing.append(config.location_env)
  return missing


def _resolve_default_target_for_ui(targets: list[TargetSetting]) -> str:
  if settings.DEFAULT_AI_TARGET in settings.TARGETS:
    return settings.DEFAULT_AI_TARGET
  enabled_targets = [target.target for target in targets if target.enabled]
  if enabled_targets:
    return enabled_targets[0]
  return next(iter(settings.TARGETS.keys()))


def get_runtime_settings() -> SettingsResponse:
  targets = [
    TargetSetting(
      target=target_key,
      label=config.label,
      enabled=len(missing_keys) == 0,
      kind=config.kind,
      model=config.get_model() or None,
      missing_keys=missing_keys,
    )
    for target_key, config in settings.TARGETS.items()
    for missing_keys in [_missing_env_keys(config)]
  ]

  return SettingsResponse(
    default_target=_resolve_default_target_for_ui(targets),
    targets=targets,
  )


def get_target_metadata(target: str) -> dict[str, str | Literal["gemini", "vertex"] | None]:
  config = settings.TARGETS.get(target)
  if config is None:
    return {
      "used_target": target,
      "used_label": None,
      "used_kind": None,
      "used_model": None,
    }

  return {
    "used_target": target,
    "used_label": config.label,
    "used_kind": config.kind,
    "used_model": config.get_model() or None,
  }


def resolve_target(target: str | None) -> ResolvedTarget:
  candidate = (target or "").strip() or get_runtime_settings().default_target

  config = settings.TARGETS.get(candidate)
  if config is None:
    allowed = ", ".join(sorted(settings.TARGETS.keys()))
    raise InvalidTargetError(
      f"target='{candidate}' は不正です。利用可能なtarget: {allowed}"
    )

  missing = _missing_env_keys(config)
  if missing:
    missing_text = ", ".join(missing)
    raise TargetConfigurationError(
      f"target='{candidate}' の設定が不足しています。未設定: {missing_text}"
    )

  return ResolvedTarget(
    target=candidate,
    label=config.label,
    kind=config.kind,
    model=config.get_model(),
    api_key=config.get_api_key(),
    project_id=config.get_project_id(),
    location=config.get_location(),
  )
