"""
SenseNova — image generation via OpenAI-compatible images.generate().
Called directly (not through TokenRouter) since it uses the images API, not chat completions.
Docs: https://platform.sensenova.cn
"""
import os
from openai import AsyncOpenAI


class SenseNova:
    def __init__(self):
        self._client = AsyncOpenAI(
            api_key=os.environ["SENSENOVA_API_KEY"],
            base_url=os.environ.get("SENSENOVA_API_BASE", "https://api.sensenova.cn/v1"),
        )
        self._model = os.environ.get("SENSENOVA_MODEL", "nova-ptx-xl")

    async def generate(self, prompt: str, member: str) -> dict:
        response = await self._client.images.generate(
            model=self._model,
            prompt=prompt,
            n=1,
            size="1024x1024",
        )
        return {"image_url": response.data[0].url, "member": member}
