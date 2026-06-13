import respx
import pytest
from httpx import Response

from app.kimi import DEFAULT_KIMI_BASE_URL, KimiClient


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_kimi_model_override_wins_over_routed_model() -> None:
    client = KimiClient(
        api_key="test-key",
        base_url=DEFAULT_KIMI_BASE_URL,
        model_override="account-specific-kimi-model",
    )

    with respx.mock(assert_all_called=True) as router:
        route = router.post(f"{DEFAULT_KIMI_BASE_URL}/chat/completions").mock(
            return_value=Response(
                200,
                json={"choices": [{"message": {"content": "ok"}}]},
            )
        )

        result = await client.chat(
            messages=[{"role": "user", "content": "hello"}],
            model="kimi-k2.7-code",
        )

    assert result == "ok"
    assert route.calls[0].request.headers["authorization"] == "Bearer test-key"
    assert route.calls[0].request.content
    assert b"account-specific-kimi-model" in route.calls[0].request.content


async def test_kimi_uses_temperature_one_by_default() -> None:
    client = KimiClient(api_key="test-key", base_url=DEFAULT_KIMI_BASE_URL)

    with respx.mock(assert_all_called=True) as router:
        route = router.post(f"{DEFAULT_KIMI_BASE_URL}/chat/completions").mock(
            return_value=Response(
                200,
                json={"choices": [{"message": {"content": "ok"}}]},
            )
        )

        result = await client.chat(messages=[{"role": "user", "content": "hello"}])

    assert result == "ok"
    assert b'"temperature":1.0' in route.calls[0].request.content
