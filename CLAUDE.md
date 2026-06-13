# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Multi-agent AI collaboration workspace (Agent Forge Hackathon). Three members (A, B, C) each submit tasks to their own `MemberAgent`. All agents operate on the same codebase simultaneously with function/file-level locking and real-time broadcast.

## Running the server

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in all API keys
python main.py         # FastAPI on :8000
```

## Architecture

The request pipeline is linear — every task flows through these layers in order:

1. **`MemberAgent`** (`agents/member_agent.py`) — per-member facade; orchestrates steps 2-5.
2. **`ConflictChecker`** (`conflict_checker/checker.py`) — reads the lock map from Supabase and blocks the action if another member owns the target. Callers can pass `override_conflict=True` to force through.
3. **`TokenRouter`** (`token_router/router.py`) — single `AsyncOpenAI` client pointed at `TOKENROUTER_API_BASE`. All LLM chat calls go through it; the model name selects the underlying service.
4. **Model integrations** (`integrations/`) — one file per service; see table below.
5. **`ContextStore`** + **`Broadcaster`** — Supabase write + WebSocket push to all connected members.

## Task routing

| TaskType | How it's called | Model / service | Side effect |
|---|---|---|---|
| `code`, `debug`, `review` | TokenRouter chat completions | `moonshot-v1-128k` (KimiAI) | Daytona sandbox executes generated code |
| `image`, `document` | SenseNova `images.generate()` direct | `nova-ptx-xl` | — |
| `ml_train`, `compute` | Nosana REST direct | GPU job | Poll `GET /job/{id}` until `status=="completed"` |
| `scrape` | BrightData → TokenRouter chat | `moonshot-v1-128k` | Scraped markdown injected into prompt |

**Important:** `image`/`document` tasks call SenseNova directly (not through TokenRouter) because they use the `images.generate()` endpoint, not chat completions.

## Integrations

| File | SDK / transport | Auth env var |
|---|---|---|
| `integrations/kimi_ai.py` | `openai` SDK, `base_url=KIMI_API_BASE` | `KIMI_API_KEY` |
| `integrations/sense_nova.py` | `openai` SDK, `base_url=SENSENOVA_API_BASE` | `SENSENOVA_API_KEY` |
| `integrations/nosana.py` | `httpx` async | `NOSANA_API_KEY` |
| `integrations/bright_data.py` | `httpx` async, `POST /request`, format=markdown | `BRIGHTDATA_API_KEY` |
| `integrations/daytona.py` | `httpx` async, 4-step flow (see below) | `DAYTONA_API_KEY` |

**Daytona execution flow** (`integrations/daytona.py`):
```
POST /sandbox                        → { id }
POST /sandbox/{id}/files             → write code file
POST /sandbox/{id}/exec              → { command } → stdout/stderr
DELETE /sandbox/{id}                 → always runs in finally block
```

**`integrations/kimi_ai.py` is a direct fallback only** — in production all LLM calls go through TokenRouter. Use `KimiAI` for isolated testing of the Kimi endpoint.

## Shared Context Store (Supabase)

Four tables: `workspace_files`, `lock_map`, `action_log`, `assets`. SQL to create them is in `ReadMe.md`. The `LockMap` class keeps an in-memory cache and calls `refresh()` before each conflict check — stale cache is intentional (refresh is explicit, not automatic).

## WebSocket

Connect at `ws://localhost:8000/ws/{member}`. Every completed agent action broadcasts an `agent_action` event with the updated lock snapshot. The server does not send heartbeats — clients should handle reconnect on disconnect.

## Adding a new model

1. Add client in `integrations/your_model.py`.
2. For chat models: pass a new model name string to `TokenRouter._chat()` — no new integration file needed if it routes through TokenRouter.
3. For non-chat APIs (images, compute): add the integration file, a `TaskType` enum value, and a routing branch in `TokenRouter.route()`.
4. Add env vars to `.env.example`.

## Key env vars

| Var | Purpose |
|---|---|
| `TOKENROUTER_API_KEY` / `TOKENROUTER_API_BASE` | Entry point for all LLM chat calls |
| `KIMI_API_KEY` / `KIMI_MODEL` | Direct KimiAI access (testing only) |
| `SENSENOVA_API_KEY` / `SENSENOVA_MODEL` | Image generation |
| `NOSANA_API_KEY` / `NOSANA_API_BASE` | GPU job submission |
| `BRIGHTDATA_API_KEY` | Web scraping |
| `DAYTONA_API_KEY` / `DAYTONA_API_BASE` | Sandbox execution |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | Shared context store |

All keys are required at startup — missing vars raise `KeyError` immediately.
