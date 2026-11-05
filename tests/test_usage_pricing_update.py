from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from backend.app.api.v1.usage import _require_loopback_client, update_usage_exchange_rate
from backend.app.repositories.usage_repository import build_usage_record
from backend.app.schemas.usage import ExchangeRateUpdateRequest
from backend.app.services.pricing_service import (
    PricingConfigurationConflict,
    PricingConfigurationError,
    PricingService,
    load_pricing_config,
)
from backend.app.services.usage_service import UsageService


def config() -> dict:
    return {
        "schema_version": 1,
        "prices": [{
            "model": "model-a",
            "aliases": [],
            "pricing_effective_date": "2025-01-01",
            "traffic_type": "ON_DEMAND",
            "accepted_input_modalities": ["TEXT"],
            "tiers": [{
                "max_input_tokens": None,
                "input_usd_per_million_tokens": "1",
                "output_usd_per_million_tokens": "2",
                "thoughts_usd_per_million_tokens": "2",
                "cached_input_usd_per_million_tokens": "0.1",
            }],
        }],
        "exchange_rates": [{
            "exchange_rate_effective_date": "2025-01-01",
            "jpy_per_usd": "100",
            "source": "test",
        }],
    }


class UsagePricingUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "settings" / "usage_pricing.json"
        self.path.parent.mkdir()
        self.path.write_text(json.dumps(config(), ensure_ascii=False, indent=2), encoding="utf-8")
        self.service = PricingService(config_path=self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_decimal_input_rejects_blank_zero_negative_and_invalid(self):
        revision = self.service.config_revision()
        for value in ("", "0", "-1", "abc"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ExchangeRateUpdateRequest.model_validate({
                    "jpy_per_usd": value,
                    "expected_revision": revision,
                })

    def test_save_reload_and_prices_remain_unchanged(self):
        before = json.loads(self.path.read_text(encoding="utf-8"))
        _, revision = self.service.update_exchange_rate(
            jpy_per_usd=Decimal("151.25"),
            effective_date=date(2025, 2, 1),
            expected_revision=self.service.config_revision(),
        )
        after = json.loads(self.path.read_text(encoding="utf-8"))
        reloaded = load_pricing_config(self.path)
        self.assertEqual(after["prices"], before["prices"])
        self.assertEqual(reloaded.exchange_rates[-1].jpy_per_usd, Decimal("151.25"))
        self.assertEqual(reloaded.exchange_rates[-1].exchange_rate_effective_date, date(2025, 2, 1))
        self.assertEqual(revision, self.service.config_revision())

    def test_jpy_recalculates_without_changing_usd(self):
        usage = build_usage_record(
            request_id="11111111-1111-4111-8111-111111111111",
            created_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            model="model-a",
            status="success",
            usage_metadata={
                "trafficType": "ON_DEMAND",
                "promptTokenCount": 10,
                "candidatesTokenCount": 20,
            },
        )
        before = self.service.calculate(usage)
        self.service.update_exchange_rate(
            jpy_per_usd=Decimal("150"),
            effective_date=date(2025, 1, 1),
            expected_revision=self.service.config_revision(),
        )
        after = self.service.calculate(usage)
        self.assertEqual(after.total_cost_usd, before.total_cost_usd)
        self.assertEqual(after.total_cost_jpy, before.total_cost_jpy * Decimal("1.5"))

    def test_failed_atomic_replace_keeps_existing_file(self):
        before = self.path.read_bytes()
        with patch("backend.app.services.pricing_service.os.replace", side_effect=OSError("denied")):
            with self.assertRaises(PricingConfigurationError):
                self.service.update_exchange_rate(
                    jpy_per_usd=Decimal("150"),
                    effective_date=date(2025, 2, 1),
                    expected_revision=self.service.config_revision(),
                )
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_concurrent_update_is_detected(self):
        stale_revision = self.service.config_revision()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        raw["exchange_rates"][0]["source"] = "other updater"
        self.path.write_text(json.dumps(raw), encoding="utf-8")
        before = self.path.read_bytes()
        with self.assertRaises(PricingConfigurationConflict):
            self.service.update_exchange_rate(
                jpy_per_usd=Decimal("150"),
                effective_date=date(2025, 2, 1),
                expected_revision=stale_revision,
            )
        self.assertEqual(self.path.read_bytes(), before)

    def test_in_progress_cross_process_update_is_detected(self):
        lock = self.path.parent / f".{self.path.name}.update.lock"
        lock.write_text("other process", encoding="utf-8")
        before = self.path.read_bytes()
        try:
            with self.assertRaises(PricingConfigurationConflict):
                self.service.update_exchange_rate(
                    jpy_per_usd=Decimal("150"),
                    effective_date=date(2025, 2, 1),
                    expected_revision=self.service.config_revision(),
                )
        finally:
            lock.unlink(missing_ok=True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_update_rejects_non_loopback_client_even_with_local_host_header(self):
        scope = {
            "type": "http",
            "method": "PUT",
            "path": "/api/v1/usage/pricing-settings/exchange-rate",
            "headers": [(b"host", b"127.0.0.1")],
            "client": ("192.0.2.10", 50000),
            "server": ("127.0.0.1", 8000),
            "scheme": "http",
            "query_string": b"",
        }
        with self.assertRaises(HTTPException) as raised:
            _require_loopback_client(Request(scope))
        self.assertEqual(raised.exception.status_code, 403)

    def test_local_update_api_saves_and_returns_new_revision(self):
        local_service = UsageService(root=Path(self.temp.name), pricing_service=self.service)
        old_revision = self.service.config_revision()
        request = Request({
            "type": "http",
            "method": "PUT",
            "path": "/api/v1/usage/pricing-settings/exchange-rate",
            "headers": [(b"host", b"testserver")],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        })
        payload = ExchangeRateUpdateRequest(
            jpy_per_usd=Decimal("152.75"), expected_revision=old_revision
        )
        with patch("backend.app.api.v1.usage.usage_service", local_service):
            response = update_usage_exchange_rate(payload, request)
        self.assertNotEqual(response.revision, old_revision)
        self.assertEqual(load_pricing_config(self.path).exchange_rates[-1].jpy_per_usd, Decimal("152.75"))


if __name__ == "__main__":
    unittest.main()
