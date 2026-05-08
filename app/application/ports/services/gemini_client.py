from typing import Any, Protocol


class GeminiClientPort(Protocol):
    model: str

    def generate_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        pass
