from __future__ import annotations

from urllib import parse

from backend.app.core.ai.base import AIBase


class GeminiProvider(AIBase):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def predict(self, image_base64: str, image_mime_type: str, system_instruction: str, prompt: str) -> str:
        encoded_model = parse.quote(self.model, safe="")
        encoded_key = parse.quote(self.api_key, safe="")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{encoded_model}:generateContent?key={encoded_key}"
        )

        payload = {
            "system_instruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": image_mime_type,
                                "data": image_base64,
                            }
                        },
                    ],
                }
            ],
        }

        response_json = self._post_json(url, payload)
        return self._extract_text(response_json)
