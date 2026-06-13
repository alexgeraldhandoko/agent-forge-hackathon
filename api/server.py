from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from shared_context import ContextStore, LockMap, ActionLog, Broadcaster
from agents import MemberAgent
from token_router import TaskType

app = FastAPI(title="AI Workspace")

# Singletons shared across all requests
_store = ContextStore()
_lock_map = LockMap(_store)
_action_log = ActionLog(_store)
_broadcaster = Broadcaster()


def _get_agent(member: str) -> MemberAgent:
    return MemberAgent(
        member=member,
        store=_store,
        lock_map=_lock_map,
        action_log=_action_log,
        broadcaster=_broadcaster,
    )


class TaskRequest(BaseModel):
    member: str
    task_type: TaskType
    prompt: str
    target: str
    override_conflict: bool = False


@app.post("/task")
async def submit_task(req: TaskRequest):
    agent = _get_agent(req.member)
    return await agent.submit(
        task_type=req.task_type,
        prompt=req.prompt,
        target=req.target,
        override_conflict=req.override_conflict,
    )


@app.get("/locks")
def get_locks():
    _lock_map.refresh()
    return _lock_map.snapshot()


@app.get("/actions")
def get_actions(limit: int = 50):
    return _action_log.recent(limit=limit)


@app.get("/files")
def list_files():
    return _store.list_files()


@app.websocket("/ws/{member}")
async def websocket_endpoint(websocket: WebSocket, member: str):
    await _broadcaster.connect(member, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _broadcaster.disconnect(member)
