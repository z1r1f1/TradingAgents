# Phase 5 Goal: Production Hardening for Internet-Facing Web Platform

## Objective

Build Phase 5 production hardening for the authenticated TradingAgents web platform: make the Phase 1-4 web system safer to expose beyond a trusted development network by adding deployment guidance, stronger authentication defaults, rate limiting, audit/export controls, retention/delete workflows, SQLite backup/migration safeguards, and focused security tests while preserving existing CLI behavior and current web features.

## Scope

Allowed changes:

- `tradingagents/web/`
  - Add production-safe configuration validation for internet-facing deployments.
  - Add admin/user provisioning support or disable-open-registration flow.
  - Add basic rate limiting for auth, analysis creation, schedule trigger/run-due, memory APIs, and intervention continuation endpoints.
  - Add audit log persistence for security-relevant actions.
  - Add export/delete/retention workflows for analysis history, memories, schedules, and intervention records.
  - Add SQLite backup and schema-migration safety helpers.
  - Add security headers and stricter CORS/origin validation where appropriate.
- `frontend/`
  - Add admin/security settings UI only if needed for implemented backend controls.
  - Add user-facing export/delete controls where supported.
  - Surface production-safety warnings for insecure local defaults.
- `tests/`
  - Add focused tests for auth hardening, registration controls, rate limits, audit logging, export/delete, retention, backup/migration helpers, and ownership isolation.
- `docs/` and `README.md`
  - Add production deployment guide covering HTTPS/reverse proxy, environment variables, CORS, registration, backups, rate limits, provider-cost safeguards, and operational limitations.
- `goaldocs/`
  - Keep this goal document updated if scope changes during implementation.

## Non-goals

This phase does not include:

- Full enterprise RBAC, SSO/OAuth, SAML, billing, or team collaboration.
- Migrating from SQLite to Postgres or another external database.
- Distributed workers, Redis, Celery, Kubernetes operators, or cloud-native queue infrastructure.
- Broker integration, real trading, order placement, or fund management.
- Legal/compliance certification for investment advice.
- Rewriting Phase 1-4 feature behavior or core TradingAgents graph execution.
- Breaking existing CLI behavior.

## Acceptance Criteria

- Production mode can be enabled explicitly, for example with `TRADINGAGENTS_WEB_ENV=production` or equivalent documented setting.
- In production mode, unsafe defaults are rejected or warned clearly, including:
  - open self-registration
  - wildcard/overbroad CORS
  - default auth secret or missing secret where relevant
  - demo/default credentials in frontend state
- Self-registration can be disabled, and at least one documented admin/user provisioning path exists.
- Security-relevant actions are written to an audit log table, at minimum:
  - login success/failure
  - logout
  - registration/user creation
  - analysis creation
  - schedule create/update/delete/trigger/run-due
  - memory archive/unarchive/update
  - intervention create/message/pause/resume/close/run
  - export/delete actions
- Basic rate limiting exists for high-risk endpoints and is covered by tests.
- Users can export their own relevant data in a documented format, at minimum analyses/history, memories, schedules, and interventions.
- Users can delete or archive their own data according to documented rules without affecting other users.
- Retention/delete behavior is explicit and tested for owner isolation.
- SQLite backup helper or documented command exists and is tested or smoke-validated.
- SQLite schema migration safety is documented and has tests for idempotent initialization on an existing database.
- CORS/origin settings are documented and validated for production mode.
- Deployment documentation includes HTTPS/reverse proxy guidance and provider cost/rate-limit warnings for real runner usage.
- Phase 1 analysis/history/realtime still works.
- Phase 2 scheduling still works.
- Phase 3 memory selection/attachment still works.
- Phase 4 intervention continuation still works.
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

Run changed-scope lint:

```bash
ruff check tradingagents/web tests/test_web_backend.py frontend
```

Run whitespace diff check:

```bash
git diff --check
```

Run CLI smoke checks:

```bash
tradingagents --help
python3 -m cli.main --help
```

Run Web production-hardening smoke checks:

- Production mode rejects unsafe open-registration/default-secret/CORS settings.
- Authenticated user can still create an analysis task under safe settings.
- Rate limit returns expected status after configured threshold.
- Audit log records at least login, analysis creation, schedule trigger, memory archive, and intervention run events.
- User export returns only that user's data.
- User delete/archive operation does not affect another user's data.
- SQLite backup helper creates a readable backup.
- Existing Phase 1-4 happy path still works in demo runner mode.

## Stop Conditions

Stop and ask the user if:

- The desired production target requires OAuth/SSO, full RBAC, SAML, billing, or team collaboration.
- Requirements imply moving from SQLite to Postgres or another external database.
- Requirements imply distributed scheduling/locking, Redis, Celery, or cloud queue infrastructure.
- Legal/compliance obligations require formal financial-advice disclaimers, regulated retention, or certified audit workflows beyond pragmatic app hardening.
- Rate limiting requires a multi-process shared backend rather than local/in-process controls.
- Data deletion/export semantics are ambiguous or could destroy data unexpectedly.
- Existing Phase 1-4 behavior or CLI behavior would need to be broken.
- Tests reveal widespread unrelated failures that make regression boundaries unclear.

## Final Report Requirements

Report the following when complete:

- Branch name and commit hash.
- Major files added or changed.
- Production-mode configuration summary.
- Auth/registration hardening summary.
- Rate limiting design and endpoints covered.
- Audit log table/schema and event list.
- Export/delete/retention behavior and safety guarantees.
- SQLite backup/migration strategy.
- Deployment documentation location and key commands.
- Test, lint, build, diff-check, CLI smoke, and web smoke results.
- Remaining production risks and any recommended Phase 6 follow-up.

## Suggested Phase 6 Follow-up

Optional enterprise expansion: multi-user roles, team workspaces, shared memory governance, stronger audit review UI, optional Postgres migration path, distributed task execution, and SSO/OAuth integration if the deployment target requires it.
