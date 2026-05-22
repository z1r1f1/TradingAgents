# Phase 7 Goal: Production Cluster Runtime with Postgres and Redis

## Objective

Make the TradingAgents web platform safe to run as a multi-process or multi-instance production service by adding Postgres-backed persistence, Redis-backed shared coordination, and cluster-safe rate limiting, budget counters, scheduling locks, and idempotency while preserving Phase 1-6 behavior and CLI compatibility.

## Scope

Allowed changes:

- `tradingagents/web/`
  - Add a storage/runtime abstraction that supports existing SQLite local mode and new Postgres production-cluster mode.
  - Add Postgres schema initialization/migration support for all Phase 1-6 web tables and relationships.
  - Add Redis-backed shared rate limiting, budget counters, distributed locks, idempotency keys, and optional short-lived coordination state.
  - Make schedule `run-due`, manual schedule trigger, analysis creation/rerun, and intervention continuation cluster-safe.
  - Add production startup validation for cluster mode, requiring Postgres and Redis configuration.
  - Keep SQLite mode supported for local/demo/single-process usage with explicit documented limitations.
  - Add maintenance commands or helpers for Postgres migration checks, health checks, and backup guidance where appropriate.
- `frontend/`
  - Surface cluster runtime health/status warnings only if backend exposes relevant status.
  - Preserve existing Phase 1-6 UI behavior and workspace/RBAC UX.
- `tests/`
  - Add deterministic unit tests for backend abstractions, Redis fallbacks/mocks, lock semantics, idempotency, rate limit sharing, budget counters, and startup validation.
  - Add integration tests that run against Postgres/Redis when services are available, and skip clearly when unavailable.
- `docker-compose.yml`, Docker-related files, docs, and examples
  - Add or update local development services for Postgres and Redis if useful.
  - Document production-cluster deployment variables, migration/backup strategy, and operational limitations.
- `pyproject.toml` / dependency metadata
  - Add only necessary Postgres/Redis client dependencies and keep optional extras if appropriate.
- `goaldocs/`
  - Keep this goal document updated if scope changes during implementation.

## Non-goals

This phase does not include:

- SSO/OAuth/SAML/SCIM, billing, or external identity-provider integration.
- Legal hold, regulated retention certification, or compliance attestations.
- Kubernetes operators, Terraform, Helm charts, or cloud-specific managed-service provisioning.
- Celery or a full external job queue unless unavoidable for cluster safety.
- Real broker integration, trading execution, or fund management.
- Rewriting the core TradingAgents graph execution.
- Breaking SQLite local/demo mode, existing CLI commands, or Phase 1-6 web behavior.

## Acceptance Criteria

- Runtime mode is explicit and documented, at minimum:
  - `local` or equivalent: SQLite + in-process controls for development/demo.
  - `production-single` or equivalent: clearly documented single-process limitations.
  - `production-cluster` or equivalent: Postgres + Redis required.
- Production-cluster startup fails fast with clear errors if Postgres or Redis configuration is missing, invalid, or unreachable.
- Existing SQLite databases still initialize idempotently and pass current Phase 1-6 tests.
- Postgres schema initialization is idempotent and covers users, auth/session state, analyses, events, reports, schedules, memories, interventions, workspaces, memberships, audit logs, migrations, and cost/budget state.
- Postgres repositories preserve owner/workspace/RBAC isolation semantics from Phase 6.
- Redis-backed rate limiting is shared across app instances and covered by tests using isolated keys/namespaces.
- Redis-backed budget counters are shared and enforce user/workspace real-runner limits atomically.
- Distributed locks prevent duplicate due-schedule execution across concurrent workers/instances.
- Idempotency keys prevent duplicate analysis/schedule/intervention side effects on retried requests where applicable.
- Audit events record cluster-relevant blocked or deduplicated actions, including rate-limit blocks, budget blocks, and duplicate schedule suppression.
- Health/status endpoint or startup logs make database, Redis, and runtime mode visible without leaking secrets.
- Backup/migration documentation explains SQLite local backups and Postgres production backup expectations.
- Existing Phase 1 analysis/history/realtime still works.
- Existing Phase 2 scheduling still works and is cluster-safe in production-cluster mode.
- Existing Phase 3 memory selection/attachment still works.
- Existing Phase 4 intervention continuation still works.
- Existing Phase 5 production hardening controls still work.
- Existing Phase 6 workspace RBAC/governance/cost guardrails still work.
- Existing CLI commands still work.

