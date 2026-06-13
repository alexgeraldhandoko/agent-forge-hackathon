import pytest
import respx
from httpx import Response

from app.tokenrouter import DEFAULT_TOKENROUTER_BASE_URL, TokenRouterClient, normalize_tokenrouter_base_url


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_tokenrouter_calls_openai_compatible_chat_endpoint() -> None:
    client = TokenRouterClient(
        api_key="tr-test-key",
        base_url=DEFAULT_TOKENROUTER_BASE_URL,
        model_override="kimi-k2.7-code",
    )

    with respx.mock(assert_all_called=True) as router:
        route = router.post(f"{DEFAULT_TOKENROUTER_BASE_URL}/chat/completions").mock(
            return_value=Response(
                200,
                json={"choices": [{"message": {"content": "tokenrouter ok"}}]},
            )
        )

        result = await client.chat(
            messages=[{"role": "user", "content": "hello"}],
            model="fallback-model",
            max_tokens=300,
            temperature=1,
        )

    assert result == "tokenrouter ok"
    assert route.calls[0].request.headers["authorization"] == "Bearer tr-test-key"
    assert b'"model":"kimi-k2.7-code"' in route.calls[0].request.content
    assert b'"max_tokens":300' in route.calls[0].request.content


def test_tokenrouter_normalizes_website_base_url() -> None:
    assert normalize_tokenrouter_base_url("https://www.tokenrouter.com/v1") == DEFAULT_TOKENROUTER_BASE_URL
    assert normalize_tokenrouter_base_url("https://www.tokenrouter.com") == DEFAULT_TOKENROUTER_BASE_URL
