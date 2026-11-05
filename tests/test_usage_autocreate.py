"""Step 5-1: real UsageRepository wired through AnalysisService (mock Vertex, temp dir only)."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from backend.app.core.ai.base import AIResponse, UpstreamExecutionError
from backend.app.core.config import settings
from backend.app.repositories.usage_repository import UsageRepository
from backend.app.schemas.analysis import AnalyzeSafetyRequest
from backend.app.services.analysis_service import AnalysisService
from backend.app.services.pricing_service import PricingService
from backend.app.services.usage_service import UsageService


class _Factory:
    def __init__(self, provider):
        self.provider = provider

    def get_provider(self):
        return self.provider


def _ok_provider():
    resp = AIResponse(
        text="ok", model_version="model-a", finish_reason="STOP", response_id="r1",
        usage_metadata={"promptTokenCount": 10, "candidatesTokenCount": 20, "totalTokenCount": 30},
    )
    return type("P", (), {"predict": lambda self, **kw: resp})()


def _max_tokens_provider():
    err = UpstreamExecutionError("cut", status="max_tokens")
    err.usage_metadata = {"promptTokenCount": 7, "totalTokenCount": 50}
    err.model_version = "model-a"

    def predict(self, **kw):
        raise err
    return type("P", (), {"predict": predict})()


class UsageAutoCreateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)  # no usage/ folder exists
        self.repo = UsageRepository(root=self.root, project_id="p1")

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, provider, repo=None):
        service = AnalysisService(usage_repo=repo or self.repo)
        service.ai_factory = _Factory(provider)
        service.parser = type("Parser", (), {"validate_complete": staticmethod(lambda m: [])})()
        with patch.multiple(settings, VERTEX_API_KEY="k", GEMINI_MODEL="model-a", GOOGLE_CLOUD_PROJECT="p"):
            return service.run_analysis(AnalyzeSafetyRequest(image_base64="aW1hZ2U="))

    def _files(self):
        return list((self.root / "usage").rglob("*.json"))

    def test_folder_autocreated_and_json_saved_on_success(self):
        self.assertFalse((self.root / "usage").exists())
        result = self._run(_ok_provider())
        files = self._files()
        self.assertEqual(len(files), 1)
        self.assertRegex(files[0].parent.name, r"^\d{4}-\d{2}$")
        raw = json.loads(files[0].read_text(encoding="utf-8"))
        usage = raw["usage"]
        self.assertEqual(usage["request_id"], result.result.id)
        self.assertEqual(usage["model"], "model-a")
        self.assertEqual(usage["status"], "success")
        self.assertEqual(usage["total_token_count"], 30)
        self.assertTrue(usage["created_at"])
        self.assertEqual(raw["project_id"], "p1")

    def test_abnormal_response_saved(self):
        with self.assertRaises(UpstreamExecutionError):
            self._run(_max_tokens_provider())
        raw = json.loads(self._files()[0].read_text(encoding="utf-8"))
        self.assertEqual(raw["usage"]["status"], "max_tokens")
        self.assertEqual(raw["usage"]["total_token_count"], 50)

    def test_same_request_id_not_duplicated(self):
        self._run(_ok_provider())
        record = UsageRepository._read_existing(self._files()[0])
        self.repo.add(record)
        self.repo.add(record)
        self.assertEqual(len(self._files()), 1)

    def test_write_permission_error_logged_and_analysis_succeeds(self):
        with patch("backend.app.core.shared_storage.Path.mkdir", side_effect=PermissionError("denied")):
            with self.assertLogs("genba_safety_rag_app.analysis", level="ERROR") as logs:
                result = self._run(_ok_provider())
        self.assertEqual(result.used_model, "model-a")
        self.assertEqual(self._files(), [])
        self.assertIn("NOT recorded", logs.output[0])
        self.assertIn("denied", logs.output[0])

    def test_saved_ledger_is_read_by_usage_aggregation(self):
        self._run(_ok_provider())
        with self.assertRaises(UpstreamExecutionError):
            self._run(_max_tokens_provider())
        pricing = PricingService(config_path=self.root / "settings" / "usage_pricing.json")
        service = UsageService(root=self.root, pricing_service=pricing)
        today = date.today()
        res = service.query(date_from=today.replace(day=1), date_to=today)
        self.assertEqual(res.summary.call_count, 2)
        self.assertEqual(res.summary.success_count, 1)
        self.assertEqual(res.summary.failure_count, 1)
        self.assertEqual(res.corrupt_json_count, 0)


if __name__ == "__main__":
    unittest.main()
