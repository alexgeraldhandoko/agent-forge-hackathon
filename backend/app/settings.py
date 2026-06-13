import os

from redis.asyncio import from_url

from app.brightdata import BrightDataClient, WebResearcher
from app.kimi import KimiClient, KimiProvider
from app.store import InMemoryWorkspaceStore, RedisWorkspaceStore, WorkspaceStore
from app.tokenrouter import TokenRouterClient


def build_store_from_env() -> WorkspaceStore:
    backend = os.getenv("AI_WORKSPACE_STORE", "redis").lower()

    if backend == "memory":
        return InMemoryWorkspaceStore()

    if backend != "redis":
        raise ValueError("AI_WORKSPACE_STORE must be 'redis' or 'memory'.")

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis = from_url(redis_url, decode_responses=True)
    return RedisWorkspaceStore(redis)


def build_model_client_from_env() -> KimiProvider:
    configured_gateway = os.getenv("MODEL_GATEWAY")
    gateway = (
        configured_gateway.lower()
        if configured_gateway
        else "tokenrouter"
        if os.getenv("TOKENROUTER_API_KEY")
        else "kimi"
    )

    if gateway in {"kimi", "kimiai", "moonshot"}:
        return KimiClient.from_env()

    if gateway in {"tokenrouter", "token-router"}:
        return TokenRouterClient.from_env()

    raise ValueError("MODEL_GATEWAY must be 'tokenrouter' or 'kimi'.")


def build_fallback_model_client_from_env(primary_name: str | None = None) -> KimiProvider | None:
    primary = primary_name or build_model_client_from_env().name
    if primary != "tokenrouter":
        return None

    if not (os.getenv("MOONSHOT_API_KEY") or os.getenv("KIMI_API_KEY")):
        return None

    return KimiClient.from_env()


def build_web_researcher_from_env() -> WebResearcher:
    return BrightDataClient.from_env()