## Validation

Run backend tests:

```bash
python3 -m pytest -q
```

Run frontend validation:

```bash
cd frontend
npm install
npm run build
npm test
npm run lint
```

Run changed-scope lint and formatting checks:

```bash
ruff check tradingagents/web tests/test_web_backend.py frontend
git diff --check
```

Run CLI smoke checks:

```bash
tradingagents --help
python3 -m cli.main --help
```

Run Web smoke checks in SQLite/local mode:

- Auth/register/login still works.
- Manual analysis/history/realtime still works.
- Schedule trigger/run-due still works.
- Memory extraction/attachment still works.
- Intervention continuation still works.
- Workspace RBAC and governance filters still work.
- Export/delete/audit still works.

Run production-cluster validation:

- Startup rejects cluster mode without Postgres configuration.
- Startup rejects cluster mode without Redis configuration.
- Postgres schema initializes idempotently on an empty database.
- A second app instance can read data created by the first app instance.
- Redis rate limit is shared across two app instances.
- Redis budget counter blocks after the shared user/workspace limit is reached.
- Concurrent due-schedule runners execute a due schedule at most once.
- Repeated idempotent request does not duplicate analysis/schedule/intervention side effects.
- Health/status reports runtime mode and dependency availability.

If local Postgres/Redis services are unavailable, integration tests must skip with explicit messages, and mocked/unit coverage must still validate the cluster-safety logic.

## Stop Conditions

Stop and ask the user if:

- Requirements imply removing SQLite local/demo support.
- Requirements require Celery, Kubernetes, Terraform, Helm, or cloud-specific provisioning.
- Requirements require an externally managed Postgres/Redis credential or live production deployment access.
- Data migration semantics could lose, duplicate, or reassign existing user/workspace data.
- Runtime mode names or production deployment assumptions conflict with the user's target hosting environment.
- Adding dependencies creates licensing, platform, or installation concerns.
- Existing CLI behavior or Phase 1-6 behavior would need to break.
- Tests reveal widespread unrelated failures that make regression boundaries unclear.

## Final Report Requirements

Report the following when complete:

- Branch name and commit hash pushed to remote.
- Major files added or changed.
- Runtime mode matrix and required environment variables.
- Postgres schema/migration strategy and SQLite compatibility summary.
- Redis usage summary: rate limiting, budget counters, locks, idempotency, key namespace/TTL choices.
- Cluster-safety behavior for schedule run-due, manual triggers, analysis/rerun, and intervention continuation.
- Health/status and operational documentation locations.
- Test, lint, build, diff-check, CLI smoke, local Web smoke, and cluster validation results.
- Any integration tests skipped and the exact reason.
- Remaining risks and recommended Phase 8 follow-up.

## Codex /goal Objective

Implement Phase 7 production-cluster runtime for the TradingAgents web platform by adding Postgres persistence and Redis-backed shared coordination for rate limits, budget counters, distributed locks, and idempotency, while preserving SQLite local mode, Phase 1-6 behavior, and CLI compatibility, with the full task contract in `goaldocs/phase-7-production-cluster-runtime.md`.

## Preflight Instructions

Before code changes, confirm the current branch is clean and pushed, then create a new feature branch such as `feat/production-cluster-runtime`. Do not overwrite or delete existing SQLite data; migrations must be idempotent and must stop on ambiguous data ownership or workspace mapping semantics.
