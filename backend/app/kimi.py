import os
from typing import Protocol

import httpx


DEFAULT_KIMI_BASE_URL = "https://api.moonshot.ai/v1"
DEFAULT_KIMI_MODEL = "kimi-k2.7-code"


class KimiClientError(RuntimeError):
    pass


class KimiConfigurationError(KimiClientError):
    pass


class KimiAPIError(KimiClientError):
    pass


class KimiProvider(Protocol):
    name: str

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int = 1200,
        temperature: float = 1.0,
    ) -> str:
        ...


class KimiClient:
    name = "kimi"

    def __init__(
        self,
        api_key: str | None,
        base_url: str = DEFAULT_KIMI_BASE_URL,
        default_model: str = DEFAULT_KIMI_MODEL,
        model_override: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._model_override = model_override
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "KimiClient":
        return cls(
            api_key=os.getenv("MOONSHOT_API_KEY") or os.getenv("KIMI_API_KEY"),
            base_url=os.getenv("KIMI_BASE_URL", DEFAULT_KIMI_BASE_URL),
            default_model=DEFAULT_KIMI_MODEL,
            model_override=os.getenv("KIMI_MODEL"),
            timeout_seconds=float(os.getenv("KIMI_TIMEOUT_SECONDS", "60")),
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int = 1200,
        temperature: float = 1.0,
    ) -> str:
        if not self._api_key:
            raise KimiConfigurationError("Set MOONSHOT_API_KEY or KIMI_API_KEY before running Kimi sessions.")

        payload = {
            "model": self._model_override or model or self._default_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise KimiAPIError(f"Kimi request failed: {exc}") from exc

        if response.status_code >= 400:
            raise KimiAPIError(f"Kimi returned HTTP {response.status_code}: {response.text}")

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise KimiAPIError("Kimi response did not include choices[0].message.content.") from exc

        if not isinstance(content, str):
            raise KimiAPIError("Kimi response content was not text.")

        return content
