import os

from redis.asyncio import from_url

from app.store import InMemoryWorkspaceStore, RedisWorkspaceStore, WorkspaceStore


def build_store_from_env() -> WorkspaceStore:
    backend = os.getenv("AI_WORKSPACE_STORE", "redis").lower()

    if backend == "memory":
        return InMemoryWorkspaceStore()

    if backend != "redis":
        raise ValueError("AI_WORKSPACE_STORE must be 'redis' or 'memory'.")

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis = from_url(redis_url, decode_responses=True)
    return RedisWorkspaceStore(redis)
