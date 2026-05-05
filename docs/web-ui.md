# TradingAgents Web UI

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
- `TRADINGAGENTS_WEB_RUNNER`: `demo` for deterministic local smoke tests; any other value uses the real graph streaming runner.
- `TRADINGAGENTS_WEB_ALLOW_REGISTRATION`: set `0` to disable self-registration.
- `TRADINGAGENTS_WEB_CORS_ORIGINS`: comma-separated frontend origins.
- `TRADINGAGENTS_WEB_REAL_RUNNER_USER_ANALYSIS_LIMIT`: optional local cap for real-runner analysis/continuation creation per user; `-1` disables it.
- `TRADINGAGENTS_WEB_REAL_RUNNER_WORKSPACE_ANALYSIS_LIMIT`: optional local cap for real-runner analysis/continuation creation per workspace; `-1` disables it.
- `TRADINGAGENTS_WEB_RUNTIME_MODE`: `local` (default SQLite/in-process), `production-single` (SQLite with documented single-process limits), or `production-cluster` (Postgres + Redis).
- `TRADINGAGENTS_WEB_POSTGRES_DSN`: required in `production-cluster`; for example `postgresql://user:pass@postgres:5432/tradingagents`.
- `TRADINGAGENTS_WEB_REDIS_URL`: required in `production-cluster`; for example `redis://redis:6379/0`.
- `TRADINGAGENTS_WEB_COORDINATION_NAMESPACE`: Redis key prefix for rate limits, budgets, locks, and idempotency keys.

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
- No OAuth/SAML/SCIM, billing, external DB, object storage, broker integration, legal hold, or distributed scheduler is included.

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

## Phase 8 operator usage reporting

The frontend exposes a Phase 8 operator/governance report using the APIs available in this build. It summarizes `GET /api/governance/audit` plus `GET /api/health`, so operators can review analysis launches, schedule triggers, intervention continuations, duplicate suppression, and `cost.blocked` events without requiring live provider credentials. Backend Phase 8 support includes SQLite migration dry-run/apply/validate helpers, durable usage-ledger records, Redis counter reconciliation helpers, and mockable provider-usage import seams.

- The report is derived from `GET /api/governance/audit` plus `GET /api/health`.
- Audit filters remain workspace-scoped and can narrow by target user id, event type, and ISO start/end timestamps.
- The UI summarizes analysis launches, schedule triggers, intervention continuations, blocked real-runner attempts, and duplicate-suppression events already present in the audit log.
- Blocked-run reasons are read from audit metadata, for example `user budget exceeded` or `workspace budget exceeded`.
- Cluster/runtime warnings are displayed only from the existing health response fields (`runtime_mode`, storage backend, coordination backend, and dependency configuration flags).
- Dedicated migration, reconciliation, or provider-usage operator views can build on the Phase 8 helper/API seams; this release keeps the UI intentionally audit/health based to avoid destructive migration controls in the browser.
- Until those backend routes and maintenance commands land, operators should continue using the Phase 5-7 backup, audit, budget-cap, and cluster-health procedures below; do not infer provider billing totals from the audit-only report.

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

## Phase 3 per-agent analysis memory

Phase 3 adds explicit, user-selected historical agent memories without vector databases, external embedding services, Redis, Postgres, or object storage.

### Memory extraction rules

When a web analysis completes, the backend extracts per-agent memories from persisted report sections:

- `market_report` -> `Market Analyst`
- `sentiment_report` -> `Social Analyst`
- `news_report` -> `News Analyst`
- `fundamentals_report` -> `Fundamentals Analyst`
- `investment_plan` -> `Research Manager`
- `trader_investment_plan` -> `Trader`
- `final_trade_decision` -> `Portfolio Manager`

Each memory stores owner user id, source analysis task id, ticker, analysis date, agent name, title, content, JSON tags, archived flag, and creation timestamp.

### Memory API routes

All memory routes require bearer authentication and are owner-scoped:

- `GET /api/memories` — list memories. Filters: `ticker`, `agent`, `analysis_date`, `query`, `archived`.
- `GET /api/memories/{memory_id}` — view one memory.
- `PATCH /api/memories/{memory_id}` — update title/tags metadata.
- `POST /api/memories/{memory_id}/archive` — hide memory from default selection/search.
- `POST /api/memories/{memory_id}/unarchive` — restore memory to default selection/search.

### SQLite memory tables

- `agent_memories`: extracted per-agent memories with owner, source task, ticker/date, agent, title/content, tags JSON, archive status, and timestamp.
- `analysis_memory_attachments`: selected memories attached to a generated analysis task.
- `schedule_memory_attachments`: selected memories attached to a schedule and copied to each generated analysis task.

