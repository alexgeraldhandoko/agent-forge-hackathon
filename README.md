# Shared AI

<img width="1512" height="818" alt="image" src="https://github.com/user-attachments/assets/7a1be512-9e95-432a-a83d-267d27b0b422" />

<img width="1510" height="820" alt="image" src="https://github.com/user-attachments/assets/f7d047b2-b237-45bd-9bd5-6fef5bc33c29" />


Shared AI is a hackathon MVP for a teammate-aware AI workspace. Users sign in with Google, create or join a 6-digit workspace, prompt a shared agent, and see generated files, chat updates, conflicts, scraped context, and execution output in one live room.

The MVP is designed to be demoable fast:

- React + Vite frontend with a Google-Stitch-style dark workspace UI
- FastAPI backend with WebSocket collaboration
- In-memory workspace state, so no database is required for local/demo use
- Google OAuth sign-in through Google Identity Services
- 6-digit random workspace join codes
- Shared generated file explorer and inline code blocks in chat
- Conflict detection for overlapping function edits
- Sponsor integrations for Kimi, TokenRouter, SenseNova, Bright Data, Daytona, and Nosana
- Local fallbacks when a sponsor key or service is unavailable

## Architecture

```text
Frontend: Vite + React + Framer Motion
Backend:  FastAPI + WebSockets + in-memory workspace store
AI route: prompt -> task detector -> Kimi / TokenRouter / SenseNova / Bright Data / Nosana
Run step: generated files -> Daytona sandbox -> syntax/run output -> shared context update
```

The backend keeps each workspace in memory by its 6-digit code. If the backend restarts, workspace state resets. This is intentional for the hackathon MVP and keeps setup simple.

## Requirements

Install these before running the project:

- Python 3.11 or newer
- Node.js 20 or newer
- npm 10 or newer
- Git
- Google OAuth Web Client ID
- Optional sponsor API keys for live routes

Recommended local ports:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:3000`

## Project Structure

```text
.
├── backend/
│   ├── main.py            # FastAPI app, WebSocket room handling
│   ├── router.py          # Prompt routing and AI provider calls
│   ├── context_store.py   # In-memory workspaces, files, members, actions
│   ├── conflict.py        # Function conflict detection
│   ├── sandbox.py         # Daytona and Nosana integration
│   ├── scraper.py         # Bright Data and direct-fetch fallback
│   └── .env.example       # Backend environment template
├── frontend/
│   ├── src/
│   │   ├── App.jsx        # Main UI
│   │   ├── auth.js        # Google sign-in helpers
│   │   ├── ws.js          # WebSocket client and 6-digit workspace codes
│   │   └── styles.css     # App styling
│   ├── package.json
│   └── .env.example       # Frontend environment template
├── requirements.txt
└── README.md
```

## Environment Setup

Never commit real API keys. Copy the example files and fill in local values.

### Backend Env

```bash
cp backend/.env.example backend/.env
```

`backend/.env` supports:

```bash
KIMI_API_KEY=

TOKENROUTER_API_KEY=
TOKENROUTER_BASE_URL=https://api.tokenrouter.com/v1
TOKENROUTER_MODEL=anthropic/claude-opus-4.8-fast

SENSENOVA_API_KEY=
SENSENOVA_BASE_URL=https://api.velaalpha.cc/v1
SENSENOVA_CHAT_MODEL=sensenova-6.7-flash-lite

BRIGHTDATA_API_KEY=
BRIGHTDATA_UNLOCKER_ZONE=web_unlocker1
BRIGHTDATA_ZONE=

DAYTONA_API_KEY=

NOSANA_API_KEY=
NOSANA_API_BASE=https://dashboard.k8s.prd.nos.ci/api
NOSANA_MARKET=
NOSANA_CREATE_DEPLOYMENT=false
```

Important notes:

- `NOSANA_CREATE_DEPLOYMENT=false` authenticates and checks Nosana readiness without launching a GPU deployment.
- Set `NOSANA_CREATE_DEPLOYMENT=true` only when you intentionally want the train route to create and start a real Nosana deployment.
- `BRIGHTDATA_UNLOCKER_ZONE` should normally be your Web Unlocker zone, for example `web_unlocker1`.
- If a provider key is missing, the app uses a local/demo fallback where possible.

### Frontend Env

```bash
cp frontend/.env.example frontend/.env
```

`frontend/.env`:

```bash
VITE_GOOGLE_CLIENT_ID=your-google-web-client-id.apps.googleusercontent.com
```

Google OAuth setup:

1. Open Google Cloud Console.
2. Create an OAuth client of type `Web application`.
3. Add these Authorized JavaScript origins:

```text
http://127.0.0.1:3000
http://localhost:3000
```

4. No backend redirect URI is required for the current Google Identity Services button flow.
5. Paste the client ID into `frontend/.env`.

## Install

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then install frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

## Run Locally

Start the backend:

```bash
source .venv/bin/activate
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

In a second terminal, start the frontend:

```bash
cd frontend
npm run dev -- --port 3000
```

