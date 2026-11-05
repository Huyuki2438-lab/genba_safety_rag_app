from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from backend.app.core.config import settings
from backend.app.repositories.history_repository import AnalysisHistoryRecord
from backend.app.repositories.usage_repository import APIUsageRecord
from backend.app.schemas.usage import (
    ExchangeRateSetting, TokenAggregate, UsageBreakdown, UsageCostAggregate,
    UsageDetail, UsagePricingSettingsResponse, UsageQueryResponse, UsageReadIssue,
)
from backend.app.services.pricing_service import (
    PricingConfigurationError, PricingService, load_pricing_config,
)

try:
    JST = ZoneInfo("Asia/Tokyo")
except Exception:  # pragma: no cover
    JST = timezone(timedelta(hours=9), name="Asia/Tokyo")


class UsageService:
    def __init__(self, root: Path | None = None, pricing_service: PricingService | None = None):
        self.root = root or settings.DATA_DIR
        self.pricing_service = pricing_service or PricingService()

    def query(
        self, *, date_from: date, date_to: date,
        construction_name: str | None = None, model: str | None = None,
        analysis_state: str | None = None, page: int = 1, page_size: int = 50,
    ) -> UsageQueryResponse:
        if date_to < date_from:
            raise ValueError("終了日は開始日以降を指定してください。")
        start = datetime.combine(date_from, time.min, tzinfo=JST)
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=JST)
        records: list[UsageDetail] = []
        issues: list[UsageReadIssue] = []
        seen: set[str] = set()
        duplicates = corrupt = read_failures = 0

        for month in self._months(date_from, date_to):
            try:
                paths = self._month_files(month)
            except OSError:
                read_failures += 1
                issues.append(UsageReadIssue(
                    month=month, kind="read_failure",
                    message="月別台帳フォルダを読み取れませんでした。",
                ))
                continue
            for path in paths:
                try:
                    usage, project_id = self._read_record(path)
                except OSError:
                    read_failures += 1
                    issues.append(UsageReadIssue(
                        month=month, kind="read_failure", file_name=path.name,
                        message="台帳ファイルを読み取れませんでした。",
                    ))
                    continue
                except (ValueError, KeyError, TypeError, ValidationError):
                    corrupt += 1
                    issues.append(UsageReadIssue(
                        month=month, kind="corrupt_json", file_name=path.name,
                        message="台帳JSONの形式が不正です。",
                    ))
                    continue

                if usage.usage_id in seen:
                    duplicates += 1
                    issues.append(UsageReadIssue(
                        month=month, kind="duplicate", file_name=path.name,
                        message=f"usage_id={usage.usage_id} は既に集計済みです。",
                    ))
                    continue
                seen.add(usage.usage_id)
                created_jst = usage.created_at.astimezone(JST)
                if not start <= created_jst < end:
                    continue

                construction = (
                    self._construction_name(usage, created_jst) if project_id else "工事未特定"
                )
                try:
                    pricing = self.pricing_service.calculate_ledger(path)
                    pricing_status = pricing.pricing_status
                    pricing_reason = pricing.pricing_error_reason
                    usd, jpy = pricing.total_cost_usd, pricing.total_cost_jpy
                except PricingConfigurationError as exc:
                    pricing_status, pricing_reason = "unavailable", str(exc)
                    usd = jpy = None
                    exchange_rate = exchange_rate_date = None
                else:
                    exchange_rate = pricing.exchange_rate_jpy_per_usd
                    exchange_rate_date = pricing.exchange_rate_effective_date
                item = UsageDetail(
                    usage_id=usage.usage_id, request_id=usage.request_id,
                    created_at=usage.created_at, model=usage.model,
                    analysis_status=usage.status, construction_id=project_id or None,
                    construction_name=construction,
                    prompt_token_count=usage.prompt_token_count,
                    candidates_token_count=usage.candidates_token_count,
                    thoughts_token_count=usage.thoughts_token_count,
                    cached_content_token_count=usage.cached_content_token_count,
                    total_token_count=usage.total_token_count,
                    estimated_cost_usd=usd, estimated_cost_jpy=jpy,
                    exchange_rate_jpy_per_usd=exchange_rate,
                    exchange_rate_effective_date=exchange_rate_date,
                    pricing_status=pricing_status, pricing_error_reason=pricing_reason,
                )
                if construction_name and construction_name.casefold() not in construction.casefold():
                    continue
                if model and model != usage.model:
                    continue
                if analysis_state == "success" and usage.status != "success":
                    continue
                if analysis_state == "failure" and usage.status == "success":
                    continue
                records.append(item)

        records.sort(key=lambda item: (item.created_at, item.usage_id), reverse=True)
        complete = corrupt == 0 and read_failures == 0
        total_items = len(records)
        offset = (page - 1) * page_size
        return UsageQueryResponse(
            date_from=date_from, date_to=date_to,
            summary=self._aggregate(records, integrity_complete=complete),
            monthly=self._breakdowns(
                records, lambda item: item.created_at.astimezone(JST).strftime("%Y-%m")
            ),
            by_model=self._breakdowns(records, lambda item: item.model),
            by_construction=self._breakdowns(records, lambda item: item.construction_name),
            details=records[offset:offset + page_size],
            page=page, page_size=page_size, total_items=total_items,
            total_pages=math.ceil(total_items / page_size) if total_items else 0,
            corrupt_json_count=corrupt, read_failure_count=read_failures,
            duplicate_count=duplicates, aggregation_complete=complete,
            issues=issues[:100],
        )

    def query_for_export(
        self, *, date_from: date, date_to: date,
        construction_name: str | None = None, model: str | None = None,
        analysis_state: str | None = None,
    ) -> UsageQueryResponse:
        """Return every matching detail while keeping screen aggregation logic shared."""
        return self.query(
            date_from=date_from,
            date_to=date_to,
            construction_name=construction_name,
            model=model,
            analysis_state=analysis_state,
            page=1,
            page_size=2_147_483_647,
        )

    def pricing_settings(self) -> UsagePricingSettingsResponse:
        try:
            config = load_pricing_config(self.pricing_service.config_path)
            return UsagePricingSettingsResponse(
                schema_version=config.schema_version, valid=True,
                revision=self.pricing_service.config_revision(),
                exchange_rates=[
                    ExchangeRateSetting(
                        exchange_rate_effective_date=item.exchange_rate_effective_date,
                        jpy_per_usd=item.jpy_per_usd, source=item.source,
                    )
                    for item in config.exchange_rates
                ],
            )
        except PricingConfigurationError as exc:
            return UsagePricingSettingsResponse(valid=False, error=str(exc))

    def _month_files(self, month: str) -> list[Path]:
        folder = self.root / "usage" / month
        try:
            with os.scandir(folder) as entries:
                return sorted(
                    (
                        Path(entry.path) for entry in entries
                        if entry.is_file(follow_symlinks=False)
                        and entry.name.lower().endswith(".json")
                    ),
                    key=lambda path: path.name,
                )
        except FileNotFoundError:
            return []

    @staticmethod
    def _read_record(path: Path) -> tuple[APIUsageRecord, str]:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        if raw.get("schema_version") != 1:
            raise ValueError("unsupported schema_version")
        usage = APIUsageRecord.model_validate(raw["usage"])
        if raw.get("usage_id") != usage.usage_id or raw.get("request_id") != usage.request_id:
            raise ValueError("ledger identifiers do not match")
        project_id = raw.get("project_id")
        return usage, project_id if isinstance(project_id, str) else ""

    def _construction_name(self, usage: APIUsageRecord, created_jst: datetime) -> str:
        # record_id=request_id is the only supported association. Checking the
        # usage month and next month covers normal saves and month-end rollover
        # without scanning all history files on the NAS.
        for month in self._history_candidate_months(created_jst.date()):
            path = self.root / "records" / month / f"{usage.request_id}.json"
            try:
                raw = json.loads(path.read_text(encoding="utf-8-sig"))
                if raw.get("schema_version") != 1 or raw.get("record_id") != usage.request_id:
                    continue
                record = AnalysisHistoryRecord.model_validate(raw["analysis"])
                if record.id == usage.request_id:
                    return record.site_name.strip() or "工事未特定"
            except (FileNotFoundError, OSError, ValueError, KeyError, TypeError, ValidationError):
                continue
        return "工事未特定"

    @staticmethod
    def _history_candidate_months(value: date) -> list[str]:
        first = value.replace(day=1)
        following = (first + timedelta(days=32)).replace(day=1)
        return [first.strftime("%Y-%m"), following.strftime("%Y-%m")]

    @staticmethod
    def _months(date_from: date, date_to: date) -> Iterable[str]:
        current, last = date_from.replace(day=1), date_to.replace(day=1)
        while current <= last:
            yield current.strftime("%Y-%m")
            current = (current + timedelta(days=32)).replace(day=1)

    @classmethod
    def _aggregate(
        cls, records: list[UsageDetail], *, integrity_complete: bool = True,
    ) -> UsageCostAggregate:
        usd = [item.estimated_cost_usd for item in records if item.estimated_cost_usd is not None]
        jpy = [item.estimated_cost_jpy for item in records if item.estimated_cost_jpy is not None]
        usd_subtotal = sum(usd, Decimal("0")) if usd else None
        jpy_subtotal = sum(jpy, Decimal("0")) if jpy else None
        usd_complete = len(usd) == len(records) and integrity_complete
        jpy_complete = len(jpy) == len(records) and integrity_complete
        return UsageCostAggregate(
            call_count=len(records),
            success_count=sum(item.analysis_status == "success" for item in records),
            failure_count=sum(item.analysis_status != "success" for item in records),
            pricing_unavailable_count=sum(item.estimated_cost_usd is None for item in records),
            jpy_unavailable_count=sum(item.estimated_cost_jpy is None for item in records),
            input_tokens=cls._tokens(item.prompt_token_count for item in records),
            output_tokens=cls._tokens(item.candidates_token_count for item in records),
            thoughts_tokens=cls._tokens(item.thoughts_token_count for item in records),
            cached_tokens=cls._tokens(item.cached_content_token_count for item in records),
            total_tokens=cls._tokens(item.total_token_count for item in records),
            estimated_cost_usd_subtotal=usd_subtotal,
            estimated_cost_usd_total=usd_subtotal if usd_complete else None,
            estimated_cost_jpy_subtotal=jpy_subtotal,
            estimated_cost_jpy_total=jpy_subtotal if jpy_complete else None,
            average_cost_usd_known=usd_subtotal / len(usd) if usd else None,
            average_cost_jpy_known=jpy_subtotal / len(jpy) if jpy else None,
            pricing_complete=usd_complete, jpy_pricing_complete=jpy_complete,
        )

    @staticmethod
    def _tokens(values: Iterable[int | None]) -> TokenAggregate:
        values = list(values)
        known = [value for value in values if value is not None]
        return TokenAggregate(
            known_total=sum(known) if known else None,
            known_count=len(known), unknown_count=len(values) - len(known),
        )

    @classmethod
    def _breakdowns(cls, records: list[UsageDetail], key_function) -> list[UsageBreakdown]:
        groups: dict[str, list[UsageDetail]] = defaultdict(list)
        for item in records:
            groups[key_function(item)].append(item)
        result = []
        for key, items in groups.items():
            result.append(UsageBreakdown(
                key=key, label=key, **cls._aggregate(items).model_dump()
            ))
        return sorted(result, key=lambda item: item.key)


usage_service = UsageService()
