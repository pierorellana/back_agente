import json
import logging
from typing import Any

import httpx

from app.domain.errors import IntegrationError
from app.infrastructure.config.settings import Settings

logger = logging.getLogger("app.gemini")


class HttpxGeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.model = model
        self._client = httpx.Client(
            base_url="https://generativelanguage.googleapis.com/v1beta",
            timeout=timeout_seconds,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "HttpxGeminiClient":
        if not settings.gemini_api_key:
            raise IntegrationError("GEMINI_API_KEY is not configured.")

        return cls(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )

    def generate_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        logger.info("gemini_generate_json_started model=%s", self.model)
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt,
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "responseFormat": {
                    "text": {
                        "mimeType": "application/json",
                        "schema": schema,
                    }
                },
            },
        }
        response = self._send(
            "POST",
            f"/models/{self.model}:generateContent",
            "generate_content",
            json=payload,
        )
        response_payload = self._handle_response(response, "generate_content")
        text = self._extract_text(response_payload)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.exception("gemini_generate_json_invalid_json text=%s", text)
            raise IntegrationError("Gemini returned invalid JSON.") from exc

        if not isinstance(data, dict):
            raise IntegrationError("Gemini returned a JSON payload that is not an object.")

        logger.info("gemini_generate_json_succeeded model=%s", self.model)
        return data

    def _extract_text(self, response_payload: dict[str, Any]) -> str:
        candidates = response_payload.get("candidates") or []
        if not candidates:
            raise IntegrationError("Gemini returned no candidates.")

        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        if not parts:
            raise IntegrationError("Gemini returned no text parts.")

        text = parts[0].get("text")
        if not isinstance(text, str) or not text.strip():
            raise IntegrationError("Gemini returned an empty text response.")

        return text

    def _send(self, method: str, url: str, operation: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            logger.exception("gemini_%s_transport_failed error=%s", operation, exc)
            raise IntegrationError(
                f"Could not reach Gemini while running {operation}: {exc}"
            ) from exc

    def _handle_response(self, response: httpx.Response, operation: str) -> dict[str, Any]:
        if response.is_success:
            logger.info("gemini_%s_succeeded status_code=%s", operation, response.status_code)
            return response.json()

        message = response.text
        try:
            payload = response.json()
            error = payload.get("error") or {}
            message = error.get("message", message)
        except ValueError:
            pass

        logger.error(
            "gemini_%s_failed status_code=%s message=%s",
            operation,
            response.status_code,
            message,
        )
        raise IntegrationError(
            f"Gemini {operation} failed with status {response.status_code}: {message}"
        )
