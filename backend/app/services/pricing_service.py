from __future__ import annotations

import json
import hashlib
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.core.config import settings
from backend.app.repositories.usage_repository import APIUsageRecord


MILLION = Decimal("1000000")


class PricingConfigurationError(RuntimeError):
    pass


class PricingConfigurationConflict(RuntimeError):
    pass


_CONFIG_UPDATE_LOCK = threading.Lock()


@contextmanager
def _exclusive_config_update(path: Path):
    """Serialize updates across app processes sharing the same data root."""
    lock_path = path.parent / f".{path.name}.update.lock"
    stream = None
    for attempt in range(2):
        try:
            stream = lock_path.open("xb")
            stream.write(f"pid={os.getpid()} time={time.time()}\n".encode("ascii"))
            stream.flush()
            break
        except FileExistsError:
            try:
                stale = time.time() - lock_path.stat().st_mtime > 600
            except OSError:
                stale = False
            if attempt == 0 and stale:
                try:
                    lock_path.unlink()
                    continue
                except OSError:
                    pass
            raise PricingConfigurationConflict(
                "料金設定を他の操作が更新中です。再読み込みしてから再試行してください。"
            ) from None
        except OSError as exc:
            raise PricingConfigurationError(
                f"料金設定の更新を開始できません: {path} ({exc})"
            ) from None
    try:
        yield
    finally:
        if stream is not None:
            stream.close()
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


class PricingTier(BaseModel):
    max_input_tokens: int | None = Field(default=None, ge=0)
    input_usd_per_million_tokens: Decimal | None = Field(default=None, ge=0)
    output_usd_per_million_tokens: Decimal | None = Field(default=None, ge=0)
    thoughts_usd_per_million_tokens: Decimal | None = Field(default=None, ge=0)
    cached_input_usd_per_million_tokens: Decimal | None = Field(default=None, ge=0)


class ModelPricingRule(BaseModel):
    model: str
    aliases: list[str] = Field(default_factory=list)
    pricing_effective_date: date
    traffic_type: str
    accepted_input_modalities: list[str] = Field(default_factory=lambda: ["TEXT", "IMAGE", "VIDEO"])
    tiers: list[PricingTier]
    source_url: str | None = None
    note: str | None = None

    @field_validator("model", "traffic_type")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("aliases")
    @classmethod
    def valid_aliases(cls, values: list[str]) -> list[str]:
        values = [value.strip() for value in values]
        if any(not value for value in values) or len(values) != len(set(values)):
            raise ValueError("aliases must be non-empty and unique")
        return values

    @field_validator("accepted_input_modalities")
    @classmethod
    def normalize_modalities(cls, values: list[str]) -> list[str]:
        return sorted({value.strip().upper() for value in values if value.strip()})

    @model_validator(mode="after")
    def valid_tiers(self) -> "ModelPricingRule":
        limits = [tier.max_input_tokens for tier in self.tiers]
        if not limits or limits[-1] is not None or any(value is None for value in limits[:-1]):
            raise ValueError("only the last tier may be unbounded")
        bounded = [value for value in limits if value is not None]
        if bounded != sorted(set(bounded)):
            raise ValueError("tier limits must be strictly increasing")
        return self

    def matches_model(self, model: str) -> bool:
        # Exact matches and explicitly configured aliases only. Never guess by prefix.
        return model == self.model or model in self.aliases


class ExchangeRate(BaseModel):
    exchange_rate_effective_date: date
    jpy_per_usd: Decimal | None = Field(default=None, gt=0)
    source: str | None = None


class UsagePricingConfig(BaseModel):
    schema_version: Literal[1]
    prices: list[ModelPricingRule]
    exchange_rates: list[ExchangeRate]

    @model_validator(mode="after")
    def unique_names(self) -> "UsagePricingConfig":
        owner: dict[str, str] = {}
        for rule in self.prices:
            for name in [rule.model, *rule.aliases]:
                if name in owner and owner[name] != rule.model:
                    raise ValueError(f"model name or alias is ambiguous: {name}")
                owner[name] = rule.model
        return self


