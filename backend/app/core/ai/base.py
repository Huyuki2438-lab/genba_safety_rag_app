from __future__ import annotations
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib import error, request

if TYPE_CHECKING:
    from backend.app.schemas.analysis import AnalyzeSafetyRequest


class UpstreamExecutionError(RuntimeError):
    """AI model call failure error."""
    pass


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
            raise UpstreamExecutionError(f"AIサービスへの接続に失敗しました（HTTP {exc.code}）。管理者へ連絡してください。") from None
        except Exception:
            raise UpstreamExecutionError("AIサービスに接続できません。インターネット接続を確認して再試行してください。") from None

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
