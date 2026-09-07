from __future__ import annotations
import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from urllib import error, request

if TYPE_CHECKING:
    from backend.app.schemas.analysis import AnalyzeSafetyRequest


class UpstreamExecutionError(RuntimeError):
    """AI model call failure error."""
    pass


class AIBase(ABC):
    @abstractmethod
    def predict(self, image_base64: str, image_mime_type: str, system_instruction: str, prompt: str) -> str:
        """Run inference against an AI model and return the text response."""
        pass

    # ------------------------------------------------------------------
    # Shared utilities used by subclasses
    # ------------------------------------------------------------------

    def _post_json(self, url: str, payload: dict) -> dict:
        """POST a JSON payload and return the response as a dict."""
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=url,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=90) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise UpstreamExecutionError(
                f"API error (HTTP {exc.code}): {detail or exc.reason}"
            ) from exc
        except Exception as exc:
            raise UpstreamExecutionError(f"API connection error: {str(exc)}") from exc

    def _extract_text(self, response_json: dict) -> str:
        """Extract text from the common Gemini / Vertex response format."""
        candidates = response_json.get("candidates")
        if not candidates or not isinstance(candidates, list):
            raise UpstreamExecutionError(
                "AI response does not contain candidates."
            )
        try:
            return candidates[0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise UpstreamExecutionError(
                "Could not extract text from AI response."
            )