### Manual memory selection workflow

The frontend memory browser lets users search/list their own active memories, view details, archive memories, and select memories in the manual analysis form. Selected memory ids are submitted with `POST /api/analyses` as `memory_ids`. Analysis detail/history includes `attached_memories` so users can audit which historical context was used.

### Scheduled memory selection workflow

Schedule create/edit includes memory selection. The selected memory ids are persisted with the schedule. Manual schedule triggers and due schedule execution copy those ids into the generated Phase 1 analysis task, so the normal history/detail view shows the attached memories.

### Context injection design and limits

Only explicitly selected, non-archived memories owned by the authenticated user can be attached. Before the web runner starts, attached memories are rendered deterministically in attachment order as bounded plain text:

```text
Attached historical agent memories:
[Memory #id] Agent | Ticker | Date
Content...
```

The context is capped at **4000 characters** before being passed to the web runner as `memory_context`. The real graph runner appends this bounded context to the existing web-only `past_context` seam. The CLI path is unchanged.

### Privacy and security cautions

- Memories are never shared across users.
- Archived memories are excluded from default listing and cannot be newly attached.
- Memory content may contain prior model outputs and market data summaries; treat SQLite backups and exports as sensitive user data.
- Phase 3 uses simple SQLite text filtering, not semantic retrieval or embeddings.
- Production deployments should add retention policies, audit review, export/delete controls, and compliance governance before relying on memories for regulated workflows.

## Phase 4 human-in-the-loop intervention

Phase 4 adds auditable human-guided continuation sessions for a selected agent on a completed analysis task. It does **not** mutate a running LangGraph node, rewrite the original report, or change CLI execution. Continuations are stored separately and linked to the source task.

### Intervention API routes

All intervention routes require bearer authentication and are owner-scoped through the source analysis task:

- `GET /api/interventions` — list the current user's sessions.
- `POST /api/interventions` — create a session with `source_analysis_task_id` and `target_agent_name`.
- `GET /api/interventions/{session_id}` — view session detail, messages, events, and outputs.
- `POST /api/interventions/{session_id}/messages` — append explicit user guidance to an open session.
- `POST /api/interventions/{session_id}/pause` — pause a session.
- `POST /api/interventions/{session_id}/resume` — reopen a paused session.
- `POST /api/interventions/{session_id}/close` — close a session and reject future messages.
- `POST /api/interventions/{session_id}/run` — run a bounded continuation for the target agent.

### SQLite intervention tables

- `intervention_sessions`: owner, source analysis task, target agent, status, created/updated/closed timestamps.
- `intervention_messages`: ordered user guidance messages with author, content, timestamp, and sequence.
- `intervention_events`: ordered continuation progress/audit events.
- `intervention_outputs`: human-guided continuation outputs plus bounded context metadata.

### Continuation design

The continuation runner is a separate web-only seam. It builds bounded context from:

- source task id and target agent;
- the original output for the target agent when available;
- attached memories already linked to the source analysis task;
- ordered user guidance messages in the intervention session.

The continuation context is capped at **4000 characters**. Outputs are inserted into `intervention_outputs` and progress is inserted into `intervention_events`. Original `report_sections`, `final_decisions`, and Phase 1 event logs are not overwritten, so the original analysis remains auditable and distinguishable from human-guided continuation output.

### Frontend intervention UI

The analysis detail/realtime area includes agent-level intervention controls. Users can start a session for a target agent, inspect linked sessions, add guidance, pause/resume/close, trigger continuation, and view the timeline of user messages, continuation events, and generated continuation output. Labels intentionally show task id, target agent, and status to distinguish continuation output from original analysis.

### Limitations and safety cautions

- Phase 4 does not provide true mid-node live graph mutation.
- Sessions are single-user and owner-scoped; no collaborative intervention is implemented.
- Continuation output is deterministic and auditable in local/demo mode. Real model-backed continuation should add provider cost/rate controls before production use.
- No file upload, voice/video, rich document annotation, compliance approval workflow, Redis/Celery/Postgres, or external workflow engine is included.
- Production deployments should add audit export, retention/delete workflows, stronger admin provisioning, rate limits, and a dedicated security review before internet exposure.

## Phase 5 production hardening

Phase 5 adds pragmatic controls for deployments that are reachable outside a trusted development network while keeping SQLite, FastAPI, React, the demo runner, and CLI behavior intact. This is still not an enterprise compliance stack: use HTTPS, strict origin allowlists, explicit user provisioning, backups, and cost controls before enabling the real runner.

