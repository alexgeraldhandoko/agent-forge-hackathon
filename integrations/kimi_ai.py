"""
KimiAI direct client — OpenAI-compatible SDK with base_url override.
In production, calls go through TokenRouter. Use this for direct testing only.
Docs: https://platform.moonshot.cn/docs
"""
import os
from openai import AsyncOpenAI

SYSTEM_PROMPT = """You are a collaborative AI coding agent inside a shared multi-member workspace.
You have access to the full file context, lock map (who owns what), and recent action log.
Respect locked targets — do not modify them unless explicitly told to override.
Return structured responses: { "explanation": str, "code": str | null, "files_modified": list[str] }
"""


class KimiAI:
    def __init__(self):
        self._client = AsyncOpenAI(
            api_key=os.environ["KIMI_API_KEY"],
            base_url=os.environ.get("KIMI_API_BASE", "https://api.moonshot.cn/v1"),
        )
        self._model = os.environ.get("KIMI_MODEL", "moonshot-v1-128k")

    async def complete(self, prompt: str, context: dict, member: str) -> dict:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self._build_user_message(prompt, context, member)},
            ],
        )
        content = response.choices[0].message.content
        return {"raw": content, "code": None, "explanation": content, "files_modified": []}

    def _build_user_message(self, prompt: str, context: dict, member: str) -> str:
        return (
            f"Member: {member}\n"
            f"Task: {prompt}\n\n"
            f"Workspace context:\n"
            f"Files: {[f['path'] for f in context['files']]}\n"
            f"Locks: {context['locks']}\n"
            f"Recent actions: {context['recent_actions'][:5]}"
        )
