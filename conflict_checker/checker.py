"""
Conflict Checker — gates every agent action behind a lock check.

A "target" is either a file path ("auth/login.py") or a named symbol
("function_login"). Granularity is up to the caller.
"""
from dataclasses import dataclass
from shared_context.lock_map import LockMap


@dataclass
class ConflictResult:
    conflict: bool
    target: str
    owner: str | None = None
    message: str = ""


class ConflictChecker:
    def __init__(self, lock_map: LockMap):
        self._locks = lock_map

    def check(self, target: str, member: str) -> ConflictResult:
        """Return a ConflictResult before the agent touches `target`."""
        self._locks.refresh()
        owner = self._locks.owner(target)
        if owner and owner != member:
            return ConflictResult(
                conflict=True,
                target=target,
                owner=owner,
                message=f"'{target}' is locked by {owner}. Wait or override.",
            )
        return ConflictResult(conflict=False, target=target)

    def acquire(self, target: str, member: str) -> bool:
        """Atomically lock `target` for `member`. Returns False on conflict."""
        return self._locks.acquire(target, member)

    def release(self, target: str, member: str) -> bool:
        return self._locks.release(target, member)

    def check_and_acquire(self, target: str, member: str) -> ConflictResult:
        """Combined check + acquire. Use this for the standard gating flow."""
        result = self.check(target, member)
        if not result.conflict:
            acquired = self.acquire(target, member)
            if not acquired:
                owner = self._locks.owner(target)
                return ConflictResult(
                    conflict=True,
                    target=target,
                    owner=owner,
                    message=f"Race condition: '{target}' was just locked by {owner}.",
                )
        return result
