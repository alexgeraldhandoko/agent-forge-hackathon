# AI Workspace — Agent Forge Hackathon

A multi-agent AI collaboration system where multiple team members each have their own AI agent operating on a **shared codebase simultaneously**, with conflict detection, function-level locking, and real-time broadcast.

## Architecture

```
Member A / B / C
       │
       ▼
  MemberAgent  ──── ConflictChecker ──── LockMap (Supabase)
       │
       ▼
  TokenRouter
   ├── CODE/DEBUG/REVIEW  → KimiAI k2-5  → Daytona Sandbox (execute)
   ├── IMAGE/DOCUMENT     → SenseNova U1
   ├── ML_TRAIN/COMPUTE   → Nosana GPU
   └── SCRAPE             → BrightData  → KimiAI k2-5
       │
       ▼
  Shared Context Store (Supabase)
       │
       ▼
  Broadcaster (WebSocket) → all connected members
```

## Key Concepts

**Conflict detection** is function/file-level. Before any agent modifies a target, `ConflictChecker` reads the lock map from Supabase. If the target is already locked by another member, the submitting member is warned and can choose to wait or override.

**Lock map format**: `{ "function_login": "Member A", "classifier.py": "Member C" }`

**TokenRouter** picks the right model per task type and injects the full workspace context (file list, lock map, recent action log) into every model call.

**Broadcaster** pushes a WebSocket event to all members after every agent action so UIs stay in sync without polling.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in API keys
python main.py         # starts FastAPI on :8000
```

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/task` | Submit a task (member, task_type, prompt, target) |
| GET | `/locks` | Current lock map |
| GET | `/actions` | Recent action log |
| GET | `/files` | Workspace file list |
| WS | `/ws/{member}` | Real-time updates |

**Task types**: `code`, `debug`, `review`, `image`, `document`, `ml_train`, `compute`, `scrape`

## Supabase Tables

Run these in the Supabase SQL editor to bootstrap the schema:

```sql
create table workspace_files (
  id uuid default gen_random_uuid() primary key,
  path text unique,
  content text,
  updated_by text,
  updated_at timestamptz default now()
);

create table lock_map (
  id uuid default gen_random_uuid() primary key,
  target text unique,
  member text,
  locked_at timestamptz default now()
);

create table action_log (
  id uuid default gen_random_uuid() primary key,
  member text,
  action text,
  target text,
  payload jsonb,
  created_at timestamptz default now()
);

create table assets (
  id uuid default gen_random_uuid() primary key,
  name text,
  type text,
  url text,
  created_at timestamptz default now()
);
```
