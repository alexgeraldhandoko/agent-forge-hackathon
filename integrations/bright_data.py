"""
BrightData Web Scraper API — fetches live docs as markdown for KimiAI context injection.
Endpoint: POST https://api.brightdata.com/request
Docs: https://docs.brightdata.com
"""
import os
import httpx


class BrightData:
    def __init__(self):
        self._api_key = os.environ["BRIGHTDATA_API_KEY"]

    async def scrape(self, url: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.brightdata.com/request",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"url": url, "format": "markdown"},
            )
            resp.raise_for_status()
        return {"url": url, "content": resp.text}

    async def scrape_dataset(self, urls: list[str]) -> list[dict]:
        results = []
        for url in urls:
            try:
                results.append(await self.scrape(url))
            except Exception as e:
                results.append({"url": url, "error": str(e)})
        return results
