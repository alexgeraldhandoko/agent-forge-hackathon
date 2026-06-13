from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .conflict import check_conflicts
from .context_store import WorkspaceStore, get_workspace
from .router import detect_task_type, route_prompt
from .sandbox import run_daytona, submit_nosana_job

load_dotenv(Path(__file__).with_name(".env"))

app = FastAPI(title="AI Workspace MVP")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

connections: dict[str, set[WebSocket]] = {}
store_locks: dict[str, asyncio.Lock] = {}
AGENT_DEMO_LATENCY_SECONDS = 1.25


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/provider-status")
async def provider_status() -> dict[str, bool]:
    return {
        "tokenrouter": bool(os.getenv("TOKENROUTER_API_KEY")),
        "kimi": bool(os.getenv("KIMI_API_KEY")),
        "sensenova": bool(os.getenv("SENSENOVA_API_KEY")),
        "brightdata": bool(os.getenv("BRIGHTDATA_API_KEY")),
        "brightdata_zone": bool(os.getenv("BRIGHTDATA_ZONE")),
        "daytona": bool(os.getenv("DAYTONA_API_KEY")),
        "nosana": bool(os.getenv("NOSANA_API_KEY")),
    }


@app.get("/api/workspaces/{workspace_id}")
async def get_workspace_snapshot(workspace_id: str) -> dict[str, Any]:
    return get_workspace(workspace_id).snapshot()


@app.post("/api/workspaces/{workspace_id}/reset")
async def reset_workspace(workspace_id: str) -> dict[str, Any]:
    store = get_workspace(workspace_id)
    store.reset()
    payload = {"type": "workspace_reset", "snapshot": store.snapshot()}
    await broadcast(workspace_id, payload)
    return store.snapshot()


@app.websocket("/ws/{workspace_id}/{username}")
async def websocket_endpoint(websocket: WebSocket, workspace_id: str, username: str) -> None:
    await websocket.accept()
    store = get_workspace(workspace_id)
    store.join(username)
    connections.setdefault(workspace_id, set()).add(websocket)
    store_locks.setdefault(workspace_id, asyncio.Lock())

    await websocket.send_json({"type": "sync", **store.snapshot()})
    await broadcast(workspace_id, {"type": "user_joined", "user": username, "members": sorted(store.members.keys())})

    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if message.get("type") == "reset_workspace":
                store.reset()
                await broadcast(workspace_id, {"type": "workspace_reset", "snapshot": store.snapshot()})
                continue
            if message.get("type") != "prompt":
                await websocket.send_json({"type": "error", "message": "Unknown message type."})
                continue
            await handle_prompt(workspace_id, store, username, message)
    except (WebSocketDisconnect, RuntimeError):
        store.leave(username)
        connections.get(workspace_id, set()).discard(websocket)
        await broadcast(workspace_id, {"type": "user_left", "user": username, "members": sorted(store.members.keys())})


async def handle_prompt(
    workspace_id: str,
    store: WorkspaceStore,
    username: str,
    message: dict[str, Any],
) -> None:
    prompt = str(message.get("prompt", "")).strip()
    if not prompt:
        await broadcast(workspace_id, {"type": "error", "message": "Prompt cannot be empty."})
        return

    selected_model = message.get("model")
    override = bool(message.get("override", False))

    async with store_locks[workspace_id]:
        conflict = check_conflicts(store, prompt, username, override)
        if conflict.blocked:
            await broadcast(
                workspace_id,
                {
                    "type": "conflict",
                    "user": username,
                    "prompt": prompt,
                    "functions": conflict.functions,
                    "locked_by": conflict.locked_by,
                    "message": conflict.message,
                },
            )
            return
        for function_name in conflict.functions:
            store.lock(function_name, username)

    await broadcast(workspace_id, {"type": "lock_update", "lock_map": store.lock_map})
    await broadcast(workspace_id, {"type": "agent_thinking", "user": username, "prompt": prompt})
    await asyncio.sleep(AGENT_DEMO_LATENCY_SECONDS)

    task_type = detect_task_type(prompt, selected_model)
    locked_functions = conflict.functions
    try:
        result = await route_prompt(prompt, username, store, task_type)
        files = result.get("files", {})
        run_output = ""

        if files:
            if result.get("skip_execution"):
                run_output = "Stored in shared workspace."
            else:
                run_result = await run_daytona({**store.files, **files})
                run_output = "\n".join(
                    part for part in [run_result.get("stdout", ""), run_result.get("stderr", "")] if part
                )
            store.update_files(files)

        if task_type == "train":
            nosana_result = await submit_nosana_job(result.get("nosana_script", "echo training"))
            run_output = "\n".join(
                part
                for part in [
                    run_output,
                    nosana_result.get("stdout", ""),
                    nosana_result.get("stderr", ""),
                ]
                if part
            )

        functions_modified = result.get("functions_modified", locked_functions)
        action = store.add_action(
            username,
            prompt,
            functions_modified,
            result.get("explanation", "Updated workspace."),
            sorted(files.keys()),
            run_output,
        )
        await broadcast(
            workspace_id,
            {
                "type": "file_update",
                "user": username,
                "prompt": prompt,
                "files": files,
                "explanation": action["explanation"],
                "assistant_message": result.get("assistant_message", action["explanation"]),
                "functions_modified": functions_modified,
                "run_output": run_output,
                "provider": result.get("provider", "unknown"),
                "route": result.get("route", {}),
                "snapshot": store.snapshot(),
            },
        )
    except Exception as exc:
        await broadcast(workspace_id, {"type": "error", "message": str(exc)})
    finally:
        async with store_locks[workspace_id]:
            for function_name in locked_functions:
                store.unlock(function_name, username)
        await broadcast(workspace_id, {"type": "lock_update", "lock_map": store.lock_map})


async def broadcast(workspace_id: str, payload: dict[str, Any]) -> None:
    dead: list[WebSocket] = []
    for websocket in connections.get(workspace_id, set()).copy():
        try:
            await websocket.send_json(payload)
        except Exception:
            dead.append(websocket)
    for websocket in dead:
        connections.get(workspace_id, set()).discard(websocket)