### Production-mode configuration

Enable production validation explicitly:

```bash
export TRADINGAGENTS_WEB_ENV=production
export TRADINGAGENTS_WEB_AUTH_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export TRADINGAGENTS_WEB_ALLOW_REGISTRATION=0
export TRADINGAGENTS_WEB_CORS_ORIGINS=https://tradingagents.example.com
```

In production mode startup rejects open self-registration, the local default auth secret, weak/missing auth secrets, and wildcard CORS. Local development keeps the previous defaults. The frontend also removes demo login defaults when `VITE_TRADINGAGENTS_WEB_ENV=production` is set and shows a warning when the API appears to be local or the web env is not production.

### User provisioning

The supported bootstrap path is environment-driven first-user creation:

```bash
export TRADINGAGENTS_WEB_BOOTSTRAP_EMAIL=admin@example.com
export TRADINGAGENTS_WEB_BOOTSTRAP_PASSWORD='replace-with-a-long-random-password'
export TRADINGAGENTS_WEB_ALLOW_REGISTRATION=0
```

On startup the backend creates that user if it does not already exist and records `auth.user.provisioned` in `audit_logs`. Remove the bootstrap password from the environment after the account exists, then use the normal login route.

### Rate limits

Rate limiting is local in-process and intended as a basic abuse/cost guard, not a multi-process distributed limiter. Configure:

- `TRADINGAGENTS_WEB_RATE_LIMIT_WINDOW_SECONDS` (default `60`)
- `TRADINGAGENTS_WEB_AUTH_RATE_LIMIT` for login/register
- `TRADINGAGENTS_WEB_ANALYSIS_RATE_LIMIT` for analysis create/rerun
- `TRADINGAGENTS_WEB_MUTATION_RATE_LIMIT` for schedule, memory, delete/export-adjacent mutations, and intervention lifecycle actions
- `TRADINGAGENTS_WEB_INTERVENTION_RATE_LIMIT` for intervention continuation runs

Exceeded limits return HTTP `429` and emit `rate_limit.exceeded`.

### Audit log

The `audit_logs` table stores `user_id`, event type, resource type/id, metadata JSON, IP address, and timestamp. Security-relevant events include login success/failure, logout, registration/provisioning, analysis create/rerun/delete, schedule create/update/delete/pause/resume/trigger/run-due, memory update/archive/unarchive, intervention create/message/pause/resume/close/run/delete, account export, and rate-limit denials. Users can inspect their own audit events with `GET /api/account/audit`.

### Export, delete, and retention behavior

`GET /api/account/export` returns JSON format `tradingagents.web.export.v1` containing only the authenticated user's analyses, memories, schedules, and interventions. The frontend has an **Export account** button that downloads this JSON. Treat exports as sensitive because they can include prompts, model outputs, market summaries, and attached memories.

Deletion is owner-scoped:

- `DELETE /api/analyses/{task_id}` hard-deletes the user's task and cascades its events, report sections, final decision, attached memories, and linked interventions.
- `DELETE /api/schedules/{schedule_id}` keeps the existing soft-delete behavior through `deleted_at`.
- `POST /api/memories/{memory_id}/archive` remains the retention-safe memory workflow; archived memories are omitted from default listings and cannot be newly attached.
- `DELETE /api/interventions/{session_id}` hard-deletes one owned intervention session and its messages/events/outputs.

These routes return `404` for another user's data. There is no regulated retention/legal-hold workflow in Phase 5.

### SQLite backup and migration safety

SQLite initialization is idempotent and records Phase 5 schema creation in `schema_migrations`. Create a consistent backup with:

```bash
python3 -m tradingagents.web.maintenance backup \
  --database ~/.tradingagents/web.sqlite3 \
  --output ~/.tradingagents/backups/web-$(date +%Y%m%d-%H%M%S).sqlite3
```

Run backups before upgrades and store them encrypted/off-host for internet-facing deployments. Backups and exports may contain sensitive user data.

### Reverse proxy and provider-cost guidance

Terminate TLS at a reverse proxy such as Caddy, Nginx, Traefik, or a managed load balancer. Forward only the API path to Uvicorn, set exact CORS origins, use secure secret storage, and disable direct public access to the SQLite file and backup directory. Keep `TRADINGAGENTS_WEB_RUNNER=demo` until API keys, provider budgets, rate limits, monitoring, and manual review workflows are ready for real model/data-provider calls.

## Phase 6 workspace RBAC, governance, and cost guardrails

