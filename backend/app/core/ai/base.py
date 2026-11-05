from __future__ import annotations
import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib import error, request

if TYPE_CHECKING:
    from backend.app.schemas.analysis import AnalyzeSafetyRequest


class UpstreamExecutionError(RuntimeError):
    """AI model call failure error."""

    def __init__(
        self,
        message: str,
        *,
        status: str = "upstream_error",
        http_status: int | None = None,
        response_id: str | None = None,
        model_version: str | None = None,
        usage_metadata: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.http_status = http_status
        self.response_id = response_id
        self.model_version = model_version
        self.usage_metadata = usage_metadata if isinstance(usage_metadata, dict) else {}


@dataclass(frozen=True)
class AIResponse:
    """Validated text and non-sensitive diagnostics returned by the AI API."""

    text: str
    model_version: str | None = None
    finish_reason: str | None = None
    response_id: str | None = None
    usage_metadata: dict[str, Any] = field(default_factory=dict)
    finish_message: str | None = None


logger = logging.getLogger("genba_safety_rag_app.ai")

_SAFE_CODE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.\-:]{1,128}$")
_REQUEST_ID_HEADERS = ("x-goog-request-id", "x-request-id", "x-cloud-trace-context")


def _safe_value(value: Any, pattern: re.Pattern[str]) -> str | None:
    """Return the value only if it is a short token of harmless characters."""
    if isinstance(value, str) and pattern.match(value):
        return value
    return None


_AUTH_ERROR_STATUSES = frozenset({"UNAUTHENTICATED", "PERMISSION_DENIED"})
_AUTH_REASON_MARKERS = (
    "API_KEY", "ACCESS_TOKEN", "CREDENTIAL", "AUTH", "IAM_PERMISSION_DENIED",
    "SERVICE_DISABLED", "ACCOUNT_STATE_INVALID", "USER_PROJECT_DENIED",
    "CONSUMER_INVALID", "SECURITY_POLICY_VIOLATED",
)


def is_auth_related_error(diag: dict[str, Any]) -> bool:
    """401/403 are always auth errors; 400 only when Google's status/reason says so."""
    http_status = diag.get("http_status")
    if http_status in (401, 403):
        return True
    if http_status != 400:
        return False
    if diag.get("error_status") in _AUTH_ERROR_STATUSES:
        return True
    reason = (diag.get("reason") or "").upper()
    return any(marker in reason for marker in _AUTH_REASON_MARKERS)


def extract_auth_diagnostics(http_status: int, response_json: dict[str, Any], headers: Any = None) -> dict[str, Any]:
    """Pick only whitelisted, format-validated fields from a Google error response.

    Never returns the error message, request body, headers or tokens.
    """
    error_obj = response_json.get("error") if isinstance(response_json, dict) else None
    if not isinstance(error_obj, dict):
        error_obj = {}
    reasons: list[str] = []
    details = error_obj.get("details")
    if isinstance(details, list):
        for item in details[:10]:
            if isinstance(item, dict):
                reason = _safe_value(item.get("reason"), _SAFE_CODE)
                if reason and reason not in reasons:
                    reasons.append(reason)
    request_id = None
    if headers is not None:
        for name in _REQUEST_ID_HEADERS:
            try:
                candidate = headers.get(name)
            except Exception:
                candidate = None
            request_id = _safe_value(candidate, _SAFE_REQUEST_ID)
            if request_id:
                break
    if not request_id:
        request_id = _safe_value(response_json.get("responseId") if isinstance(response_json, dict) else None, _SAFE_REQUEST_ID)
    return {
        "http_status": http_status,
        "error_status": _safe_value(error_obj.get("status"), _SAFE_CODE),
        "reason": ",".join(reasons) if reasons else None,
        "request_id": request_id,
    }


