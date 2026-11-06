from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from backend.app.repositories.usage_repository import build_usage_record
from backend.app.services.pricing_service import (
    PricingConfigurationError,
    PricingService,
    UsagePricingConfig,
    load_pricing_config,
    load_usage_ledger,
    resolve_pricing_config_path,
)


def make_config(*, cache_price: str | None = "0.1") -> UsagePricingConfig:
    return UsagePricingConfig.model_validate({
        "schema_version": 1,
        "prices": [{
            "model": "test-model",
            "aliases": ["test-model-known-alias"],
            "pricing_effective_date": "2025-01-01",
            "traffic_type": "ON_DEMAND",
            "accepted_input_modalities": ["TEXT", "IMAGE"],
            "tiers": [
                {
                    "max_input_tokens": 100,
                    "input_usd_per_million_tokens": "1",
                    "output_usd_per_million_tokens": "2",
                    "thoughts_usd_per_million_tokens": "2",
                    "cached_input_usd_per_million_tokens": cache_price,
                },
                {
                    "max_input_tokens": None,
                    "input_usd_per_million_tokens": "3",
                    "output_usd_per_million_tokens": "4",
                    "thoughts_usd_per_million_tokens": "4",
                    "cached_input_usd_per_million_tokens": "0.3",
                },
            ],
        }],
        "exchange_rates": [
            {"exchange_rate_effective_date": "2025-01-01", "jpy_per_usd": "100"},
            {"exchange_rate_effective_date": "2025-03-01", "jpy_per_usd": "150"},
        ],
    })


def make_usage(
    *,
    prompt=10,
    candidates=20,
    thoughts=None,
    cached=None,
    model="test-model",
    traffic="ON_DEMAND",
    status="success",
    created_at=datetime(2025, 2, 1, tzinfo=timezone.utc),
):
    metadata = {}
    for key, value in {
        "promptTokenCount": prompt,
        "candidatesTokenCount": candidates,
        "thoughtsTokenCount": thoughts,
        "cachedContentTokenCount": cached,
        "trafficType": traffic,
    }.items():
        if value is not None:
            metadata[key] = value
    return build_usage_record(
        request_id=str(uuid4()),
        created_at=created_at,
        model=model,
        status=status,
        usage_metadata=metadata or None,
    )


class PricingServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = PricingService(config=make_config())

    def test_input_and_output_cost(self):
        result = self.service.calculate(make_usage())
        self.assertEqual(result.input_cost_usd, Decimal("0.00001"))
        self.assertEqual(result.output_cost_usd, Decimal("0.00004"))
        self.assertEqual(result.total_cost_usd, Decimal("0.00005"))
        self.assertEqual(result.total_cost_jpy, Decimal("0.00500"))

    def test_thought_tokens_use_output_side_price(self):
        result = self.service.calculate(make_usage(candidates=20, thoughts=5))
        self.assertEqual(result.output_cost_usd, Decimal("0.00005"))

    def test_cache_cost_and_no_double_count(self):
        result = self.service.calculate(make_usage(prompt=10, candidates=0, cached=4))
        self.assertEqual(result.input_cost_usd, Decimal("0.000006"))
        self.assertEqual(result.cache_cost_usd, Decimal("0.0000004"))
        self.assertEqual(result.total_cost_usd, Decimal("0.0000064"))

    def test_null_usage_is_not_zero_cost(self):
        result = self.service.calculate(make_usage(prompt=None, candidates=None))
        self.assertEqual(result.pricing_status, "unavailable")
        self.assertIsNone(result.total_cost_usd)
        self.assertIsNone(result.total_cost_jpy)

    def test_zero_tokens_are_zero_cost(self):
        result = self.service.calculate(make_usage(prompt=0, candidates=0))
        self.assertEqual(result.pricing_status, "estimated")
        self.assertEqual(result.total_cost_usd, Decimal("0"))
        self.assertEqual(result.total_cost_jpy, Decimal("0"))

    def test_unknown_model_does_not_fall_back(self):
        result = self.service.calculate(make_usage(model="test-model-unknown-suffix"))
        self.assertEqual(result.pricing_status, "unavailable")
        self.assertIn("モデル", result.pricing_error_reason)

    def test_explicit_alias_is_allowed(self):
        result = self.service.calculate(make_usage(model="test-model-known-alias"))
        self.assertEqual(result.pricing_status, "estimated")

    def test_unknown_or_missing_traffic_type_is_unavailable(self):
        unknown = self.service.calculate(make_usage(traffic="UNKNOWN"))
        missing = self.service.calculate(make_usage(traffic=None))
        self.assertIn("traffic_type", unknown.pricing_error_reason)
        self.assertIn("traffic_type", missing.pricing_error_reason)

    def test_missing_required_unit_price_is_unavailable(self):
        service = PricingService(config=make_config(cache_price=None))
        result = service.calculate(make_usage(cached=1))
        self.assertEqual(result.pricing_status, "unavailable")
        self.assertIn("キャッシュ入力", result.pricing_error_reason)

    def test_exchange_rate_changes_by_effective_date(self):
        old = self.service.calculate(make_usage(), pricing_date=date(2025, 2, 28))
        new = self.service.calculate(make_usage(), pricing_date=date(2025, 3, 1))
        self.assertEqual(old.exchange_rate_jpy_per_usd, Decimal("100"))
        self.assertEqual(new.exchange_rate_jpy_per_usd, Decimal("150"))
        self.assertEqual(new.total_cost_jpy, old.total_cost_jpy * Decimal("1.5"))

    def test_latest_applicable_price_effective_date_is_selected(self):
        data = make_config().model_dump(mode="json")
        newer = dict(data["prices"][0])
        newer["pricing_effective_date"] = "2025-02-15"
        newer["tiers"] = [dict(tier) for tier in newer["tiers"]]
        newer["tiers"][0]["input_usd_per_million_tokens"] = "9"
        data["prices"].append(newer)
        service = PricingService(config=UsagePricingConfig.model_validate(data))
        old = service.calculate(make_usage(), pricing_date=date(2025, 2, 14))
        new = service.calculate(make_usage(), pricing_date=date(2025, 2, 15))
        self.assertEqual(old.input_cost_usd, Decimal("0.00001"))
        self.assertEqual(new.input_cost_usd, Decimal("0.00009"))
        self.assertEqual(new.pricing_effective_date, date(2025, 2, 15))

    def test_tier_boundary_uses_all_tokens_at_selected_tier(self):
        at_boundary = self.service.calculate(make_usage(prompt=100, candidates=1))
        over_boundary = self.service.calculate(make_usage(prompt=101, candidates=1))
        self.assertEqual(at_boundary.input_cost_usd, Decimal("0.0001"))
        self.assertEqual(over_boundary.input_cost_usd, Decimal("0.000303"))
        self.assertEqual(over_boundary.output_cost_usd, Decimal("0.000004"))

    def test_decimal_precision(self):
        result = self.service.calculate(make_usage(prompt=1, candidates=0, cached=1))
        self.assertEqual(result.cache_cost_usd, Decimal("0.0000001"))
        self.assertEqual(str(result.total_cost_usd), "1E-7")

    def test_api_error_with_usage_is_still_priced(self):
        result = self.service.calculate(make_usage(status="http_error"))
        self.assertEqual(result.pricing_status, "estimated")

    def test_legacy_schema_v1_ledger_is_read_without_rewrite(self):
        record = make_usage()
        payload = {
            "schema_version": 1,
            "usage_id": record.usage_id,
            "request_id": record.request_id,
            "project_id": "legacy-project",
            "usage": record.model_dump(mode="json"),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "usage.json"
            original = json.dumps(payload, ensure_ascii=False, indent=2)
            path.write_text(original, encoding="utf-8")
            loaded = load_usage_ledger(path)
            result = self.service.calculate_ledger(path)
            self.assertEqual(loaded.usage_id, record.usage_id)
            self.assertEqual(result.pricing_status, "estimated")
            self.assertEqual(path.read_text(encoding="utf-8"), original)


class PricingConfigPathTests(unittest.TestCase):
    def test_app_wide_file_is_independent_of_project_switch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app_dir = root / "app"
            project_a = root / "project-a"
            project_b = root / "project-b"
            app_file = app_dir / "settings" / "usage_pricing.json"
            app_file.parent.mkdir(parents=True)
            app_file.write_text("{}", encoding="utf-8")

            self.assertEqual(resolve_pricing_config_path(app_dir, project_a), app_file)
            self.assertEqual(resolve_pricing_config_path(app_dir, project_b), app_file)

    def test_existing_site_local_file_is_legacy_fallback_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy = root / "project" / "settings" / "usage_pricing.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("legacy", encoding="utf-8")

            selected = resolve_pricing_config_path(root / "app", root / "project")

            self.assertEqual(selected, legacy)
            self.assertEqual(legacy.read_text(encoding="utf-8"), "legacy")

    def test_missing_files_return_app_path_without_creating_anything(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = root / "app" / "settings" / "usage_pricing.json"

            selected = resolve_pricing_config_path(root / "app", root / "project")

            self.assertEqual(selected, expected)
            self.assertFalse(expected.exists())
            with self.assertRaises(PricingConfigurationError):
                load_pricing_config(selected)

    def test_corrupt_app_file_is_not_hidden_or_overwritten_by_legacy_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app_file = root / "app" / "settings" / "usage_pricing.json"
            legacy = root / "project" / "settings" / "usage_pricing.json"
            app_file.parent.mkdir(parents=True)
            legacy.parent.mkdir(parents=True)
            app_file.write_text("{broken", encoding="utf-8")
            legacy.write_text("{}", encoding="utf-8")
            before = app_file.read_bytes()

            selected = resolve_pricing_config_path(root / "app", root / "project")

            self.assertEqual(selected, app_file)
            with self.assertRaises(PricingConfigurationError):
                load_pricing_config(selected)
            self.assertEqual(app_file.read_bytes(), before)
            self.assertTrue(legacy.exists())


class Gemini37FlashPricingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config_path = Path(__file__).resolve().parents[1] / "settings" / "usage_pricing.json"
        cls.config = load_pricing_config(config_path)
        cls.service = PricingService(config=cls.config)

    def test_existing_gemini_25_flash_pricing_is_retained(self):
        self.assertTrue(any(rule.model == "gemini-2.5-flash" for rule in self.config.prices))

    def test_gemini_37_flash_price_switches_on_2027_01_01(self):
        usage = make_usage(
            prompt=2_000_000,
            candidates=1_000_000,
            thoughts=1_000_000,
            cached=1_000_000,
            model="gemini-3.7-flash",
            created_at=datetime(2026, 12, 31, tzinfo=timezone.utc),
        )

        through_2026 = self.service.calculate(usage, pricing_date=date(2026, 12, 31))
        from_2027 = self.service.calculate(usage, pricing_date=date(2027, 1, 1))

        self.assertEqual(through_2026.pricing_effective_date, date(2026, 8, 13))
        self.assertEqual(through_2026.input_cost_usd, Decimal("0.75"))
        self.assertEqual(through_2026.output_cost_usd, Decimal("7.50"))
        self.assertEqual(through_2026.cache_cost_usd, Decimal("0.075"))
        self.assertEqual(through_2026.total_cost_usd, Decimal("8.325"))
        self.assertEqual(
            through_2026.pricing_snapshot["cached_input_usd_per_million_tokens"],
            Decimal("0.075"),
        )

        self.assertEqual(from_2027.pricing_effective_date, date(2027, 1, 1))
        self.assertEqual(from_2027.input_cost_usd, Decimal("1.50"))
        self.assertEqual(from_2027.output_cost_usd, Decimal("15.00"))
        self.assertEqual(from_2027.cache_cost_usd, Decimal("0.15"))
        self.assertEqual(from_2027.total_cost_usd, Decimal("16.65"))
        self.assertEqual(
            from_2027.pricing_snapshot["cached_input_usd_per_million_tokens"],
            Decimal("0.15"),
        )


if __name__ == "__main__":
    unittest.main()