Phase 6 adds SQLite-backed workspaces and role checks while preserving the existing FastAPI/SQLite/React shape, the deterministic demo runner, and CLI behavior. Existing users are migrated idempotently into a personal workspace; new users receive a personal workspace during registration/provisioning.

### Workspace schema and migration

New tables:

- `workspaces`: workspace name, `kind` (`personal` or `shared`), creator, and timestamps.
- `workspace_members`: workspace/user membership with role and timestamps.

New nullable `workspace_id` columns are added to `analysis_tasks`, `schedules`, `agent_memories`, `intervention_sessions`, and `audit_logs`. Startup backfills existing user-owned rows into each user's personal workspace only when `workspace_id` is missing. The migration never reassigns rows that already have an explicit workspace.

### Role matrix

| Role | Read workspace data | Create analysis/schedule/memory/intervention work | Update schedules/memories/interventions | Delete analyses/schedules/interventions | Manage members/export/audit |
| --- | --- | --- | --- | --- | --- |
| owner | yes | yes | yes | yes | yes |
| admin | yes | yes | yes | yes | yes |
| member | yes | yes | yes | no | audit/export read only |
| viewer | yes | no | no | no | audit/export read only |

The API prevents removing the final owner or demoting the final owner from a workspace.

### Workspace-scoped API behavior

Workspace-aware endpoints accept or infer `workspace_id`:

- analyses/history: create, list, detail, rerun, delete, and SSE replay;
- schedules: create, list, detail, update, pause/resume, trigger, delete, and `/api/scheduler/run-due?workspace_id=...`;
- memories: list/detail/update/archive/unarchive and memory attachment validation;
- interventions: list/detail/create/message/pause/resume/close/run/delete;
- audit/export: `/api/governance/audit`, `/api/account/export?workspace_id=...`, and `/api/workspaces/{workspace_id}/export`;
- workspace administration: `/api/workspaces`, `/api/workspaces/{id}`, and member add/update/remove routes.

Unauthorized cross-workspace access returns `403` when the workspace is known but the role is insufficient, or `404` when the resource is not visible to the caller. List and export routes include only workspaces where the caller is a member.

### Governance audit console

The frontend workspace governance card includes:

- workspace switcher and shared-workspace creation;
- member provisioning, role changes, and removal controls for owner/admin users;
- audit filters for workspace, user id, event type, start time, and end time;
- a budget-status note so operators know real-runner caps are enforced server-side.

Audit rows include `workspace_id` when an event is workspace-related. `cost.blocked` audit events are written before budget-denied real-runner analysis, scheduled trigger/due execution, or intervention continuation requests return `402`.

### Real-runner budget guardrails

These local caps are intentionally simple counters, not provider billing reconciliation:

```bash
export TRADINGAGENTS_WEB_RUNNER=real
export TRADINGAGENTS_WEB_REAL_RUNNER_USER_ANALYSIS_LIMIT=100
export TRADINGAGENTS_WEB_REAL_RUNNER_WORKSPACE_ANALYSIS_LIMIT=500
```

Set either cap to `-1` to disable it. When enabled, the API checks the cap before manual analysis, history rerun, schedule trigger/due execution, and intervention continuation. Blocked requests return `402` and append `cost.blocked` to `audit_logs` with the reason.

### Backup hardening

`python3 -m tradingagents.web.maintenance backup` now fails clearly if the source SQLite file is missing and verifies the copied database with `pragma integrity_check`. A non-`ok` result raises an error instead of silently accepting a corrupt backup.

### Phase 6 production limits and follow-up

Phase 6 remains a single-process SQLite deployment. It does not add SSO/OAuth/SAML, SCIM, billing APIs, Celery, legal hold, or compliance certification. Recommended follow-up: organization invitations with email verification, stronger admin provisioning UX, retention/legal-hold design, provider billing reconciliation, and a dedicated security review before broad enterprise rollout.

## Phase 7 production-cluster runtime

Phase 7 adds an explicit runtime mode matrix and shared coordination layer so the web API can run safely in multi-process or multi-instance deployments.

### Runtime mode matrix

| Mode | Storage | Coordination | Intended use | Startup requirements |
| --- | --- | --- | --- | --- |
| `local` | SQLite | in-process memory | development, demos, deterministic tests | no Postgres/Redis |
| `production-single` | SQLite | in-process memory | one web process with Phase 5 hardening | production auth/CORS/registration checks |
| `production-cluster` | Postgres | Redis | multiple API processes/instances | `TRADINGAGENTS_WEB_POSTGRES_DSN` and `TRADINGAGENTS_WEB_REDIS_URL` must be configured and reachable |

