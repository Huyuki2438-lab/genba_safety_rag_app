from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field

class TokenAggregate(BaseModel):
    known_total: int | None = None
    known_count: int = 0
    unknown_count: int = 0

class UsageCostAggregate(BaseModel):
    call_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    pricing_unavailable_count: int = 0
    jpy_unavailable_count: int = 0
    input_tokens: TokenAggregate
    output_tokens: TokenAggregate
    thoughts_tokens: TokenAggregate
    cached_tokens: TokenAggregate
    total_tokens: TokenAggregate
    estimated_cost_usd_subtotal: Decimal | None = None
    estimated_cost_usd_total: Decimal | None = None
    estimated_cost_jpy_subtotal: Decimal | None = None
    estimated_cost_jpy_total: Decimal | None = None
    average_cost_usd_known: Decimal | None = None
    average_cost_jpy_known: Decimal | None = None
    pricing_complete: bool = False
    jpy_pricing_complete: bool = False

class UsageBreakdown(UsageCostAggregate):
    key: str
    label: str

class UsageDetail(BaseModel):
    usage_id: str
    request_id: str
    created_at: datetime
    model: str
    analysis_status: str
    construction_id: str | None = None
    construction_name: str = "工事未特定"
    prompt_token_count: int | None = None
    candidates_token_count: int | None = None
    thoughts_token_count: int | None = None
    cached_content_token_count: int | None = None
    total_token_count: int | None = None
    estimated_cost_usd: Decimal | None = None
    estimated_cost_jpy: Decimal | None = None
    exchange_rate_jpy_per_usd: Decimal | None = None
    exchange_rate_effective_date: date | None = None
    pricing_status: Literal["estimated", "partial", "unavailable"]
    pricing_error_reason: str | None = None

class UsageReadIssue(BaseModel):
    month: str
    kind: Literal["corrupt_json", "read_failure", "duplicate"]
    file_name: str | None = None
    message: str

class UsageQueryResponse(BaseModel):
    date_from: date
    date_to: date
    summary: UsageCostAggregate
    monthly: list[UsageBreakdown]
    by_model: list[UsageBreakdown]
    by_construction: list[UsageBreakdown]
    details: list[UsageDetail]
    page: int
    page_size: int
    total_items: int
    total_pages: int
    corrupt_json_count: int = 0
    read_failure_count: int = 0
    duplicate_count: int = 0
    aggregation_complete: bool = True
    issues: list[UsageReadIssue] = Field(default_factory=list)

class ExchangeRateSetting(BaseModel):
    exchange_rate_effective_date: date
    jpy_per_usd: Decimal | None = None
    source: str | None = None

class UsagePricingSettingsResponse(BaseModel):
    schema_version: int | None = None
    exchange_rates: list[ExchangeRateSetting] = Field(default_factory=list)
    revision: str | None = None
    valid: bool
    editable: bool = True
    error: str | None = None


class ExchangeRateUpdateRequest(BaseModel):
    jpy_per_usd: Decimal = Field(gt=0, allow_inf_nan=False)
    expected_revision: str = Field(min_length=64, max_length=64, pattern="^[0-9a-f]{64}$")
