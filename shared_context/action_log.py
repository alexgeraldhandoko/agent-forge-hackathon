from .store import ContextStore


class ActionLog:
    def __init__(self, store: ContextStore):
        self._store = store

    def record(self, member: str, action: str, target: str, payload: dict = None):
        return self._store.log_action(member, action, target, payload)

    def recent(self, limit: int = 50) -> list[dict]:
        return self._store.get_recent_actions(limit)
