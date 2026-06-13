"""
Shared Context Store — Supabase-backed source of truth for the workspace.

Supabase tables required:
  - workspace_files  (id, path, content, updated_at, updated_by)
  - lock_map         (id, target, member, locked_at)
  - action_log       (id, member, action, target, payload, created_at)
  - assets           (id, name, type, url, created_at)
"""
import os
from supabase import create_client, Client


class ContextStore:
    def __init__(self):
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        self._db: Client = create_client(url, key)

    # ── Files ──────────────────────────────────────────────────────────────

    def get_file(self, path: str) -> dict | None:
        res = self._db.table("workspace_files").select("*").eq("path", path).execute()
        return res.data[0] if res.data else None

    def upsert_file(self, path: str, content: str, member: str) -> dict:
        row = {"path": path, "content": content, "updated_by": member}
        res = (
            self._db.table("workspace_files")
            .upsert(row, on_conflict="path")
            .execute()
        )
        return res.data[0]

    def list_files(self) -> list[dict]:
        return self._db.table("workspace_files").select("path,updated_by,updated_at").execute().data

    # ── Lock Map ───────────────────────────────────────────────────────────

    def get_lock(self, target: str) -> dict | None:
        res = self._db.table("lock_map").select("*").eq("target", target).execute()
        return res.data[0] if res.data else None

    def acquire_lock(self, target: str, member: str) -> dict:
        row = {"target": target, "member": member}
        res = (
            self._db.table("lock_map")
            .upsert(row, on_conflict="target")
            .execute()
        )
        return res.data[0]

    def release_lock(self, target: str, member: str) -> bool:
        res = (
            self._db.table("lock_map")
            .delete()
            .eq("target", target)
            .eq("member", member)
            .execute()
        )
        return bool(res.data)

    def get_all_locks(self) -> dict[str, str]:
        rows = self._db.table("lock_map").select("target,member").execute().data
        return {r["target"]: r["member"] for r in rows}

    # ── Action Log ─────────────────────────────────────────────────────────

    def log_action(self, member: str, action: str, target: str, payload: dict = None) -> dict:
        row = {"member": member, "action": action, "target": target, "payload": payload or {}}
        return self._db.table("action_log").insert(row).execute().data[0]

    def get_recent_actions(self, limit: int = 50) -> list[dict]:
        return (
            self._db.table("action_log")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )
