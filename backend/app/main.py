from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.models import (
    ActionEvent,
    AgentSession,
    CompleteSessionRequest,
    PromptRequest,
    PromptResponse,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceState,
)
from app.settings import build_store_from_env
from app.store import StoreMutexTimeoutError, WorkspaceStore


class WebSocketHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, workspace_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(workspace_id, set()).add(websocket)

    def disconnect(self, workspace_id: str, websocket: WebSocket) -> None:
        self._connections.get(workspace_id, set()).discard(websocket)

    async def broadcast(self, workspace_id: str, payload: dict) -> None:
        stale_connections: list[WebSocket] = []
        for websocket in self._connections.get(workspace_id, set()):
            try:
                await websocket.send_json(payload)
            except RuntimeError:
                stale_connections.append(websocket)

        for websocket in stale_connections:
            self.disconnect(workspace_id, websocket)


def create_app(workspace_store: WorkspaceStore | None = None) -> FastAPI:
    store = workspace_store or build_store_from_env()
    hub = WebSocketHub()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await store.close()

    app = FastAPI(title="AI Workspace Backend", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        try:
            await store.ping()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"{store.name} store unavailable.",
            ) from exc

        return {"status": "ok", "store": store.name}

    @app.post("/workspaces", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
    async def create_workspace(request: WorkspaceCreate) -> WorkspaceResponse:
        return await store.create_workspace(request)

    @app.get("/workspaces/{workspace_id}/state", response_model=WorkspaceState)
    async def get_workspace_state(workspace_id: str) -> WorkspaceState:
        state = await store.get_state(workspace_id)
        if state is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
        return state

    @app.post("/workspaces/{workspace_id}/prompts", response_model=PromptResponse)
    async def submit_prompt(workspace_id: str, request: PromptRequest) -> JSONResponse:
        try:
            result = await store.submit_prompt(workspace_id, request)
        except StoreMutexTimeoutError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Workspace is busy. Retry the request shortly.",
            ) from exc

        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")

        response_status = status.HTTP_409_CONFLICT if result.status == "conflict" else status.HTTP_202_ACCEPTED
        await hub.broadcast(workspace_id, {"type": "prompt.updated", "payload": jsonable_encoder(result)})
        return JSONResponse(status_code=response_status, content=jsonable_encoder(result))

    @app.post(
        "/workspaces/{workspace_id}/sessions/{session_id}/complete",
        response_model=AgentSession,
    )
    async def complete_session(
        workspace_id: str,
        session_id: str,
        request: CompleteSessionRequest,
    ) -> AgentSession:
        try:
            session = await store.complete_session(workspace_id, session_id, request)
        except StoreMutexTimeoutError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Workspace is busy. Retry the request shortly.",
            ) from exc

        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace or session not found.")

        await hub.broadcast(workspace_id, {"type": "session.completed", "payload": jsonable_encoder(session)})
        return session

    @app.get("/workspaces/{workspace_id}/events", response_model=list[ActionEvent])
    async def list_events(workspace_id: str) -> list[ActionEvent]:
        events = await store.list_events(workspace_id)
        if events is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
        return events

    @app.websocket("/workspaces/{workspace_id}/ws")
    async def workspace_websocket(workspace_id: str, websocket: WebSocket) -> None:
        workspace = await store.get_workspace(workspace_id)
        if workspace is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await hub.connect(workspace_id, websocket)
        try:
            await websocket.send_json({"type": "connected", "workspace_id": workspace_id})
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            hub.disconnect(workspace_id, websocket)

    return app


app = create_app()

