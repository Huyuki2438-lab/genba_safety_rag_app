"""Defense in depth: known credentials never become shared text or UI output."""
import os

def redact(value):
    if isinstance(value, str):
        for name in ("GEMINI_API_KEY", "GEMINI_A_API_KEY", "GEMINI_B_API_KEY", "VERTEX_API_KEY"):
            key = os.getenv(name, "")
            if len(key) >= 8:
                value = value.replace(key, "[非表示]")
        return value
    if isinstance(value, dict):
        return {redact(k): redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value
