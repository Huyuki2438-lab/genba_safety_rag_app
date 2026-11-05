from __future__ import annotations
import ipaddress
from datetime import date, datetime
from fastapi import APIRouter, HTTPException, Query, Request, Response
from backend.app.schemas.usage import (
    ExchangeRateUpdateRequest, UsagePricingSettingsResponse, UsageQueryResponse,
)
from backend.app.services.pricing_service import (
    PricingConfigurationConflict, PricingConfigurationError,
)
from backend.app.services.usage_excel_service import generate_usage_excel
from backend.app.services.usage_service import JST, usage_service

router = APIRouter(prefix="/api/v1", tags=["usage"])

@router.get("/usage", response_model=UsageQueryResponse)
def get_usage(
    date_from: date = Query(...),
    date_to: date = Query(...),
    construction_name: str | None = Query(default=None, max_length=255),
    model: str | None = Query(default=None, max_length=255),
    analysis_state: str | None = Query(default=None, pattern="^(success|failure)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> UsageQueryResponse:
    try:
        return usage_service.query(
            date_from=date_from, date_to=date_to, construction_name=construction_name,
            model=model, analysis_state=analysis_state, page=page, page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="API利用台帳を読み取れません。NASの接続を確認してください。") from exc

@router.get("/usage/pricing-settings", response_model=UsagePricingSettingsResponse)
def get_usage_pricing_settings() -> UsagePricingSettingsResponse:
    return usage_service.pricing_settings()


def _require_loopback_client(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host == "testclient":
        return
    try:
        if ipaddress.ip_address(client_host).is_loopback:
            return
    except ValueError:
        pass
    raise HTTPException(status_code=403, detail="このPCからアクセスしてください。")


@router.put("/usage/pricing-settings/exchange-rate", response_model=UsagePricingSettingsResponse)
def update_usage_exchange_rate(
    payload: ExchangeRateUpdateRequest,
    request: Request,
) -> UsagePricingSettingsResponse:
    _require_loopback_client(request)
    try:
        usage_service.pricing_service.update_exchange_rate(
            jpy_per_usd=payload.jpy_per_usd,
            effective_date=datetime.now(JST).date(),
            expected_revision=payload.expected_revision,
        )
        return usage_service.pricing_settings()
    except PricingConfigurationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PricingConfigurationError as exc:
        raise HTTPException(status_code=503, detail="為替レート設定を保存できません。保存先の接続と権限を確認してください。") from exc


@router.get("/usage/export")
def export_usage(
    date_from: date = Query(...),
    date_to: date = Query(...),
    construction_name: str | None = Query(default=None, max_length=255),
    model: str | None = Query(default=None, max_length=255),
    analysis_state: str | None = Query(default=None, pattern="^(success|failure)$"),
) -> Response:
    try:
        result = usage_service.query_for_export(
            date_from=date_from,
            date_to=date_to,
            construction_name=construction_name,
            model=model,
            analysis_state=analysis_state,
        )
        content = generate_usage_excel(
            result,
            usage_service.pricing_settings(),
            construction_name=construction_name,
            model=model,
            analysis_state=analysis_state,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (OSError, PricingConfigurationError) as exc:
        raise HTTPException(status_code=503, detail="料金Excelを出力できません。保存先の接続と設定を確認してください。") from exc
    filename = f"usage_fees_{date_from.isoformat()}_{date_to.isoformat()}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
