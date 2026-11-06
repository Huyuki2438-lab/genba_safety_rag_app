"""コピー.env の読み込み検証(--verify)と、標準Vertex AIへの認証テスト1回(--auth-once)。
自動再試行なし。キー・レスポンス本文は出力しない。"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from copy_env_loader import COPY_ENV, apply_copy_env_to_config  # noqa: E402

import backend.app.core.config as config  # noqa: E402

loaded, settings = apply_copy_env_to_config(config)
from backend.app.core.ai.base import extract_auth_diagnostics  # noqa: E402

key = settings.VERTEX_API_KEY
expected = __import__("dotenv").dotenv_values(COPY_ENV)["VERTEX_API_KEY"]
print("loaded from コピー.env:", loaded)
print("key source is コピー.env:", key == expected, "| key length:", len(key))
print("model/project/location:", settings.GEMINI_MODEL, settings.GOOGLE_CLOUD_PROJECT, settings.GOOGLE_CLOUD_LOCATION)

if "--auth-once" in sys.argv:
    loc = settings.GOOGLE_CLOUD_LOCATION
    host = "aiplatform.googleapis.com" if loc == "global" else f"{loc}-aiplatform.googleapis.com"
    url = (f"https://{host}/v1/projects/{settings.GOOGLE_CLOUD_PROJECT}/locations/{loc}"
           f"/publishers/google/models/{settings.GEMINI_MODEL}:generateContent")
    body = json.dumps({"generationConfig": {"maxOutputTokens": 8},
                       "contents": [{"role": "user", "parts": [{"text": "ping"}]}]}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    print("endpoint host:", host)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("HTTP status:", r.status)
    except urllib.error.HTTPError as e:
        try:
            parsed = json.loads(e.read().decode("utf-8", "replace"))
        except ValueError:
            parsed = {}
        print("diagnostics:", extract_auth_diagnostics(e.code, parsed if isinstance(parsed, dict) else {}, e.headers))
    except Exception as e:
        print("network error:", type(e).__name__)
