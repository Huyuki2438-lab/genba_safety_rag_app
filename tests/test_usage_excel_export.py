from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from openpyxl import load_workbook

from backend.app.repositories.usage_repository import UsageRepository, build_usage_record
from backend.app.services.pricing_service import PricingService
from backend.app.services.usage_excel_service import generate_usage_excel
from backend.app.services.usage_service import UsageService


def pricing_config() -> dict:
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
            "jpy_per_usd": "150.5",
            "source": "test rate",
        }],
    }


class UsageExcelExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pricing_path = self.root / "settings" / "usage_pricing.json"
        self.pricing_path.parent.mkdir()
        self.pricing_path.write_text(json.dumps(pricing_config()), encoding="utf-8")
        self.repo = UsageRepository(root=self.root, project_id="project-1")
        self.repo.initialize_schema()
        self.service = UsageService(
            root=self.root,
            pricing_service=PricingService(config_path=self.pricing_path),
        )

    def tearDown(self):
        self.temp.cleanup()

    def add(self, index: int, *, priced: bool = True) -> None:
        metadata = {
            "trafficType": "ON_DEMAND",
            "candidatesTokenCount": 20,
            "totalTokenCount": 30,
        }
        if priced:
            metadata["promptTokenCount"] = 10
        record = build_usage_record(
            request_id=str(uuid4()),
            created_at=datetime(2025, 1, 2, tzinfo=timezone.utc) + timedelta(minutes=index),
            model="model-a",
            status="success" if index % 2 == 0 else "http_error",
            usage_metadata=metadata,
        )
        self.repo.add(record)

    @staticmethod
    def value_for_label(sheet, label: str):
        for row in sheet.iter_rows():
            if row[0].value == label:
                return row[1].value
        raise AssertionError(f"label not found: {label}")

    def test_all_sheets_all_records_and_screen_totals_match(self):
        for index in range(55):
            self.add(index)
        screen = self.service.query(
            date_from=date(2025, 1, 1), date_to=date(2025, 1, 31),
            page=1, page_size=50,
        )
        exported = self.service.query_for_export(
            date_from=date(2025, 1, 1), date_to=date(2025, 1, 31),
        )
        content = generate_usage_excel(exported, self.service.pricing_settings())
        workbook = load_workbook(io.BytesIO(content), data_only=False)
        self.assertEqual(workbook.sheetnames, [
            "概要", "解析別明細", "月別集計", "工事別集計", "モデル別集計",
        ])
        self.assertEqual(len(screen.details), 50)
        self.assertEqual(workbook["解析別明細"].max_row - 3, 55)
        overview = workbook["概要"]
        self.assertEqual(self.value_for_label(overview, "API呼出し数"), screen.summary.call_count)
        self.assertAlmostEqual(
            self.value_for_label(overview, "推定料金（JPY）"),
            float(screen.summary.estimated_cost_jpy_total),
        )
        self.assertEqual(workbook["月別集計"]["B4"].value, screen.monthly[0].call_count)
        self.assertEqual(workbook["解析別明細"]["L4"].value, 150.5)
        self.assertEqual(overview["B9"].value, 150.5)

    def test_unavailable_price_cells_are_blank_not_zero(self):
        self.add(0, priced=False)
        exported = self.service.query_for_export(
            date_from=date(2025, 1, 1), date_to=date(2025, 1, 31),
        )
        workbook = load_workbook(io.BytesIO(
            generate_usage_excel(exported, self.service.pricing_settings())
        ))
        detail = workbook["解析別明細"]
        self.assertIsNone(detail["J4"].value)
        self.assertIsNone(detail["K4"].value)
        overview = workbook["概要"]
        self.assertIsNone(self.value_for_label(overview, "推定料金（USD）"))
        self.assertIsNone(self.value_for_label(overview, "推定料金（JPY）"))


if __name__ == "__main__":
    unittest.main()
