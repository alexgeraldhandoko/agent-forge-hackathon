"""
In-memory lock map with Supabase persistence via ContextStore.
Used by ConflictChecker. Kept in sync via WebSocket broadcasts.
"""
from .store import ContextStore


class LockMap:
    def __init__(self, store: ContextStore):
        self._store = store
        self._cache: dict[str, str] = {}

    def refresh(self):
        self._cache = self._store.get_all_locks()

    def acquire(self, target: str, member: str) -> bool:
        existing = self._cache.get(target)
        if existing and existing != member:
            return False
        self._store.acquire_lock(target, member)
        self._cache[target] = member
        return True

    def release(self, target: str, member: str) -> bool:
        released = self._store.release_lock(target, member)
        if released:
            self._cache.pop(target, None)
        return released

    def owner(self, target: str) -> str | None:
        return self._cache.get(target)

    def snapshot(self) -> dict[str, str]:
        return dict(self._cache)
