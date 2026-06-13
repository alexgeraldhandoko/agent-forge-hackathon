import pytest
from fakeredis.aioredis import FakeRedis

from app.models import CompleteSessionRequest, PromptRequest, Target, WorkspaceCreate
from app.store import RedisWorkspaceStore


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def store() -> RedisWorkspaceStore:
    redis = FakeRedis(decode_responses=True)
    workspace_store = RedisWorkspaceStore(redis, namespace="test-ai-workspace")
    yield workspace_store
    await workspace_store.close()


async def test_redis_store_acquires_conflicts_and_releases_locks(store: RedisWorkspaceStore) -> None:
    workspace = await store.create_workspace(WorkspaceCreate(name="Redis Workspace"))
    target = Target(scope_type="symbol", scope_key="src/auth.py::function_login")

    first = await store.submit_prompt(
        workspace.id,
        PromptRequest(member_id="Member A", prompt="modify function_login()", targets=[target]),
    )

    assert first is not None
    assert first.status == "accepted"
    assert first.route is not None
    assert first.route.provider == "KimiAI"
    assert first.session_id is not None

    conflict = await store.submit_prompt(
        workspace.id,
        PromptRequest(member_id="Member B", prompt="also modify function_login()", targets=[target]),
    )

    assert conflict is not None
    assert conflict.status == "conflict"
    assert conflict.conflicts[0].owner_member_id == "Member A"

    completed = await store.complete_session(
        workspace.id,
        first.session_id,
        CompleteSessionRequest(result_summary="Patch validated."),
    )

    assert completed is not None
    assert completed.status == "completed"

    state = await store.get_state(workspace.id)
    assert state is not None
    assert state.locks == []
    assert len(state.events) >= 4


async def test_redis_store_override_replaces_lock_owner(store: RedisWorkspaceStore) -> None:
    workspace = await store.create_workspace(WorkspaceCreate(name="Override Workspace"))
    target = Target(scope_type="file", scope_key="src/auth.py")

    first = await store.submit_prompt(
        workspace.id,
        PromptRequest(member_id="Member A", prompt="modify auth", targets=[target]),
    )
    assert first is not None
    assert first.status == "accepted"

    override = await store.submit_prompt(
        workspace.id,
        PromptRequest(
            member_id="Member B",
            prompt="take over auth changes",
            targets=[target],
            override_conflicts=True,
        ),
    )

    assert override is not None
    assert override.status == "accepted"

    state = await store.get_state(workspace.id)
    assert state is not None
    assert len(state.locks) == 1
    assert state.locks[0].owner_member_id == "Member B"

