from __future__ import annotations

import re
from dataclasses import dataclass

from .context_store import WorkspaceStore


@dataclass
class ConflictResult:
    blocked: bool
    functions: list[str]
    locked_by: str | None = None
    message: str | None = None


def extract_target_functions(prompt: str) -> list[str]:
    names: set[str] = set()
    prompt_lower = prompt.lower()

    for match in re.findall(r"\b([a-zA-Z_][\w]*)\s*\(", prompt):
        if match not in {"if", "for", "while", "print", "return"}:
            names.add(match)

    for match in re.findall(r"\bdef\s+([a-zA-Z_][\w]*)", prompt):
        names.add(match)

    for match in re.findall(r"\b(function_[a-zA-Z_][\w]*)\b", prompt):
        names.add(match)

    simple_feature_aliases = {
        "login": "function_login",
        "auth": "function_login",
        "classifier": "train_classifier",
        "training": "train_classifier",
        "train": "train_classifier",
    }
    for word, function_name in simple_feature_aliases.items():
        if re.search(rf"\b{re.escape(word)}\b", prompt_lower):
            names.add(function_name)

    return sorted(names)


def check_conflicts(
    store: WorkspaceStore, prompt: str, user: str, override: bool = False
) -> ConflictResult:
    functions = extract_target_functions(prompt)
    if override:
        return ConflictResult(blocked=False, functions=functions)

    for function_name in functions:
        locked_by = store.lock_map.get(function_name)
        if locked_by and locked_by != user:
            return ConflictResult(
                blocked=True,
                functions=[function_name],
                locked_by=locked_by,
                message=(
                    f"{locked_by} is currently modifying {function_name}. "
                    "Wait or override?"
                ),
            )

    return ConflictResult(blocked=False, functions=functions)
