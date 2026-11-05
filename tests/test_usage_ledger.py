from __future__ import annotations

import io
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch
from uuid import uuid4

from backend.app.core.ai.base import AIBase, AIResponse, UpstreamExecutionError
from backend.app.core.ai.providers.vertex import VertexProvider
from backend.app.core.config import settings
from backend.app.repositories.usage_repository import (
    UsageRepository,
    UsageStorageUnavailable,
    build_usage_record,
)
from backend.app.schemas.analysis import AnalyzeSafetyRequest
from backend.app.services.analysis_service import AnalysisService


class FakeUsageRepository:
    def __init__(self, *, fail: bool = False):
        self.records = []
        self.fail = fail

    def add(self, record):
        if self.fail:
            raise UsageStorageUnavailable("simulated NAS failure")
        self.records.append(record)
        return record


class FakeFactory:
    def __init__(self, provider):
        self.provider = provider

    def get_provider(self):
        return self.provider


class Extractor(AIBase):
    def predict(self, image_base64, image_mime_type, system_instruction, prompt):  # pragma: no cover
        raise NotImplementedError


class UsageLedgerTests(unittest.TestCase):
    def _service(self, provider, usage_repo=None, parser=None):
        service = AnalysisService(usage_repo=usage_repo or FakeUsageRepository())
        service.ai_factory = FakeFactory(provider)
        service.parser = parser or type("Parser", (), {"validate_complete": staticmethod(lambda markdown: [])})()
        return service

    def _run(self, service):
        with patch.multiple(
            settings,
            VERTEX_API_KEY="test-key",
            GEMINI_MODEL="configured-model",
            GOOGLE_CLOUD_PROJECT="project",
        ):
            return service.run_analysis(AnalyzeSafetyRequest(image_base64="aW1hZ2U="))

    @staticmethod
    def _response(metadata=None):
        return AIResponse(
            text="valid markdown",
            model_version="actual-model",
            finish_reason="STOP",
            response_id="response-123",
            usage_metadata=metadata or {},
        )

    def test_normal_usage_and_thought_tokens_are_typed(self):
        metadata = {
            "promptTokenCount": 10,
            "candidatesTokenCount": 20,
            "thoughtsTokenCount": 7,
            "totalTokenCount": 37,
            "cachedContentTokenCount": 3,
            "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 10}],
            "trafficType": "ON_DEMAND",
            "unexpectedSecret": "must-not-be-saved",
        }
        repo = FakeUsageRepository()
        provider = type("Provider", (), {"predict": lambda self, **kwargs: UsageLedgerTests._response(metadata)})()
        result = self._run(self._service(provider, repo))
        record = repo.records[0]
        self.assertEqual(result.result.id, record.request_id)
        self.assertEqual(record.prompt_token_count, 10)
        self.assertEqual(record.thoughts_token_count, 7)
        self.assertEqual(record.total_token_count, 37)
        self.assertEqual(record.prompt_tokens_details[0]["tokenCount"], 10)
        self.assertEqual(record.traffic_type, "ON_DEMAND")
        self.assertNotIn("unexpectedSecret", record.usage_metadata)

    def test_missing_usage_metadata_uses_null_not_zero(self):
        repo = FakeUsageRepository()
        provider = type("Provider", (), {"predict": lambda self, **kwargs: UsageLedgerTests._response()})()
        self._run(self._service(provider, repo))
        record = repo.records[0]
        self.assertIsNone(record.prompt_token_count)
        self.assertIsNone(record.total_token_count)
        self.assertEqual(record.usage_source, "unavailable")
        self.assertIsNone(record.usage_metadata)

    def test_max_tokens_response_is_recorded(self):
        repo = FakeUsageRepository()
        provider = VertexProvider("key", "model", "project", "global")
        provider._post_json = lambda *args: {
            "modelVersion": "actual-model",
            "responseId": "max-response",
            "usageMetadata": {"promptTokenCount": 11, "totalTokenCount": 99},
            "candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "partial"}]}}],
        }
        with self.assertRaises(UpstreamExecutionError):
            self._run(self._service(provider, repo))
        self.assertEqual(repo.records[0].status, "max_tokens")
        self.assertEqual(repo.records[0].total_token_count, 99)

    def test_markdown_validation_failure_is_recorded(self):
        repo = FakeUsageRepository()
        provider = type("Provider", (), {"predict": lambda self, **kwargs: UsageLedgerTests._response({"totalTokenCount": 5})})()
        parser = type("Parser", (), {"validate_complete": staticmethod(lambda markdown: (_ for _ in ()).throw(ValueError("invalid markdown")))})()
        with self.assertRaisesRegex(UpstreamExecutionError, "invalid markdown"):
            self._run(self._service(provider, repo, parser))
        self.assertEqual(repo.records[0].status, "markdown_validation_failed")
        self.assertEqual(repo.records[0].total_token_count, 5)

    def test_http_error_and_timeout_are_recorded_with_unknown_tokens(self):
        for status in ("http_error", "communication_error"):
            with self.subTest(status=status):
                repo = FakeUsageRepository()
                error = UpstreamExecutionError("failed", status=status)
                provider = type("Provider", (), {"predict": lambda self, _error=error, **kwargs: (_ for _ in ()).throw(_error)})()
                with self.assertRaises(UpstreamExecutionError):
                    self._run(self._service(provider, repo))
                self.assertEqual(repo.records[0].status, status)
                self.assertIsNone(repo.records[0].total_token_count)

    def test_http_error_body_usage_is_extracted_without_credentials(self):
        body = io.BytesIO(json.dumps({
            "responseId": "error-response",
            "usageMetadata": {"promptTokenCount": 4, "totalTokenCount": 4},
        }).encode())
        http_error = HTTPError("https://example.invalid", 429, "rate limit", {}, body)
        with patch("backend.app.core.ai.base.request.urlopen", side_effect=http_error):
            with self.assertRaises(UpstreamExecutionError) as caught:
                Extractor()._post_json("https://example.invalid", {"secret": "not logged"}, {"x-goog-api-key": "secret"})
        self.assertEqual(caught.exception.http_status, 429)
        self.assertEqual(caught.exception.usage_metadata["totalTokenCount"], 4)

    def _auth_error(self, code, body_bytes, headers=None):
        return HTTPError("https://example.invalid", code, "x", headers or {}, io.BytesIO(body_bytes))

    def test_auth_errors_log_safe_diagnostics_only(self):
        secret = "AIzaSySECRET-KEY-123"
        cases = [
            (401, "UNAUTHENTICATED", "ACCESS_TOKEN_EXPIRED"),
            (401, "UNAUTHENTICATED", None),
            (403, "PERMISSION_DENIED", "IAM_PERMISSION_DENIED"),
            (401, "UNAUTHENTICATED", "API_KEY_INVALID"),
            (403, "PERMISSION_DENIED", "API_KEY_INVALID"),
        ]
        for code, status, reason in cases:
            with self.subTest(code=code, reason=reason):
                err = {"code": code, "status": status, "message": f"bad key {secret} Bearer ya29.TOKEN"}
                if reason:
                    err["details"] = [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": reason}]
                body = json.dumps({"error": err}).encode()
                exc = self._auth_error(code, body, {"x-goog-request-id": "req-abc123"})
                with patch("backend.app.core.ai.base.request.urlopen", side_effect=exc):
                    with self.assertLogs("genba_safety_rag_app.ai", level="ERROR") as logs:
                        with self.assertRaises(UpstreamExecutionError) as caught:
                            Extractor()._post_json(
                                "https://example.invalid", {"prompt": "REQUESTBODY"},
                                {"x-goog-api-key": secret, "Authorization": "Bearer ya29.TOKEN"},
                            )
                self.assertEqual(caught.exception.status, "http_error")
                self.assertEqual(caught.exception.http_status, code)
                text = " | ".join(logs.output)
                if code in (401, 403):
                    self.assertIn(f"http_status={code}", text)
                    self.assertIn(f"error_status={status}", text)
                    self.assertIn(f"reason={reason or '-'}", text)
                    self.assertIn("request_id=req-abc123", text)
                for leaked in (secret, "ya29", "Bearer", "REQUESTBODY", "bad key"):
                    self.assertNotIn(leaked, text)
                    self.assertNotIn(leaked, str(caught.exception))

    def test_auth_error_non_json_or_hostile_values_are_safe(self):
        for body in (b"<html>403 secret-token</html>", b"[1,2]", b"", b'{"error": "str"}',
                     json.dumps({"error": {"status": "X FAKE LOG secret", "details": [1, {"reason": "a b secret"}]}}).encode()):
            with self.subTest(body=body):
                with patch("backend.app.core.ai.base.request.urlopen", side_effect=self._auth_error(403, body)):
                    with self.assertLogs("genba_safety_rag_app.ai", level="ERROR") as logs:
                        with self.assertRaises(UpstreamExecutionError) as caught:
                            Extractor()._post_json("https://example.invalid", {}, {})
                self.assertEqual(caught.exception.status, "http_error")
                text = " | ".join(logs.output)
                self.assertIn("http_status=403 error_status=-", text)
                self.assertNotIn("secret", text)
                self.assertNotIn("FAKE", text)

    def test_auth_http_error_is_recorded_in_ledger(self):
        repo = FakeUsageRepository()
        exc = self._auth_error(401, json.dumps({"error": {"status": "UNAUTHENTICATED"}}).encode())
        class P:
            def predict(self, **kwargs):
                with patch("backend.app.core.ai.base.request.urlopen", side_effect=exc):
                    Extractor()._post_json("https://example.invalid", {}, {})
        with self.assertRaises(UpstreamExecutionError):
            self._run(self._service(P(), repo))
        self.assertEqual(repo.records[0].status, "http_error")

    def test_http_400_logs_auth_diagnostics_only_when_auth_related(self):
        secret = "AIzaSySECRET-KEY-123"
        cases = [
            ("INVALID_ARGUMENT", "API_KEY_INVALID", True),
            ("UNAUTHENTICATED", None, True),
            ("PERMISSION_DENIED", None, True),
            ("INVALID_ARGUMENT", "ACCESS_TOKEN_EXPIRED", True),
            ("INVALID_ARGUMENT", None, False),
            ("INVALID_ARGUMENT", "BAD_REQUEST_FIELD", False),
            ("FAILED_PRECONDITION", None, False),
        ]
        for status, reason, expect_log in cases:
            with self.subTest(status=status, reason=reason):
                err = {"code": 400, "status": status, "message": f"bad {secret}"}
                if reason:
                    err["details"] = [{"reason": reason}]
                exc = self._auth_error(400, json.dumps({"error": err}).encode(), {"x-goog-request-id": "req-400"})
                with patch("backend.app.core.ai.base.request.urlopen", side_effect=exc):
                    with self.assertRaises(UpstreamExecutionError) as caught:
                        if expect_log:
                            with self.assertLogs("genba_safety_rag_app.ai", level="ERROR") as logs:
                                Extractor()._post_json("https://example.invalid", {}, {"x-goog-api-key": secret})
                        else:
                            with self.assertNoLogs("genba_safety_rag_app.ai", level="ERROR"):
                                Extractor()._post_json("https://example.invalid", {}, {"x-goog-api-key": secret})
                self.assertEqual(caught.exception.status, "http_error")
                self.assertEqual(caught.exception.http_status, 400)
                self.assertNotIn(secret, str(caught.exception))
                if expect_log:
                    text = " | ".join(logs.output)
                    self.assertIn("http_status=400", text)
                    self.assertIn(f"error_status={status}", text)
                    self.assertIn(f"reason={reason or '-'}", text)
                    self.assertNotIn(secret, text)
                    self.assertNotIn("bad ", text)

    def test_transport_timeout_has_communication_status_and_no_usage(self):
        with patch("backend.app.core.ai.base.request.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaises(UpstreamExecutionError) as caught:
                Extractor()._post_json("https://example.invalid", {}, {})
        self.assertEqual(caught.exception.status, "communication_error")
        self.assertEqual(caught.exception.usage_metadata, {})

    def test_usage_write_failure_does_not_trigger_second_ai_call(self):
        calls = []
        provider = type("Provider", (), {"predict": lambda self, **kwargs: calls.append(1) or UsageLedgerTests._response({"totalTokenCount": 2})})()
        with self.assertLogs("genba_safety_rag_app.analysis", level="ERROR"):
            result = self._run(self._service(provider, FakeUsageRepository(fail=True)))
        self.assertEqual(result.used_model, "actual-model")
        self.assertEqual(len(calls), 1)

    def test_concurrent_writes_and_duplicate_prevention(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = UsageRepository(root=Path(temp_dir), project_id="project")
            created_at = datetime.now(timezone.utc)
            records = [
                build_usage_record(
                    request_id=str(uuid4()),
                    created_at=created_at,
                    model="model",
                    status="success",
                    usage_metadata={"totalTokenCount": index},
                )
                for index in range(12)
            ]
            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(repository.add, records))
            self.assertEqual(len(list((Path(temp_dir) / "usage").rglob("*.json"))), 12)

            duplicate = records[0]
            with ThreadPoolExecutor(max_workers=6) as pool:
                returned = list(pool.map(repository.add, [duplicate] * 12))
            self.assertTrue(all(item.usage_id == duplicate.usage_id for item in returned))
            self.assertEqual(len(list((Path(temp_dir) / "usage").rglob(f"{duplicate.usage_id}.json"))), 1)


if __name__ == "__main__":
    unittest.main()
