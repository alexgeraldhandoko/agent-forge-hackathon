from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))


async def scrape_url(url: str) -> dict[str, Any]:
    api_key = os.getenv("BRIGHTDATA_API_KEY")
    if not api_key:
        return await direct_fetch(url, "Bright Data key not configured; used direct fetch.")

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                "https://api.brightdata.com/request",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "zone": brightdata_zone(),
                    "url": url,
                    "format": "raw",
                },
            )
            response.raise_for_status()
            return {
                "url": url,
                "source": "Bright Data",
                "content": extract_brightdata_body(response),
                "status": response.status_code,
            }
    except Exception as exc:
        return await direct_fetch(url, f"Bright Data unavailable; used direct fetch. Error: {exc}")


async def scrape_markdown(url: str) -> str:
    result = await scrape_url(url)
    return result["content"]


def brightdata_zone() -> str:
    return os.getenv("BRIGHTDATA_UNLOCKER_ZONE") or os.getenv("BRIGHTDATA_ZONE", "web_unlocker1")


def extract_brightdata_body(response: httpx.Response) -> str:
    text = response.text
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return text
    if isinstance(payload, dict):
        body = payload.get("body")
        if isinstance(body, str):
            return body
    return text


async def direct_fetch(url: str, reason: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "AI-Workspace-MVP/1.0"})
            response.raise_for_status()
            content = response.text
            status = response.status_code
    except Exception as exc:
        content = f"Unable to scrape {url}.\n\n{reason}\nDirect fetch error: {exc}"
        status = 0
    return {
        "url": url,
        "source": reason,
        "content": content,
        "status": status,
    }
