import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.store import InMemoryWorkspaceStore


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app(InMemoryWorkspaceStore())) as test_client:
        yield test_client


def create_workspace(client: TestClient) -> str:
    response = client.post("/workspaces", json={"name": "Hackathon Workspace"})
    assert response.status_code == 201
    return response.json()["id"]


def test_health_check(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "store": "memory"}


def test_prompt_acquires_lock_and_updates_workspace_state(client: TestClient) -> None:
    workspace_id = create_workspace(client)

    response = client.post(
        f"/workspaces/{workspace_id}/prompts",
        json={
            "member_id": "Member A",
            "prompt": "modify function_login()",
            "task_type": "coding",
            "targets": [{"scope_type": "symbol", "scope_key": "src/auth.py::function_login"}],
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["route"]["provider"] == "KimiAI"
    assert body["locks"][0]["owner_member_id"] == "Member A"

    state = client.get(f"/workspaces/{workspace_id}/state").json()
    assert len(state["locks"]) == 1
    assert state["locks"][0]["target"]["scope_key"] == "src/auth.py::function_login"
    assert state["sessions"][0]["status"] == "running"


def test_conflicting_prompt_returns_warning_before_proceeding(client: TestClient) -> None:
    workspace_id = create_workspace(client)
    target = {"scope_type": "symbol", "scope_key": "src/auth.py::function_login"}

    first = client.post(
        f"/workspaces/{workspace_id}/prompts",
        json={"member_id": "Member A", "prompt": "modify login", "targets": [target]},
    )
    assert first.status_code == 202

    conflict = client.post(
        f"/workspaces/{workspace_id}/prompts",
        json={"member_id": "Member B", "prompt": "also modify login", "targets": [target]},
    )

    assert conflict.status_code == 409
    body = conflict.json()
    assert body["status"] == "conflict"
    assert body["conflicts"][0]["owner_member_id"] == "Member A"
    assert body["conflicts"][0]["target"] == target


def test_override_replaces_existing_lock(client: TestClient) -> None:
    workspace_id = create_workspace(client)
    target = {"scope_type": "file", "scope_key": "src/auth.py"}

    first = client.post(
        f"/workspaces/{workspace_id}/prompts",
        json={"member_id": "Member A", "prompt": "modify auth file", "targets": [target]},
    )
    assert first.status_code == 202

    override = client.post(
        f"/workspaces/{workspace_id}/prompts",
        json={
            "member_id": "Member B",
            "prompt": "urgent auth file update",
            "targets": [target],
            "override_conflicts": True,
        },
    )

    assert override.status_code == 202
    state = client.get(f"/workspaces/{workspace_id}/state").json()
    assert len(state["locks"]) == 1
    assert state["locks"][0]["owner_member_id"] == "Member B"


def test_completing_session_releases_locks(client: TestClient) -> None:
    workspace_id = create_workspace(client)
    target = {"scope_type": "file", "scope_key": "classifier.py"}

    prompt = client.post(
        f"/workspaces/{workspace_id}/prompts",
        json={
            "member_id": "Member C",
            "prompt": "train classifier",
            "task_type": "ml",
            "targets": [target],
        },
    )
    assert prompt.status_code == 202
    session_id = prompt.json()["session_id"]
    assert prompt.json()["route"]["provider"] == "Nosana"

    complete = client.post(
        f"/workspaces/{workspace_id}/sessions/{session_id}/complete",
        json={"result_summary": "Classifier trained in sandbox.", "patch": "diff --git ..."},
    )

    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"

    state = client.get(f"/workspaces/{workspace_id}/state").json()
    assert state["locks"] == []
    assert state["sessions"][0]["result_summary"] == "Classifier trained in sandbox."

