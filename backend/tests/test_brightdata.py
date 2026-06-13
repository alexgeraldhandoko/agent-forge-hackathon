import pytest
import respx
from httpx import Response

from app.brightdata import DEFAULT_BRIGHTDATA_ENDPOINT, BrightDataClient, should_use_web_research
from app.models import TaskType


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_brightdata_search_uses_serp_api_request_shape() -> None:
    client = BrightDataClient(
        api_key="bd-test-key",
        serp_zone="serp-zone",
        endpoint=DEFAULT_BRIGHTDATA_ENDPOINT,
    )

    with respx.mock(assert_all_called=True) as router:
        route = router.post(DEFAULT_BRIGHTDATA_ENDPOINT).mock(
            return_value=Response(
                200,
                json={
                    "organic": [
                        {
                            "link": "https://example.com/current",
                            "title": "Current result",
                            "description": "Fresh web evidence.",
                            "global_rank": 1,
                        }
                    ]
                },
            )
        )

        results = await client.search("latest Kimi model", max_results=1)

    assert results[0].url == "https://example.com/current"
    assert results[0].title == "Current result"
    assert route.calls[0].request.headers["authorization"] == "Bearer bd-test-key"
    assert b'"zone":"serp-zone"' in route.calls[0].request.content
    assert b'"data_format":"parsed_light"' in route.calls[0].request.content


def test_web_research_detection() -> None:
    assert should_use_web_research(TaskType.web, "anything")
    assert should_use_web_research(TaskType.coding, "Use the latest docs")
    assert not should_use_web_research(TaskType.coding, "Refactor this local function")
    assert not should_use_web_research(TaskType.web, "anything", force_web=False)

