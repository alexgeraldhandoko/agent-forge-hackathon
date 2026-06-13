import html
import os
import re
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import quote_plus

import httpx
from pydantic import BaseModel, Field

from app.models import TaskType


DEFAULT_BRIGHTDATA_ENDPOINT = "https://api.brightdata.com/request"
DEFAULT_SEARCH_URL = "https://www.google.com/search"
WEB_INTENT_KEYWORDS = (
    "latest",
    "current",
    "today",
    "recent",
    "news",
    "price",
    "pricing",
    "release",
    "changelog",
    "docs",
    "documentation",
    "web",
    "website",
    "scrape",
    "search",
    "research",
    "look up",
    "lookup",
    "up to date",
    "up-to-date",
)


class BrightDataClientError(RuntimeError):
    pass


class BrightDataConfigurationError(BrightDataClientError):
    pass


class BrightDataAPIError(BrightDataClientError):
    pass


class SearchResult(BaseModel):
    title: str
    url: str
    description: str | None = None
    rank: int | None = None
    content: str | None = None


class WebResearchContext(BaseModel):
    query: str
    source: str = "Bright Data"
    results: list[SearchResult] = Field(default_factory=list)


class WebResearcher(Protocol):
    name: str

    async def research(
        self,
        prompt: str,
        max_results: int = 5,
        fetch_pages: bool = True,
        query_override: str | None = None,
    ) -> WebResearchContext:
        ...


def should_use_web_research(task_type: TaskType, prompt: str, force_web: bool | None = None) -> bool:
    if force_web is not None:
        return force_web

    if task_type == TaskType.web:
        return True

    normalized_prompt = prompt.lower()
    return any(keyword in normalized_prompt for keyword in WEB_INTENT_KEYWORDS)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._ignored_tags: list[str] = []
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._ignored_tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._ignored_tags and self._ignored_tags[-1] == tag:
            self._ignored_tags.pop()

    def handle_data(self, data: str) -> None:
        if not self._ignored_tags:
            text = data.strip()
            if text:
                self._chunks.append(text)

    def get_text(self) -> str:
        return normalize_text(" ".join(self._chunks))


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def html_to_text(value: str) -> str:
    parser = TextExtractor()
    parser.feed(value)
    return parser.get_text()


class BrightDataClient:
    name = "brightdata"

    def __init__(
        self,
        api_key: str | None,
        serp_zone: str | None,
        unlocker_zone: str | None = None,
        endpoint: str = DEFAULT_BRIGHTDATA_ENDPOINT,
        country: str = "us",
        language: str = "en",
        timeout_seconds: float = 45.0,
        page_excerpt_chars: int = 3000,
    ) -> None:
        self._api_key = api_key
        self._serp_zone = serp_zone
        self._unlocker_zone = unlocker_zone
        self._endpoint = endpoint
        self._country = country
        self._language = language
        self._timeout_seconds = timeout_seconds
        self._page_excerpt_chars = page_excerpt_chars

    @classmethod
    def from_env(cls) -> "BrightDataClient":
        return cls(
            api_key=os.getenv("BRIGHTDATA_API_KEY"),
            serp_zone=os.getenv("BRIGHTDATA_SERP_ZONE"),
            unlocker_zone=os.getenv("BRIGHTDATA_UNLOCKER_ZONE"),
            endpoint=os.getenv("BRIGHTDATA_ENDPOINT", DEFAULT_BRIGHTDATA_ENDPOINT),
            country=os.getenv("BRIGHTDATA_COUNTRY", "us"),
            language=os.getenv("BRIGHTDATA_LANGUAGE", "en"),
            timeout_seconds=float(os.getenv("BRIGHTDATA_TIMEOUT_SECONDS", "45")),
            page_excerpt_chars=int(os.getenv("BRIGHTDATA_PAGE_EXCERPT_CHARS", "3000")),
        )

    async def research(
        self,
        prompt: str,
        max_results: int = 5,
        fetch_pages: bool = True,
        query_override: str | None = None,
    ) -> WebResearchContext:
        query = normalize_text(query_override or prompt)
        search_results = await self.search(query, max_results=max_results)

        if fetch_pages and self._unlocker_zone:
            enriched_results = []
            for result in search_results:
                content = await self.fetch_page_excerpt(result.url)
                enriched_results.append(result.model_copy(update={"content": content}))
            search_results = enriched_results

        return WebResearchContext(query=query, results=search_results)

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not self._api_key or not self._serp_zone:
            raise BrightDataConfigurationError(
                "Set BRIGHTDATA_API_KEY and BRIGHTDATA_SERP_ZONE before running web research."
            )

        url = (
            f"{DEFAULT_SEARCH_URL}?q={quote_plus(query)}"
            f"&hl={quote_plus(self._language)}&gl={quote_plus(self._country)}"
        )
        payload = {
            "zone": self._serp_zone,
            "url": url,
            "format": "raw",
            "data_format": "parsed_light",
        }
        data = await self._request(payload)
        return self._parse_search_results(data)[:max_results]

    async def fetch_page_excerpt(self, url: str) -> str | None:
        if not self._api_key or not self._unlocker_zone:
            return None

        payload = {
            "zone": self._unlocker_zone,
            "url": url,
            "format": "raw",
            "data_format": "markdown",
        }
        data = await self._request(payload)

        if isinstance(data, str):
            text = data if not data.lstrip().startswith("<") else html_to_text(data)
        else:
            text = normalize_text(str(data))

        return text[: self._page_excerpt_chars] if text else None

    async def _request(self, payload: dict) -> dict | list | str:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise BrightDataAPIError(f"Bright Data request failed: {exc}") from exc

        if response.status_code >= 400:
            raise BrightDataAPIError(f"Bright Data returned HTTP {response.status_code}: {response.text}")

        try:
            return response.json()
        except ValueError:
            return response.text

    def _parse_search_results(self, data: dict | list | str) -> list[SearchResult]:
        if isinstance(data, str):
            return [SearchResult(title="Search results", url="", description=html_to_text(data))]

        if isinstance(data, list):
            candidates = data
        else:
            candidates = data.get("organic") or data.get("results") or []

        results: list[SearchResult] = []
        for index, candidate in enumerate(candidates, start=1):
            if not isinstance(candidate, dict):
                continue

            url = candidate.get("link") or candidate.get("url")
            title = candidate.get("title") or candidate.get("name")
            if not url or not title:
                continue

            description = candidate.get("description") or candidate.get("snippet")
            rank = candidate.get("global_rank") or candidate.get("position") or index
            results.append(
                SearchResult(
                    title=normalize_text(str(title)),
                    url=str(url),
                    description=normalize_text(str(description)) if description else None,
                    rank=int(rank) if isinstance(rank, int | float) else index,
                )
            )

        return results

