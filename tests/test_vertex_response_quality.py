from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from backend.app.core.ai.base import AIBase, AIResponse, UpstreamExecutionError
from backend.app.core.ai.providers.vertex import VertexProvider
from backend.app.core.config import settings
from backend.app.core.parser.analysis_parser import AnalysisParser
from backend.app.repositories.history_repository import AnalysisHistoryRecord, HistoryRepository
from backend.app.schemas.analysis import AnalyzeSafetyRequest
from backend.app.schemas.history import CreateAnalysisHistoryRequest
from backend.app.services.analysis_service import AnalysisService
from backend.app.services.history_service import HistoryService


NORMAL_MARKDOWN = """[SECTION:OVERALL]
# 1. 総合評価
- 注意が必要です。

[SECTION:SUMMARY]
# 2. リスク要約表
| No | リスク項目 | 危険な理由 | 重大度 | 推奨対策 |
| --- | --- | --- | --- | --- |
| 1 | 重機接触 | 作業員が近い | 高 | 誘導員が立入を制限する |

[SECTION:RISKS]
# 3. 詳細リスク
## 3-1. 重機接触
- 観察事項: 重機がある

[SECTION:SOLUTIONS]
# 4. 是正計画
- 立入制限を行う

[SECTION:ADDITIONAL]
# 5. 補足事項
- 作業前にKYを行う
"""


def vertex_response(*, reason="STOP", text=NORMAL_MARKDOWN, parts=None, include_candidates=True, include_reason=True, finish_message=None):
    payload = {
        "modelVersion": "gemini-2.5-flash-20260901",
        "responseId": "response-123",
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 20, "totalTokenCount": 30},
    }
    if include_candidates:
        candidate = {"content": {"parts": parts if parts is not None else [{"text": text}]}}
        if include_reason:
            candidate["finishReason"] = reason
        if finish_message is not None:
            candidate["finishMessage"] = finish_message
        payload["candidates"] = [candidate]
    return payload


class Extractor(AIBase):
    def predict(self, image_base64, image_mime_type, system_instruction, prompt):  # pragma: no cover
        raise NotImplementedError


class FakeRepository:
    def __init__(self):
        self.records = []

    def add(self, record):
        self.records.append(record)
        return record


class VertexResponseQualityTests(unittest.TestCase):
    def setUp(self):
        self.extractor = Extractor()

    def test_01_stop_and_complete_markdown(self):
        response = self.extractor._extract_response(vertex_response(finish_message="completed"))
        self.assertEqual(response.finish_reason, "STOP")
        self.assertEqual(response.model_version, "gemini-2.5-flash-20260901")
        self.assertEqual(response.response_id, "response-123")
        self.assertEqual(response.usage_metadata["totalTokenCount"], 30)
        self.assertEqual(response.finish_message, "completed")
        self.assertEqual(len(AnalysisParser.validate_complete(response.text)), 1)

    def test_02_max_tokens_is_rejected_even_with_body(self):
        with self.assertRaisesRegex(UpstreamExecutionError, "最大出力トークン"):
            self.extractor._extract_response(vertex_response(reason="MAX_TOKENS", text=NORMAL_MARKDOWN[:100]))

    def test_03_stop_with_empty_body_is_rejected(self):
        with self.assertRaisesRegex(UpstreamExecutionError, "本文が空"):
            self.extractor._extract_response(vertex_response(text="  \n"))

    def test_04_missing_candidates_is_rejected(self):
        with self.assertRaisesRegex(UpstreamExecutionError, "candidates"):
            self.extractor._extract_response(vertex_response(include_candidates=False))

    def test_05_all_text_parts_are_joined_in_order(self):
        response = self.extractor._extract_response(vertex_response(parts=[
            {"text": "first"}, {"inlineData": {"data": "ignored"}}, {"text": " second"}
        ]))
        self.assertEqual(response.text, "first second")

    def test_06_missing_required_section_is_rejected(self):
        incomplete = NORMAL_MARKDOWN.replace("[SECTION:ADDITIONAL]", "[SECTION:UNKNOWN]")
        with self.assertRaisesRegex(ValueError, "5セクション"):
            AnalysisParser.validate_complete(incomplete)

    def test_07_zero_risk_factors_is_rejected(self):
        no_rows = NORMAL_MARKDOWN.replace(
            "| 1 | 重機接触 | 作業員が近い | 高 | 誘導員が立入を制限する |", ""
        )
        with self.assertRaisesRegex(ValueError, "危険要因"):
            AnalysisParser.validate_complete(no_rows)

    def test_08_safety_finish_is_rejected(self):
        with self.assertRaisesRegex(UpstreamExecutionError, "安全性"):
            self.extractor._extract_response(vertex_response(reason="SAFETY"))

    def test_09_missing_finish_reason_is_rejected(self):
        with self.assertRaisesRegex(UpstreamExecutionError, "正常終了を示す情報"):
            self.extractor._extract_response(vertex_response(include_reason=False))

    def test_10_complete_analysis_is_saved_and_model_version_is_used(self):
        service = AnalysisService()
        ai_response = AIResponse(
            text=NORMAL_MARKDOWN, model_version="actual-model-version", finish_reason="STOP",
            response_id="response-123", usage_metadata={"totalTokenCount": 30},
        )
        provider = type("Provider", (), {"predict": lambda self, **kwargs: ai_response})()
        service.ai_factory = type("Factory", (), {"get_provider": lambda self: provider})()
        with patch.multiple(settings, VERTEX_API_KEY="key", GEMINI_MODEL="configured-model", GOOGLE_CLOUD_PROJECT="project"):
            result = service.run_analysis(AnalyzeSafetyRequest(image_base64="aW1hZ2U="))
        self.assertEqual(result.used_model, "actual-model-version")
        self.assertEqual(len(result.result.factors), 1)

        repo = FakeRepository()
        history = HistoryService(repository=repo)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "records").mkdir()
            (root / "images").mkdir()
            with patch.multiple(settings, DATA_DIR=root, PHOTO_STORAGE_DIR=root / "images"):
                saved = history.create(self._history_request(NORMAL_MARKDOWN), fallback_created_by="tester")
        self.assertEqual(saved.model, "actual-model-version")
        self.assertEqual(len(repo.records), 1)

    def test_11_incomplete_analysis_is_not_saved(self):
        repo = FakeRepository()
        history = HistoryService(repository=repo)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.multiple(settings, DATA_DIR=root, PHOTO_STORAGE_DIR=root / "images"):
                with self.assertRaises(ValueError):
                    history.create(self._history_request("[SECTION:OVERALL]\n未完成"), fallback_created_by="tester")
        self.assertEqual(repo.records, [])

    def test_12_existing_history_json_remains_readable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            record = AnalysisHistoryRecord(
                id="12345678-1234-5678-1234-567812345678",
                created_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
                updated_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
                image_name="old.jpg", photo_relative_path="2025/01/old.jpg",
                mode="vertex", provider_display_label="AI解析", model="old-model",
                markdown="旧履歴は新規保存時の完全性検証対象外",
            )
            path = root / "records" / "2025-01" / f"{record.id}.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "schema_version": 1, "record_id": record.id, "project_id": "project",
                "analysis": record.model_dump(mode="json"),
            }, ensure_ascii=False), encoding="utf-8")
            repository = HistoryRepository(root=root, project_id="project")
            loaded = repository._read(path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.markdown, record.markdown)

    def test_vertex_request_sets_configurable_max_output_tokens(self):
        provider = VertexProvider("key", "model", "project", "global", max_output_tokens=1234)
        captured = {}

        def fake_post(url, payload, headers):
            captured.update(payload)
            return vertex_response()

        provider._post_json = fake_post
        provider.predict("image", "image/jpeg", "system", "prompt")
        self.assertEqual(captured["generationConfig"]["maxOutputTokens"], 1234)
        self.assertEqual(type(settings).model_fields["VERTEX_MAX_OUTPUT_TOKENS"].default, 8192)

    @staticmethod
    def _history_request(markdown):
        return CreateAnalysisHistoryRequest(
            imageName="photo.jpg", imageMimeType="image/jpeg", imageBase64="aW1hZ2U=",
            mode="vertex", providerDisplayLabel="AI解析", model="actual-model-version",
            markdown=markdown, siteName="site", workContent="work", mainRisk="risk", createdBy="tester",
        )


if __name__ == "__main__":
    unittest.main()