Cluster startup initializes the Postgres schema idempotently and pings Redis before serving. Missing or unreachable dependencies fail fast with clear startup errors. Health responses expose `runtime_mode`, `storage_backend`, `coordination_backend`, and dependency configured/available booleans without echoing DSNs, Redis credentials, auth secrets, or bearer tokens.

### Postgres persistence

`production-cluster` uses the Postgres schema manager and repository adapter for all Phase 1-6 web tables:

- auth/session: `users`, `sessions`;
- workspace/RBAC/audit: `workspaces`, `workspace_members`, `audit_logs`, `schema_migrations`;
- analysis/history/realtime: `analysis_tasks`, `task_parameters`, `agent_event_logs`, `report_sections`, `final_decisions`;
- scheduling: `schedules`, `schedule_executions`;
- memories: `agent_memories`, `analysis_memory_attachments`, `schedule_memory_attachments`;
- interventions: `intervention_sessions`, `intervention_messages`, `intervention_events`, `intervention_outputs`.

The SQLite repository remains the default and keeps its idempotent migration/backfill path for local data. Do not point `production-cluster` at a SQLite database; migrate data deliberately through export/import or a dedicated migration plan.

### Redis coordination

Redis keys are prefixed by `TRADINGAGENTS_WEB_COORDINATION_NAMESPACE` (default `tradingagents:web`). The coordinator uses:

- `rate:<scope>:<identity>:<bucket>` with a window TTL for shared fixed-window rate limits;
- `budget:user:<id>` and `budget:workspace:<id>` for shared real-runner budget counters;
- `lock:schedule:due:<id>` and `lock:schedule:trigger:<id>` for schedule execution suppression;
- `idempotency:<scope>:user:<id>:<client-key>` with a 24-hour TTL for replaying safe retried responses.

Rate-limit blocks emit `rate_limit.exceeded`. Budget blocks emit `cost.blocked`. Duplicate idempotent request replays emit `idempotency.replay`. Suppressed duplicate schedule execution emits `schedule.duplicate_suppressed`.

### Cluster-safe request behavior

- Manual analysis and history rerun honor `Idempotency-Key`; duplicate retries return the first created task instead of creating another task.
- Manual schedule trigger uses an idempotency key when supplied and a short Redis lock to avoid concurrent trigger execution.
- Due schedule execution acquires a Redis lock per due schedule; concurrent workers skip locked schedules and audit suppression.
- Intervention continuation honors `Idempotency-Key` so retried continuation calls do not duplicate outputs.
- Real-runner budget checks use the existing DB counts plus Redis shared counters, so local mode remains compatible and cluster mode gets atomic cross-instance enforcement for new requests.

### Local development services

The compose file includes optional Postgres and Redis services under the `cluster` profile:

```bash
docker compose --profile cluster up postgres redis
export TRADINGAGENTS_WEB_RUNTIME_MODE=production-cluster
export TRADINGAGENTS_WEB_POSTGRES_DSN=postgresql://tradingagents:tradingagents@localhost:5432/tradingagents
export TRADINGAGENTS_WEB_REDIS_URL=redis://localhost:6379/0
```

Integration tests use `TRADINGAGENTS_TEST_POSTGRES_DSN` and `TRADINGAGENTS_TEST_REDIS_URL`. If those variables are absent, cluster integration tests skip explicitly while unit tests still cover the coordination semantics.

### Backup and migration operations

SQLite local backups still use `python3 -m tradingagents.web.maintenance backup`. Production-cluster backups should use managed Postgres snapshots or `pg_dump`/WAL archival appropriate to the deployment. Redis coordination state is short-lived or reconstructable except budget counters; reset budget counters deliberately during operational windows and document the reset in audit/ops logs.

Phase 8 adds documented dry-run/apply/validate migration and usage-reconciliation workflows. Always create a readable backup before applying migration changes, inspect the dry-run row-count report, and validate source/target counts afterward. The helpers are idempotent and refuse apply without a readable backup by default; do not use ad-hoc migrations that could reassign users, workspaces, sessions, or audit rows.

Maintenance commands:

```bash
python3 -m tradingagents.web.maintenance migration-plan --source ~/.tradingagents/web.sqlite3 --backup ./backup.sqlite3
python3 -m tradingagents.web.maintenance migration-apply --source ./source.sqlite3 --target ./target.sqlite3 --backup ./backup.sqlite3
python3 -m tradingagents.web.maintenance migration-validate --source ./source.sqlite3 --target ./target.sqlite3
```