Open:

```text
http://127.0.0.1:3000
```

## Using the App

1. Sign in with Google.
2. Choose `Create workspace`.
3. Copy the generated 6-digit code.
4. Teammates sign in with Google, choose `Join`, and enter the same code.
5. Type a prompt and press Enter to send.
6. Generated files appear in the file explorer and inside the chat response.
7. All connected teammates see shared context updates in real time.

Example prompts:

```text
Create a tiny Python calculator in src/calculator.py with add and subtract functions.
```

```text
Create a React landing page for a weather app.
```

```text
Who is the current prime minister of Singapore?
```

```text
Scrape https://example.com and summarize the page.
```

```text
Train a small classifier and show the training script.
```

## Sponsor Product Behavior

### Kimi

Used first for coding/editing prompts. The backend calls an OpenAI-compatible chat endpoint and asks for strict JSON containing:

- `assistant_message`
- `files`
- `functions_modified`

### TokenRouter

Used as a routing/fallback provider when Kimi is unavailable or when configured as the preferred model. Configure:

```bash
TOKENROUTER_API_KEY=
TOKENROUTER_BASE_URL=https://api.tokenrouter.com/v1
TOKENROUTER_MODEL=
```

### SenseNova

Used for document, image, diagram, visual, and artifact-style prompts. The app first attempts a structured workspace edit. If the model does not return strict JSON, the backend saves a Markdown artifact so the user still gets a visible result.

### Bright Data

Used when the prompt includes a URL or asks for current/latest/live information. If no URL is provided, the backend creates a search URL from the prompt, scrapes it, stores the result under `scrapes/`, and asks the model to answer from the scraped content.

### Daytona

Used after code generation to run a sandboxed Python syntax check through the Daytona SDK. If Daytona is unavailable, the app falls back to a local syntax check so the demo does not break.

### Nosana

Used for training/GPU-style prompts. With `NOSANA_CREATE_DEPLOYMENT=false`, the backend authenticates, reads markets/jobs, and reports readiness. With `NOSANA_CREATE_DEPLOYMENT=true`, it creates and starts a deployment.

## Health Checks

Backend health:

```bash
curl http://127.0.0.1:8000/health
```

Provider status:

```bash
curl http://127.0.0.1:8000/api/provider-status
```

Workspace snapshot:

```bash
curl http://127.0.0.1:8000/api/workspaces/123456
```

Reset a workspace:

```bash
curl -X POST http://127.0.0.1:8000/api/workspaces/123456/reset
```

## Build

Frontend production build:

```bash
cd frontend
npm run build
```

Preview production build:

```bash
cd frontend
npm run preview -- --port 3000
```

## Troubleshooting

### Google button does not appear

Check `frontend/.env`:

```bash
VITE_GOOGLE_CLIENT_ID=...
```

Restart the Vite dev server after changing env vars. Also make sure `http://127.0.0.1:3000` and `http://localhost:3000` are in Google OAuth Authorized JavaScript origins.

### Teammates cannot join

Workspace codes must be exactly 6 digits. The backend must also be running, because the WebSocket room lives in backend memory.

### Workspace disappears after restart

This MVP uses an in-memory store. Restarting the backend clears workspaces, members, files, conflicts, and action logs.

### Bright Data route gives fallback output

Check:

```bash
BRIGHTDATA_API_KEY=
BRIGHTDATA_UNLOCKER_ZONE=web_unlocker1
```

If Bright Data fails, the app attempts direct fetch for continuity.

### Nosana says authenticated but not launched

That is expected unless:

```bash
NOSANA_CREATE_DEPLOYMENT=true
```

Keep it `false` for safe demos. Turn it on only when you want to spend credits/start a deployment.

### Daytona fails

The app falls back to local Python syntax checks. Verify:

```bash
DAYTONA_API_KEY=
```

and that your Daytona account can create sandboxes.

## Database Notes

No database is required for this MVP. Supabase can be added later for persistent users, workspace membership, files, and action logs. If you add persistence, the likely tables are:

- `workspaces`
- `workspace_members`
- `workspace_files`
- `workspace_actions`
- `workspace_conflicts`

For the current hackathon demo, Google OAuth plus backend in-memory state is enough.

## Demo Script

1. Open the app and sign in with Google.
2. Create a workspace and show the 6-digit code.
3. Open another browser or incognito window, sign in with another Google account, and join with the code.
4. Prompt: `Create a tiny Python calculator in src/calculator.py with add and subtract functions.`
5. Show the generated file in the explorer and the code block in chat.
6. Prompt: `Who is the current prime minister of Singapore?`
7. Explain that Bright Data is used for current/live data and stores the scrape in shared context.
8. Prompt a training request if Nosana is configured.
9. Show that teammate count, recent work, files, and conflicts update in real time.

## Security

- Do not commit `.env` files.
- Do not paste API keys into frontend code.
- Keep sponsor keys on the backend only.
- Use `NOSANA_CREATE_DEPLOYMENT=false` unless you intentionally want to launch a GPU deployment.