class AIBase(ABC):
    @abstractmethod
    def predict(self, image_base64: str, image_mime_type: str, system_instruction: str, prompt: str) -> AIResponse:
        """Run inference and return a response whose completion was validated."""
        pass

    # ------------------------------------------------------------------
    # Shared utilities used by subclasses
    # ------------------------------------------------------------------

    def _post_json(self, url: str, payload: dict, headers: dict | None = None) -> dict:
        """POST a JSON payload and return the response as a dict."""
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=url,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8", **(headers or {})},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=90) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            response_json: dict[str, Any] = {}
            try:
                raw = exc.read().decode("utf-8", errors="ignore")
                parsed = json.loads(raw) if raw else {}
                response_json = parsed if isinstance(parsed, dict) else {}
            except (OSError, ValueError, TypeError):
                pass
            if exc.code in (400, 401, 403):
                diag = extract_auth_diagnostics(exc.code, response_json, getattr(exc, "headers", None))
            else:
                diag = None
            if diag is not None and is_auth_related_error(diag):
                logger.error(
                    "Vertex AI auth error: http_status=%s error_status=%s reason=%s request_id=%s",
                    diag["http_status"], diag["error_status"] or "-", diag["reason"] or "-", diag["request_id"] or "-",
                )
            usage_metadata = response_json.get("usageMetadata")
            raise UpstreamExecutionError(
                f"AIサービスへの接続に失敗しました（HTTP {exc.code}）。管理者へ連絡してください。",
                status="http_error",
                http_status=exc.code,
                response_id=response_json.get("responseId") if isinstance(response_json.get("responseId"), str) else None,
                model_version=response_json.get("modelVersion") if isinstance(response_json.get("modelVersion"), str) else None,
                usage_metadata=usage_metadata if isinstance(usage_metadata, dict) else None,
            ) from None
        except Exception:
            raise UpstreamExecutionError(
                "AIサービスに接続できません。インターネット接続を確認して再試行してください。",
                status="communication_error",
            ) from None

    def _extract_response(self, response_json: dict) -> AIResponse:
        """Validate and extract the common Gemini / Vertex response format."""
        candidates = response_json.get("candidates")
        if not candidates or not isinstance(candidates, list):
            raise UpstreamExecutionError("AIの応答に解析候補がcandidatesとして含まれていません。再解析してください。")

        candidate = candidates[0]
        if not isinstance(candidate, dict):
            raise UpstreamExecutionError("AIの応答形式が不正です。再解析してください。")

        raw_reason = candidate.get("finishReason")
        finish_reason = raw_reason.strip().upper() if isinstance(raw_reason, str) and raw_reason.strip() else None
        finish_message = candidate.get("finishMessage") if isinstance(candidate.get("finishMessage"), str) else None
        if finish_reason != "STOP":
            if finish_reason == "MAX_TOKENS":
                message = "AIの応答が最大出力トークン数に達し、途中で終了しました。再解析してください。"
            elif finish_reason == "SAFETY":
                message = "AIの応答が安全性判定により停止しました。画像内容を確認して再解析してください。"
            elif finish_reason is None:
                message = "AIの応答に正常終了を示す情報がありません。再解析してください。"
            else:
                message = f"AIの応答が正常終了しませんでした（終了理由: {finish_reason}）。再解析してください。"
            logger.warning(
                "Vertex response rejected: finish_reason=%s response_id=%s finish_message_present=%s",
                finish_reason or "MISSING",
                response_json.get("responseId") if isinstance(response_json.get("responseId"), str) else None,
                bool(finish_message),
            )
            raise UpstreamExecutionError(message)

        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            parts = []
        text = "".join(part["text"] for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str))
        if not text.strip():
            raise UpstreamExecutionError("AIの応答本文が空です。再解析してください。")

        usage_metadata = response_json.get("usageMetadata")
        return AIResponse(
            text=text,
            model_version=response_json.get("modelVersion") if isinstance(response_json.get("modelVersion"), str) else None,
            finish_reason=finish_reason,
            response_id=response_json.get("responseId") if isinstance(response_json.get("responseId"), str) else None,
            usage_metadata=usage_metadata if isinstance(usage_metadata, dict) else {},
            finish_message=finish_message,
        )

    def _extract_text(self, response_json: dict) -> str:
        """Backward-compatible text helper; applies the same validation."""
        return self._extract_response(response_json).text
