from __future__ import annotations

from urllib import parse

from backend.app.core.ai.base import AIBase, AIResponse


class VertexProvider(AIBase):
    def __init__(self, api_key: str, model: str, project_id: str, location: str, max_output_tokens: int = 8192):
        self.api_key = api_key
        self.model = model
        self.project_id = project_id
        self.location = location
        self.max_output_tokens = max_output_tokens

    def predict(self, image_base64: str, image_mime_type: str, system_instruction: str, prompt: str) -> AIResponse:
        encoded_model = parse.quote(self.model, safe="")
        encoded_project = parse.quote(self.project_id, safe="")
        encoded_location = parse.quote(self.location, safe="")

        # The "global" location uses a host without a region prefix; every
        # other location is served from its own regional host.
        host = "aiplatform.googleapis.com" if self.location == "global" else f"{encoded_location}-aiplatform.googleapis.com"
        url = (
            f"https://{host}/v1/projects/"
            f"{encoded_project}/locations/{encoded_location}/publishers/google/models/"
            f"{encoded_model}:generateContent"
        )

        payload = {
            "generationConfig": {"maxOutputTokens": self.max_output_tokens},
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

        response_json = self._post_json(url, payload, {"x-goog-api-key": self.api_key})
        return self._extract_response(response_json)
