# AI Workspace MVP

Shared collaborative AI coding workspace for a hackathon demo. It includes FastAPI WebSockets, an in-memory workspace store, conflict detection, live locks, Supabase-ready sign-in, teammate invites, and a Vite React client.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm install
npm run dev -- --port 3000
```

Open `http://127.0.0.1:3000/?w=demo1&name=Member%20A`.

## Auth

The app works immediately with demo sign-in. To enable Google sign-in and email magic-link invites, create `frontend/.env`:

```bash
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
```

Then enable Google in Supabase Auth providers and add `http://127.0.0.1:3000` to the redirect URL allow list.

## Demo

1. Open one tab as `Member A`.
2. Copy an invite link for `Member B`.
3. In both tabs, send `modify function_login()` close together.
4. Member B sees a conflict warning and can wait or override.

Sponsor API hooks are implemented behind env vars in `backend/.env.example`. If keys are missing, local fallbacks keep the MVP demoable.