class PricingResult(BaseModel):
    usage_id: str
    model: str
    pricing_status: Literal["estimated", "partial", "unavailable"]
    pricing_error_reason: str | None = None
    prompt_token_count: int | None = None
    candidates_token_count: int | None = None
    thoughts_token_count: int | None = None
    cached_content_token_count: int | None = None
    input_cost_usd: Decimal | None = None
    output_cost_usd: Decimal | None = None
    cache_cost_usd: Decimal | None = None
    total_cost_usd: Decimal | None = None
    exchange_rate_jpy_per_usd: Decimal | None = None
    exchange_rate_effective_date: date | None = None
    total_cost_jpy: Decimal | None = None
    pricing_effective_date: date | None = None
    pricing_snapshot: dict[str, Any] | None = None


def load_pricing_config(path: Path) -> UsagePricingConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"), parse_float=Decimal)
        return UsagePricingConfig.model_validate(raw)
    except (OSError, ValueError, TypeError) as exc:
        raise PricingConfigurationError(f"料金設定を読み込めません: {path} ({exc})") from None


def pricing_config_revision(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise PricingConfigurationError(f"料金設定を読み込めません: {path} ({exc})") from None


def load_usage_ledger(path: Path) -> APIUsageRecord:
    """Read a schema-v1 ledger without modifying it."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        if raw.get("schema_version") != 1:
            raise ValueError("unsupported usage ledger schema_version")
        record = APIUsageRecord.model_validate(raw["usage"])
        if raw.get("usage_id") != record.usage_id or raw.get("request_id") != record.request_id:
            raise ValueError("usage ledger identifiers do not match")
        return record
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PricingConfigurationError(f"API利用台帳を読み込めません: {path} ({exc})") from None


def resolve_pricing_config_path(app_dir: Path, data_dir: Path) -> Path:
    """Choose the app-wide price file, with read-only legacy compatibility.

    A site-local file is considered only when the app-wide file is absent.  We
    never copy, merge, delete, or repair either file here: in particular, a
    corrupt app-wide file must remain visible as an error instead of being
    silently hidden by another site's settings.
    """
    app_wide = Path(app_dir) / "settings" / "usage_pricing.json"
    legacy_site_local = Path(data_dir) / "settings" / "usage_pricing.json"
    if app_wide.is_file():
        return app_wide
    if legacy_site_local.is_file():
        return legacy_site_local
    return app_wide


class PricingService:
    def __init__(self, config: UsagePricingConfig | None = None, config_path: Path | None = None):
        self.config_path = config_path or resolve_pricing_config_path(
            settings.APP_DIR, settings.DATA_DIR
        )
        self._config = config

    @property
    def config(self) -> UsagePricingConfig:
        # External configs are reloaded for every calculation, so changing a price or
        # exchange rate requires neither an EXE rebuild nor an application restart.
        return self._config or load_pricing_config(self.config_path)

    def calculate_ledger(self, path: Path, *, pricing_date: date | None = None) -> PricingResult:
        return self.calculate(load_usage_ledger(path), pricing_date=pricing_date)

    def config_revision(self) -> str:
        return pricing_config_revision(self.config_path)

    def update_exchange_rate(
        self,
        *,
        jpy_per_usd: Decimal,
        effective_date: date,
        expected_revision: str,
    ) -> tuple[UsagePricingConfig, str]:
        """Update only exchange_rates and atomically replace the settings file."""
        rate = Decimal(jpy_per_usd)
        if not rate.is_finite() or rate <= 0:
            raise ValueError("為替レートは0より大きい数値を入力してください。")
        if not expected_revision:
            raise ValueError("料金設定のリビジョンが必要です。")

        temporary: Path | None = None
        with _CONFIG_UPDATE_LOCK, _exclusive_config_update(self.config_path):
            try:
                original = self.config_path.read_bytes()
                actual_revision = hashlib.sha256(original).hexdigest()
                if actual_revision != expected_revision:
                    raise PricingConfigurationConflict(
                        "料金設定が他の操作で更新されました。再読み込みしてから再試行してください。"
                    )
                raw = json.loads(original.decode("utf-8-sig"))
                if not isinstance(raw, dict):
                    raise ValueError("料金設定はJSONオブジェクトである必要があります。")

                exchange_rates = raw.get("exchange_rates")
                if not isinstance(exchange_rates, list):
                    raise ValueError("exchange_ratesの形式が正しくありません。")
                updated_entry = {
                    "exchange_rate_effective_date": effective_date.isoformat(),
                    "jpy_per_usd": format(rate, "f"),
                    "source": "管理画面で入力",
                }
                replaced = False
                updated_rates: list[object] = []
                for item in exchange_rates:
                    if (
                        isinstance(item, dict)
                        and item.get("exchange_rate_effective_date") == effective_date.isoformat()
                    ):
                        if not replaced:
                            updated_rates.append(updated_entry)
                            replaced = True
                        continue
                    updated_rates.append(item)
                if not replaced:
                    updated_rates.append(updated_entry)
                raw["exchange_rates"] = updated_rates

                # Validate the complete candidate while leaving prices and tiers untouched.
                candidate = UsagePricingConfig.model_validate(raw)
                content = (
                    json.dumps(raw, ensure_ascii=False, indent=2) + "\n"
                ).encode("utf-8")
                temporary = self.config_path.parent / f".{self.config_path.name}.{uuid.uuid4().hex}.tmp"
                with temporary.open("xb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.config_path)
                temporary = None
                return candidate, hashlib.sha256(content).hexdigest()
            except PricingConfigurationConflict:
                raise
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                raise PricingConfigurationError(
                    f"為替レート設定を保存できません: {self.config_path} ({exc})"
                ) from None
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass

    def calculate(self, usage: APIUsageRecord, *, pricing_date: date | None = None) -> PricingResult:
        usage = APIUsageRecord.model_validate(usage)
        config = self.config
        applied_date = pricing_date or usage.created_at.date()
        base = {
            "usage_id": usage.usage_id,
            "model": usage.model,
            "prompt_token_count": usage.prompt_token_count,
            "candidates_token_count": usage.candidates_token_count,
            "thoughts_token_count": usage.thoughts_token_count,
            "cached_content_token_count": usage.cached_content_token_count,
        }
        if usage.prompt_token_count is None or usage.candidates_token_count is None:
            return PricingResult(**base, pricing_status="unavailable", pricing_error_reason="prompt_token_countまたはcandidates_token_countがnullです")
        if usage.traffic_type is None or not usage.traffic_type.strip():
            return PricingResult(**base, pricing_status="unavailable", pricing_error_reason="traffic_typeが未設定です")

        rule = self._select_rule(config, usage.model, usage.traffic_type, applied_date)
        if rule is None:
            known = any(item.matches_model(usage.model) for item in config.prices)
            reason = (
                f"traffic_type={usage.traffic_type}の単価が未設定です"
                if known else f"モデル={usage.model}の単価が未設定です"
            )
            return PricingResult(**base, pricing_status="unavailable", pricing_error_reason=reason)

        cached_tokens = usage.cached_content_token_count or 0
        thought_tokens = usage.thoughts_token_count or 0
        if cached_tokens > usage.prompt_token_count:
            return PricingResult(**base, pricing_status="unavailable", pricing_error_reason="cached_content_token_countがprompt_token_countを超えています", pricing_effective_date=rule.pricing_effective_date)

        unsupported = self._unsupported_modalities(usage, rule)
        if unsupported:
            return PricingResult(**base, pricing_status="unavailable", pricing_error_reason=f"入力モダリティの単価が未設定です: {', '.join(unsupported)}", pricing_effective_date=rule.pricing_effective_date)

        tier = next(item for item in rule.tiers if item.max_input_tokens is None or usage.prompt_token_count <= item.max_input_tokens)
        required = {"入力": tier.input_usd_per_million_tokens, "出力": tier.output_usd_per_million_tokens}
        if thought_tokens:
            required["思考"] = tier.thoughts_usd_per_million_tokens
        if cached_tokens:
            required["キャッシュ入力"] = tier.cached_input_usd_per_million_tokens
        missing = [name for name, price in required.items() if price is None]
        if missing:
            return PricingResult(
                **base,
                pricing_status="unavailable",
                pricing_error_reason=f"単価が未設定です: {', '.join(missing)}",
                pricing_effective_date=rule.pricing_effective_date,
                pricing_snapshot=self._snapshot(rule, tier, None),
            )

        input_cost = self._cost(usage.prompt_token_count - cached_tokens, tier.input_usd_per_million_tokens)
        output_cost = self._cost(usage.candidates_token_count, tier.output_usd_per_million_tokens)
        output_cost += self._cost(thought_tokens, tier.thoughts_usd_per_million_tokens)
        cache_cost = self._cost(cached_tokens, tier.cached_input_usd_per_million_tokens)
        total_usd = input_cost + output_cost + cache_cost
        exchange_rate = self._select_exchange_rate(config, applied_date)
        snapshot = self._snapshot(rule, tier, exchange_rate)
        if exchange_rate is None or exchange_rate.jpy_per_usd is None:
            return PricingResult(
                **base,
                pricing_status="partial",
                pricing_error_reason="為替レートが未設定です",
                input_cost_usd=input_cost,
                output_cost_usd=output_cost,
                cache_cost_usd=cache_cost,
                total_cost_usd=total_usd,
                pricing_effective_date=rule.pricing_effective_date,
                pricing_snapshot=snapshot,
            )
        return PricingResult(
            **base,
            pricing_status="estimated",
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            cache_cost_usd=cache_cost,
            total_cost_usd=total_usd,
            exchange_rate_jpy_per_usd=exchange_rate.jpy_per_usd,
            exchange_rate_effective_date=exchange_rate.exchange_rate_effective_date,
            total_cost_jpy=total_usd * exchange_rate.jpy_per_usd,
            pricing_effective_date=rule.pricing_effective_date,
            pricing_snapshot=snapshot,
        )

    @staticmethod
    def _select_rule(config: UsagePricingConfig, model: str, traffic_type: str, applied_date: date) -> ModelPricingRule | None:
        candidates = [
            rule for rule in config.prices
            if rule.matches_model(model)
            and rule.traffic_type == traffic_type
            and rule.pricing_effective_date <= applied_date
        ]
        return max(candidates, key=lambda item: item.pricing_effective_date, default=None)

    @staticmethod
    def _select_exchange_rate(config: UsagePricingConfig, applied_date: date) -> ExchangeRate | None:
        candidates = [rate for rate in config.exchange_rates if rate.exchange_rate_effective_date <= applied_date]
        return max(candidates, key=lambda item: item.exchange_rate_effective_date, default=None)

    @staticmethod
    def _unsupported_modalities(usage: APIUsageRecord, rule: ModelPricingRule) -> list[str]:
        actual = {
            str(item.get("modality", "")).strip().upper()
            for item in (usage.prompt_tokens_details or [])
            if isinstance(item, dict) and item.get("modality")
        }
        return sorted(actual - set(rule.accepted_input_modalities))

    @staticmethod
    def _cost(tokens: int, price: Decimal | None) -> Decimal:
        if tokens == 0:
            return Decimal("0")
        assert price is not None
        return Decimal(tokens) * price / MILLION

    @staticmethod
    def _snapshot(rule: ModelPricingRule, tier: PricingTier, rate: ExchangeRate | None) -> dict[str, Any]:
        return {
            "model": rule.model,
            "aliases": list(rule.aliases),
            "traffic_type": rule.traffic_type,
            "pricing_effective_date": rule.pricing_effective_date.isoformat(),
            "tier_max_input_tokens": tier.max_input_tokens,
            "input_usd_per_million_tokens": tier.input_usd_per_million_tokens,
            "output_usd_per_million_tokens": tier.output_usd_per_million_tokens,
            "thoughts_usd_per_million_tokens": tier.thoughts_usd_per_million_tokens,
            "cached_input_usd_per_million_tokens": tier.cached_input_usd_per_million_tokens,
            "pricing_source_url": rule.source_url,
            "exchange_rate_effective_date": rate.exchange_rate_effective_date.isoformat() if rate else None,
            "exchange_rate_jpy_per_usd": rate.jpy_per_usd if rate else None,
            "exchange_rate_source": rate.source if rate else None,
            "calculated_at": datetime.now().astimezone().isoformat(),
            "estimation_notice": "Google Cloud公式単価に基づく推定値であり、実請求額とは一致しない場合があります",
        }


pricing_service = PricingService()
