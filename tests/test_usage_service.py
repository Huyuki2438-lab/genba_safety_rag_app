from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from backend.app.repositories.usage_repository import UsageRepository, build_usage_record
from backend.app.services.pricing_service import PricingService, UsagePricingConfig
from backend.app.services.usage_service import UsageService


def config(*, exchange: str | None = "150") -> dict:
    return {
        "schema_version": 1,
        "prices": [{
            "model": "model-a", "aliases": ["model-b"],
            "pricing_effective_date": "2025-01-01", "traffic_type": "ON_DEMAND",
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
            "jpy_per_usd": exchange, "source": "test",
        }],
    }


class UsageServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        pricing_path = self.root / "settings" / "usage_pricing.json"
        pricing_path.parent.mkdir()
        pricing_path.write_text(json.dumps(config()), encoding="utf-8")
        self.repo = UsageRepository(root=self.root, project_id="project-1")
        self.repo.initialize_schema()
        self.service = UsageService(
            root=self.root, pricing_service=PricingService(config_path=pricing_path)
        )

    def tearDown(self):
        self.temp.cleanup()

    def add(
        self, when: datetime, *, model="model-a", status="success",
        prompt=10, candidates=20, thoughts=5, total=35, cached=0,
    ):
        metadata = {"trafficType": "ON_DEMAND"}
        for key, value in {
            "promptTokenCount": prompt, "candidatesTokenCount": candidates,
            "thoughtsTokenCount": thoughts, "totalTokenCount": total,
            "cachedContentTokenCount": cached,
        }.items():
            if value is not None:
                metadata[key] = value
        record = build_usage_record(
            request_id=str(uuid4()), created_at=when, model=model,
            status=status, usage_metadata=metadata,
        )
        self.repo.add(record)
        return record

    def query(self, start=date(2025, 1, 1), end=date(2025, 3, 31), **kwargs):
        return self.service.query(date_from=start, date_to=end, **kwargs)

    def test_normal_price_and_token_aggregation(self):
        self.add(datetime(2025, 1, 2, tzinfo=timezone.utc))
        result = self.query()
        self.assertEqual(result.summary.call_count, 1)
        self.assertEqual(result.summary.input_tokens.known_total, 10)
        self.assertTrue(result.summary.pricing_complete)
        self.assertIsNotNone(result.summary.estimated_cost_jpy_total)

    def test_multiple_months_and_month_breakdown(self):
        self.add(datetime(2025, 1, 31, tzinfo=timezone.utc))
        self.add(datetime(2025, 2, 1, tzinfo=timezone.utc))
        result = self.query()
        self.assertEqual(result.summary.call_count, 2)
        self.assertEqual([row.key for row in result.monthly], ["2025-01", "2025-02"])

    def test_model_breakdown(self):
        self.add(datetime(2025, 1, 2, tzinfo=timezone.utc), model="model-a")
        self.add(datetime(2025, 1, 3, tzinfo=timezone.utc), model="model-b")
        self.assertEqual({row.key for row in self.query().by_model}, {"model-a", "model-b"})

    def test_construction_is_linked_only_by_request_id(self):
        usage = self.add(datetime(2025, 1, 2, tzinfo=timezone.utc))
        folder = self.root / "records" / "2025-01"
        folder.mkdir(parents=True)
        now = datetime(2025, 1, 2, tzinfo=timezone.utc).isoformat()
        analysis = {
            "id": usage.request_id, "created_at": now, "updated_at": now,
            "created_by": "tester", "site_name": "工事A", "work_content": "",
            "main_risk": "", "image_name": "x.jpg",
            "photo_relative_path": "2025/01/x.jpg", "mode": "vertex",
            "provider_display_label": "AI", "model": "model-a", "markdown": "x",
        }
        (folder / f"{usage.request_id}.json").write_text(json.dumps({
            "schema_version": 1, "record_id": usage.request_id,
            "project_id": "project-1", "analysis": analysis,
        }), encoding="utf-8")
        result = self.query()
        self.assertEqual(result.details[0].construction_name, "工事A")
        self.assertEqual(result.by_construction[0].key, "工事A")

    def test_unavailable_price_is_not_zero(self):
        self.add(datetime(2025, 1, 2, tzinfo=timezone.utc), prompt=None)
        summary = self.query().summary
        self.assertIsNone(summary.estimated_cost_usd_total)
        self.assertEqual(summary.pricing_unavailable_count, 1)

    def test_missing_exchange_keeps_usd_and_unsets_jpy(self):
        path = self.root / "settings" / "usage_pricing.json"
        path.write_text(json.dumps(config(exchange=None)), encoding="utf-8")
        self.add(datetime(2025, 1, 2, tzinfo=timezone.utc))
        summary = self.query().summary
        self.assertIsNotNone(summary.estimated_cost_usd_total)
        self.assertIsNone(summary.estimated_cost_jpy_total)
        self.assertEqual(summary.jpy_unavailable_count, 1)

    def test_missing_pricing_keeps_ledger_visible_as_unpriced(self):
        path = self.root / "settings" / "usage_pricing.json"
        path.unlink()
        record = self.add(datetime(2025, 1, 2, tzinfo=timezone.utc))

        result = self.query()

        self.assertEqual(result.summary.call_count, 1)
        self.assertEqual(result.details[0].usage_id, record.usage_id)
        self.assertEqual(result.details[0].pricing_status, "unavailable")
        self.assertIsNone(result.details[0].estimated_cost_usd)
        self.assertFalse(path.exists())

    def test_corrupt_pricing_is_preserved_and_ledger_remains_visible(self):
        path = self.root / "settings" / "usage_pricing.json"
        path.write_text("{broken", encoding="utf-8")
        before = path.read_bytes()
        self.add(datetime(2025, 1, 2, tzinfo=timezone.utc))

        result = self.query()

        self.assertEqual(result.summary.call_count, 1)
        self.assertEqual(result.details[0].pricing_status, "unavailable")
        self.assertEqual(path.read_bytes(), before)

    def test_duplicate_usage_id_is_not_counted_twice(self):
        record = self.add(datetime(2025, 1, 2, tzinfo=timezone.utc))
        source = self.root / "usage" / "2025-01" / f"{record.usage_id}.json"
        shutil.copyfile(source, source.with_name("duplicate.json"))
        result = self.query()
        self.assertEqual(result.summary.call_count, 1)
        self.assertEqual(result.duplicate_count, 1)

    def test_empty_ledger(self):
        result = self.query()
        self.assertEqual(result.summary.call_count, 0)
        self.assertEqual(result.details, [])
        self.assertIsNone(result.summary.total_tokens.known_total)

    def test_corrupt_json_does_not_stop_aggregation(self):
        folder = self.root / "usage" / "2025-01"
        folder.mkdir(exist_ok=True)
        (folder / "broken.json").write_text("{", encoding="utf-8")
        result = self.query()
        self.assertEqual(result.corrupt_json_count, 1)
        self.assertFalse(result.aggregation_complete)

    def test_nas_month_read_failure_is_reported(self):
        self.add(datetime(2025, 1, 2, tzinfo=timezone.utc))
        with patch.object(self.service, "_month_files", side_effect=OSError("offline")):
            result = self.query(date(2025, 1, 1), date(2025, 1, 31))
        self.assertEqual(result.read_failure_count, 1)
        self.assertFalse(result.aggregation_complete)

    def test_pagination(self):
        for index in range(55):
            self.add(datetime(2025, 1, 2, tzinfo=timezone.utc) + timedelta(minutes=index))
        first = self.query(page=1, page_size=50)
        second = self.query(page=2, page_size=50)
        self.assertEqual((len(first.details), len(second.details)), (50, 5))
        self.assertEqual(first.total_pages, 2)

    def test_date_boundaries_use_jst(self):
        jst = timezone(timedelta(hours=9))
        self.add(datetime(2025, 2, 1, 0, 0, tzinfo=jst))
        self.add(datetime(2025, 2, 2, 0, 0, tzinfo=jst))
        result = self.query(date(2025, 2, 1), date(2025, 2, 1))
        self.assertEqual(result.summary.call_count, 1)

    def test_schema_v1_old_ledger_is_read_without_change(self):
        record = self.add(datetime(2025, 1, 2, tzinfo=timezone.utc))
        path = self.root / "usage" / "2025-01" / f"{record.usage_id}.json"
        before = path.read_bytes()
        self.query()
        self.assertEqual(path.read_bytes(), before)

    def test_exchange_validation_rejects_zero(self):
        raw = config(exchange="0")
        with self.assertRaises(ValueError):
            UsagePricingConfig.model_validate(raw)

    def test_success_and_failure_counts(self):
        self.add(datetime(2025, 1, 2, tzinfo=timezone.utc), status="success")
        self.add(datetime(2025, 1, 3, tzinfo=timezone.utc), status="http_error")
        summary = self.query().summary
        self.assertEqual((summary.success_count, summary.failure_count), (1, 1))


if __name__ == "__main__":
    unittest.main()
