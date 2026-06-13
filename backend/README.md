# AI Workspace Backend

Minimal FastAPI backend for a collaborative AI workspace.

The MVP implements:

- workspace creation
- prompt submission
- file/symbol lock acquisition
- conflict warnings
- conflict override
- model routing through a TokenRouter-style policy
- session completion and lock release
- workspace state inspection
- WebSocket update channel

Runtime state is Redis-backed by default. Redis stores workspaces, active lock leases, agent sessions, and recent action events. The in-memory store still exists for tests and quick local experiments through `AI_WORKSPACE_STORE=memory`.

## Run locally

Start Redis first:

```bash
docker run --rm -p 6379:6379 redis:7
```

Then start the API:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
REDIS_URL=redis://localhost:6379/0 uvicorn app.main:app --reload
```

Open the API docs at:

```txt
http://127.0.0.1:8000/docs
```

For an in-memory local run without Redis:

```bash
AI_WORKSPACE_STORE=memory uvicorn app.main:app --reload
```

## Run tests

```bash
cd backend
pytest
```

## Example flow

Create a workspace:

```bash
curl -X POST http://127.0.0.1:8000/workspaces \
  -H "Content-Type: application/json" \
  -d '{"name":"Hackathon Workspace"}'
```

Submit a coding prompt:

```bash
curl -X POST http://127.0.0.1:8000/workspaces/<workspace_id>/prompts \
  -H "Content-Type: application/json" \
  -d '{
    "member_id": "Member A",
    "prompt": "modify function_login()",
    "task_type": "coding",
    "targets": [
      {"scope_type": "symbol", "scope_key": "src/auth.py::function_login"}
    ]
  }'
```

If another member targets the same file or symbol, the backend returns `409 Conflict` unless `override_conflicts` is set to `true`.
