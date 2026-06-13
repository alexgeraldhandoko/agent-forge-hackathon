from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any


class WorkspaceStore:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.lock_map: dict[str, str] = {}
        self.action_log: list[dict[str, Any]] = []
        self.members: dict[str, int] = {}
        self.assets: dict[str, str] = {}

    def get_context_string(self) -> str:
        file_blocks = "\n\n".join(
            f"### {path}\n```python\n{content}\n```"
            for path, content in sorted(self.files.items())
        )
        return (
            f"Files:\n{file_blocks or '(no files yet)'}\n\n"
            f"Lock map:\n{json.dumps(self.lock_map, indent=2)}\n\n"
            f"Recent actions:\n{json.dumps(self.action_log[-5:], indent=2)}"
        )

    def lock(self, function_name: str, user: str) -> None:
        self.lock_map[function_name] = user

    def unlock(self, function_name: str, user: str | None = None) -> None:
        if function_name not in self.lock_map:
            return
        if user is None or self.lock_map[function_name] == user:
            self.lock_map.pop(function_name, None)

    def update_files(self, new_files: dict[str, str]) -> None:
        for path, content in new_files.items():
            clean_path = path.strip().lstrip("/")
            if clean_path:
                self.files[clean_path] = content

    def extract_functions(self, file_content: str) -> list[str]:
        return re.findall(r"def\s+(\w+)\s*\(", file_content)

    def add_action(
        self,
        user: str,
        prompt: str,
        changed_functions: list[str],
        explanation: str,
        files: list[str],
        run_output: str = "",
    ) -> dict[str, Any]:
        entry = {
            "user": user,
            "prompt": prompt,
            "changed_functions": changed_functions,
            "explanation": explanation,
            "files": files,
            "run_output": run_output,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.action_log.append(entry)
        self.action_log = self.action_log[-50:]
        return entry

    def join(self, user: str) -> None:
        self.members[user] = self.members.get(user, 0) + 1

    def leave(self, user: str) -> None:
        if user not in self.members:
            return
        self.members[user] -= 1
        if self.members[user] <= 0:
            self.members.pop(user, None)

    def reset(self) -> None:
        self.files.clear()
        self.lock_map.clear()
        self.action_log.clear()
        self.assets.clear()

    def snapshot(self) -> dict[str, Any]:
        return {
            "files": self.files,
            "lock_map": self.lock_map,
            "action_log": self.action_log,
            "members": sorted(self.members.keys()),
            "assets": self.assets,
        }


workspaces: dict[str, WorkspaceStore] = {}


def get_workspace(workspace_id: str) -> WorkspaceStore:
    if workspace_id not in workspaces:
        workspaces[workspace_id] = WorkspaceStore()
    return workspaces[workspace_id]
