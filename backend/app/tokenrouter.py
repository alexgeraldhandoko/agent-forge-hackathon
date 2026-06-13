import os

import httpx


DEFAULT_TOKENROUTER_BASE_URL = "https://api.tokenrouter.com/v1"
TOKENROUTER_WEBSITE_BASE_URLS = {
    "https://www.tokenrouter.com",
    "https://www.tokenrouter.com/v1",
    "https://tokenrouter.com",
    "https://tokenrouter.com/v1",
}


class TokenRouterClientError(RuntimeError):
    pass


class TokenRouterConfigurationError(TokenRouterClientError):
    pass


class TokenRouterAPIError(TokenRouterClientError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_text: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text or ""

    @property
    def is_model_unavailable(self) -> bool:
        normalized = self.response_text.lower()
        return "model_not_found" in normalized or "no available channel for model" in normalized

    @property
    def is_fallback_eligible(self) -> bool:
        return self.is_model_unavailable or (self.status_code is not None and self.status_code >= 500)


def normalize_tokenrouter_base_url(base_url: str) -> str:
    cleaned_url = base_url.rstrip("/")
    if cleaned_url in TOKENROUTER_WEBSITE_BASE_URLS:
        return DEFAULT_TOKENROUTER_BASE_URL
    return cleaned_url


class TokenRouterClient:
    name = "tokenrouter"

    def __init__(
        self,
        api_key: str | None,
        base_url: str = DEFAULT_TOKENROUTER_BASE_URL,
        model_override: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = normalize_tokenrouter_base_url(base_url)
        self._model_override = model_override
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "TokenRouterClient":
        return cls(
            api_key=os.getenv("TOKENROUTER_API_KEY"),
            base_url=os.getenv("TOKENROUTER_BASE_URL", DEFAULT_TOKENROUTER_BASE_URL),
            model_override=os.getenv("TOKENROUTER_MODEL"),
            timeout_seconds=float(os.getenv("TOKENROUTER_TIMEOUT_SECONDS", "60")),
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int = 1200,
        temperature: float = 1.0,
    ) -> str:
        if not self._api_key:
            raise TokenRouterConfigurationError("Set TOKENROUTER_API_KEY before running TokenRouter sessions.")

        payload = {
            "model": self._model_override or model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if not payload["model"]:
            raise TokenRouterConfigurationError("Set TOKENROUTER_MODEL or use a routed session with a model.")

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
            raise TokenRouterAPIError(f"TokenRouter request failed: {exc}") from exc

        if response.status_code >= 400:
            raise TokenRouterAPIError(
                f"TokenRouter returned HTTP {response.status_code} from {self._base_url}/chat/completions: "
                f"{response.text}",
                status_code=response.status_code,
                response_text=response.text,
            )

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TokenRouterAPIError(
                "TokenRouter response did not include choices[0].message.content."
            ) from exc

        if not isinstance(content, str):
            raise TokenRouterAPIError("TokenRouter response content was not text.")

        return content
