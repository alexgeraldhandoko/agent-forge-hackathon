"""
MemberAgent — the per-member facade that orchestrates the full pipeline:
  1. ConflictChecker gates the action
  2. TokenRouter dispatches to the right model with full workspace context
  3. ActionLog records what happened
  4. Broadcaster pushes the update to all connected members
"""
from conflict_checker import ConflictChecker
from token_router import TokenRouter, TaskType
from shared_context import ContextStore, LockMap, ActionLog, Broadcaster


class MemberAgent:
    def __init__(
        self,
        member: str,
        store: ContextStore,
        lock_map: LockMap,
        action_log: ActionLog,
        broadcaster: Broadcaster,
    ):
        self.member = member
        self._store = store
        self._lock_map = lock_map
        self._checker = ConflictChecker(lock_map)
        self._router = TokenRouter(store)
        self._log = action_log
        self._broadcaster = broadcaster

    async def submit(
        self,
        task_type: TaskType,
        prompt: str,
        target: str,
        override_conflict: bool = False,
        **kwargs,
    ) -> dict:
        conflict = self._checker.check(target, self.member)
        if conflict.conflict and not override_conflict:
            return {"status": "conflict", "detail": conflict.message, "owner": conflict.owner}

        acquired = self._checker.acquire(target, self.member)
        if not acquired and not override_conflict:
            return {"status": "conflict", "detail": f"Could not lock '{target}'."}

        try:
            result = await self._router.route(
                task_type=task_type, prompt=prompt, member=self.member, **kwargs
            )
        finally:
            self._checker.release(target, self.member)

        self._log.record(
            member=self.member,
            action=task_type.value,
            target=target,
            payload={"prompt": prompt, "result_summary": str(result)[:200]},
        )

        await self._broadcaster.broadcast(
            event="agent_action",
            data={
                "member": self.member,
                "task_type": task_type.value,
                "target": target,
                "locks": self._lock_map.snapshot(),
            },
        )

        return {"status": "ok", "result": result}
