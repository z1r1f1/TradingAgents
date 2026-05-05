# TradingAgents Web UI Phase 1

Phase 1 adds an authenticated FastAPI + SQLite backend and a React/Vite/TypeScript/Tailwind frontend for one-stock analysis.

## Backend setup and run

```bash
pip install .
TRADINGAGENTS_WEB_HOST=0.0.0.0 TRADINGAGENTS_WEB_PORT=8000 python -m tradingagents.web.main
```

The service binds to `0.0.0.0` by default through `TRADINGAGENTS_WEB_HOST`. Local API URL: `http://localhost:8000`.

Important environment variables:

- `TRADINGAGENTS_WEB_DB`: SQLite path. Default: `~/.tradingagents/web.sqlite3`.
- `TRADINGAGENTS_WEB_AUTH_SECRET`: reserved secret setting for future signed-token/session hardening.
- `TRADINGAGENTS_WEB_RUNNER`: `demo` for deterministic local smoke tests; any other value uses the real `TradingAgentsGraph.propagate()` runner.
- `TRADINGAGENTS_WEB_ALLOW_REGISTRATION`: set `0` to disable self-registration.
- `TRADINGAGENTS_WEB_CORS_ORIGINS`: comma-separated frontend origins.

## Frontend setup and run

```bash
cd frontend
npm install
npm run dev
npm run build
npm test
npm run lint
```

Frontend URL: `http://localhost:5173`. Set `VITE_TRADINGAGENTS_API=http://localhost:8000` if the API is not on the default URL.

## Authentication design

The backend stores users with PBKDF2-SHA256 password hashes. Login creates an opaque bearer session token; only the SHA-256 token hash is stored in SQLite. Protected API routes require `Authorization: Bearer <token>`. Logout deletes the session token.

## SQLite location and tables

Default DB: `~/.tradingagents/web.sqlite3`.

Tables:

- `users`: email and password hash.
- `sessions`: bearer-session token hashes and expiry metadata.
- `analysis_tasks`: owner, status, timestamps, and errors.
- `task_parameters`: ticker, date, analysts, research depth, provider/model parameters, output language, and full JSON payload.
- `agent_event_logs`: ordered per-agent realtime events.
- `report_sections`: named markdown/text report sections.
- `final_decisions`: normalized final decision plus raw rationale/payload.

## API routes

Public:

- `GET /health` and `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`

Protected:

- `POST /api/auth/logout`
- `GET /api/auth/me`
- `POST /api/analyses`
- `GET /api/analyses`
- `GET /api/analyses/{task_id}`
- `GET /api/analyses/{task_id}/events`
- `GET /api/analyses/{task_id}/events/stream`
- `POST /api/analyses/{task_id}/rerun`
- History aliases: `GET /api/history`, `GET /api/history/{task_id}`, `POST /api/history/{task_id}/rerun`

## Realtime output approach

The web runner accepts an `emit(EventPayload)` callback. Each event is persisted to `agent_event_logs` with a monotonically increasing sequence number. The SSE endpoint returns persisted events as `text/event-stream`, so completed tasks can be replayed without rerunning analysis. This callback seam is also the Phase 4 extension point for human-in-the-loop intervention.

## Current limitations and deferred work

- Demo runner is default for safe local smoke tests. Set `TRADINGAGENTS_WEB_RUNNER=real` to invoke the existing graph and external LLM/data dependencies.
- Background task execution uses FastAPI background tasks, not Redis/Celery.
- No production RBAC, OAuth, billing, team collaboration, external DB, object storage, broker integration, or scheduler is included.
- Scheduler, per-agent memory selection, and mid-run human takeover are reserved as future extension points only.
