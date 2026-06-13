"""
TokenRouter — single OpenAI-compatible client that routes all LLM calls.

All text completion tasks go through tokenrouter.io; model name determines
which underlying service handles the request:
  code / debug / review  → model="moonshot-v1-128k"  (KimiAI via TokenRouter)
  scrape                 → BrightData → model="moonshot-v1-128k"
  image / document       → SenseNova images.generate() directly (images API, not chat)
  ml_train / compute     → Nosana GPU (not an LLM call)
"""
import os
from enum import Enum

from openai import AsyncOpenAI

from integrations.sense_nova import SenseNova
from integrations.nosana import Nosana
from integrations.bright_data import BrightData
from integrations.daytona import Daytona
from shared_context.store import ContextStore

SYSTEM_PROMPT = """You are a collaborative AI coding agent inside a shared multi-member workspace.
You have access to the full file context, lock map (who owns what), and recent action log.
Respect locked targets — do not modify them unless explicitly told to override.
Return structured responses: { "explanation": str, "code": str | null, "files_modified": list[str] }
"""


class TaskType(str, Enum):
    CODE = "code"
    DEBUG = "debug"
    REVIEW = "review"
    IMAGE = "image"
    DOCUMENT = "document"
    ML_TRAIN = "ml_train"
    COMPUTE = "compute"
    SCRAPE = "scrape"


class TokenRouter:
    def __init__(self, store: ContextStore):
        self._store = store
        self._client = AsyncOpenAI(
            api_key=os.environ["TOKENROUTER_API_KEY"],
            base_url=os.environ.get("TOKENROUTER_API_BASE", "https://tokenrouter.io/v1"),
        )
        self._sensenova = SenseNova()
        self._nosana = Nosana()
        self._brightdata = BrightData()
        self._daytona = Daytona()

    def _build_context(self) -> dict:
        return {
            "files": self._store.list_files(),
            "locks": self._store.get_all_locks(),
            "recent_actions": self._store.get_recent_actions(limit=20),
        }

    def _build_user_message(self, prompt: str, context: dict, member: str) -> str:
        return (
            f"Member: {member}\n"
            f"Task: {prompt}\n\n"
            f"Workspace context:\n"
            f"Files: {[f['path'] for f in context['files']]}\n"
            f"Locks: {context['locks']}\n"
            f"Recent actions: {context['recent_actions'][:5]}"
        )

    async def _chat(self, prompt: str, context: dict, member: str, model: str) -> dict:
        response = await self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self._build_user_message(prompt, context, member)},
            ],
        )
        content = response.choices[0].message.content
        return {"raw": content, "code": None, "explanation": content, "files_modified": []}

    async def route(self, task_type: TaskType, prompt: str, member: str, **kwargs) -> dict:
        ctx = self._build_context()

        if task_type in (TaskType.CODE, TaskType.DEBUG, TaskType.REVIEW):
            result = await self._chat(prompt, ctx, member, model="moonshot-v1-128k")
            if task_type == TaskType.CODE and result.get("code"):
                result["sandbox"] = await self._daytona.run(result["code"])
            return result

        if task_type in (TaskType.IMAGE, TaskType.DOCUMENT):
            return await self._sensenova.generate(prompt=prompt, member=member)

        if task_type in (TaskType.ML_TRAIN, TaskType.COMPUTE):
            return await self._nosana.submit_job(member=member, **kwargs)

        if task_type == TaskType.SCRAPE:
            scraped = await self._brightdata.scrape(url=kwargs["url"])
            enriched = f"{prompt}\n\nScraped content:\n{scraped['content']}"
            return await self._chat(enriched, ctx, member, model="moonshot-v1-128k")

        raise ValueError(f"Unknown task type: {task_type}")
