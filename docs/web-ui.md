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

## External-access authentication defaults

Phase 1 is safe for authenticated external access only when deployed behind HTTPS and configured deliberately:

- The API binds to `0.0.0.0` by default so containers and remote browsers can reach it.
- Self-registration is enabled by default for local evaluation (`TRADINGAGENTS_WEB_ALLOW_REGISTRATION=1`). Disable it for any shared or internet-reachable deployment after provisioning users: `TRADINGAGENTS_WEB_ALLOW_REGISTRATION=0`.
- Authentication uses opaque bearer tokens. Tokens are returned only by `POST /api/auth/login`; SQLite stores only SHA-256 token hashes.
- Passwords are stored as PBKDF2-SHA256 hashes, never plaintext.
- The default runner is `demo` to avoid accidental external LLM/data-provider calls. Set `TRADINGAGENTS_WEB_RUNNER=real` only when API keys, data-provider access, cost controls, and rate limits are ready.
- CORS defaults to local Vite origins. Set `TRADINGAGENTS_WEB_CORS_ORIGINS` to the exact production frontend origin before exposing the API.

## Production hardening requirements before internet deployment

Before deploying beyond a trusted development network, add or enforce:

- HTTPS/TLS termination and secure reverse-proxy headers.
- Strong random secret management; do not rely on local defaults.
- Registration controls or an admin user-provisioning flow.
- Token expiry/rotation policy, session revocation UI, and audit logging.
- Rate limiting for login, registration, analysis creation, and SSE endpoints.
- CSRF strategy if browser cookie auth is introduced later; current Phase 1 uses bearer tokens.
- Origin allowlisting, security headers, and host/firewall restrictions.
- Backups and migration strategy for SQLite, or a future approved DB migration.
- Provider cost/rate-limit safeguards for `TRADINGAGENTS_WEB_RUNNER=real`.
- Secrets scanning and runtime DB exclusion in CI/CD artifacts.

## Real runner progressive events

The production web runner streams the actual `TradingAgentsGraph.graph.stream(...)` execution and emits/persists section and message events as chunks arrive. It does not call the Rich CLI `run_analysis()` wrapper, so CLI prompts, terminal state, and Telegram side effects remain isolated from web execution. Final report sections and the final decision are persisted after the stream completes.

## Adjustable history rerun workflow

History cards and completed task details include a load/template action. Loading a historical task copies its persisted parameters into the analysis form; users can edit ticker, date, analysts, research depth, provider/model fields, and output language, then press **Launch analysis** to create a new task. The existing rerun endpoint remains available for same-parameter or API-driven override reruns.

## Phase 2 scheduled analysis

Phase 2 adds SQLite-backed recurring analysis schedules without Redis, Celery, Postgres, cloud schedulers, or external queue services.

### Scheduler setup

The schedule API is available in the same FastAPI process as the Phase 1 web API. No extra service is required for manual triggers. Automatic due execution is intentionally in-process and can be driven by the protected explicit entrypoint:

```bash
POST /api/scheduler/run-due
Authorization: Bearer <token>
Content-Type: application/json

{"now":"2026-05-02T10:00:00+00:00"}
```

Omit `now` in normal operation to use the server's current UTC time. A deployment can call this endpoint from a local cron/systemd timer against each authenticated service account, or a future in-process loop can call the same `SchedulerService.run_due_for_user(...)` seam.

### Schedule API routes

All schedule routes require bearer authentication and are owner-scoped:

- `POST /api/schedules` — create a schedule.
- `GET /api/schedules` — list the current user's schedules.
- `GET /api/schedules/{schedule_id}` — view schedule detail and recent executions.
- `PATCH /api/schedules/{schedule_id}` — edit schedule configuration.
- `DELETE /api/schedules/{schedule_id}` — soft-delete a schedule.
- `POST /api/schedules/{schedule_id}/pause` — pause future due execution.
- `POST /api/schedules/{schedule_id}/resume` — resume future due execution.
- `POST /api/schedules/{schedule_id}/trigger` — manually create a normal Phase 1 analysis task from the schedule.
- `POST /api/scheduler/run-due` — execute all due active schedules owned by the authenticated user.

### Schedule configuration

Schedules persist the Phase 1 analysis parameters plus recurrence metadata:

- `name`
- `ticker`
- `start_at`
- `interval`: `daily`, `weekly`, or `monthly`
- `analysts`
- `research_depth`
- `llm_provider`, `backend_url`, `quick_model`, `deep_model`
- `output_language`
- optional `analysis_date` and `analysis_date_policy`

By default, executions use the run date as the generated Phase 1 task's analysis date. Monthly recurrence clamps to the last valid day of the target month, for example January 31 -> February 28 in non-leap years.

### SQLite scheduler tables

- `schedules`: owner, status, recurrence metadata, next/last run timestamps, and copied Phase 1 analysis parameters.
- `schedule_executions`: schedule id, generated analysis task id, status, trigger source, started/completed timestamps, and error message.

Manual and due executions create ordinary rows in `analysis_tasks`, `task_parameters`, `agent_event_logs`, `report_sections`, and `final_decisions`, so Phase 1 history and realtime event behavior continue to work.

### Frontend scheduler UI

The React UI includes a scheduled-analysis panel with:

- schedule create/edit form;
- list of schedules with status, next run time, and recent execution result;
- trigger, pause/resume, edit, and delete controls;
- triggered schedule executions loading the generated Phase 1 analysis result into the existing realtime/history panel.

### Scheduler limitations and cautions

- The scheduler is single-process and SQLite-backed. It is not a distributed lock manager and should not be run concurrently from multiple web processes without additional coordination.
- Due execution only happens when the web process is running and the explicit due-run entrypoint or future loop is invoked.
- There is no production-grade retry queue, dead-letter queue, or horizontal scaling in Phase 2.
- Keep `TRADINGAGENTS_WEB_RUNNER=demo` for local scheduler smoke tests. Set `TRADINGAGENTS_WEB_RUNNER=real` only after provider keys, budgets, and rate limits are ready.
- Do not expose schedule APIs on the internet without the Phase 1 production hardening items: HTTPS, registration controls, origin allowlisting, rate limiting, secret management, and audit logging.
