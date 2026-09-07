from __future__ import annotations

from urllib import parse

from backend.app.core.ai.base import AIBase


class VertexProvider(AIBase):
    def __init__(self, api_key: str, model: str, project_id: str, location: str):
        self.api_key = api_key
        self.model = model
        self.project_id = project_id
        self.location = location

    def predict(self, image_base64: str, image_mime_type: str, system_instruction: str, prompt: str) -> str:
        encoded_model = parse.quote(self.model, safe="")
        encoded_project = parse.quote(self.project_id, safe="")
        encoded_location = parse.quote(self.location, safe="")
        encoded_key = parse.quote(self.api_key, safe="")

        url = (
            f"https://{encoded_location}-aiplatform.googleapis.com/v1/projects/"
            f"{encoded_project}/locations/{encoded_location}/publishers/google/models/"
            f"{encoded_model}:generateContent?key={encoded_key}"
        )

        payload = {
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": image_mime_type,
                                "data": image_base64,
                            }
                        },
                    ],
                }
            ],
        }

        response_json = self._post_json(url, payload)
        return self._extract_text(response_json)
