# Phase 2 Goal: Scheduled Analysis Tasks

## Objective

Build Phase 2 of the authenticated TradingAgents web platform: add SQLite-backed scheduled analysis tasks that let authenticated users create, view, pause, resume, edit, delete, and manually trigger recurring stock analyses from the web UI, while reusing the existing Phase 1 analysis task runner, auth model, history persistence, and realtime event pipeline. Preserve existing CLI behavior and do not introduce Redis, Celery, Postgres, or external queue infrastructure unless explicitly approved.

## Scope

Allowed changes:

- `tradingagents/web/`
  - Add SQLite schema/migration logic for schedules and schedule executions.
  - Add scheduler service for due-task calculation and in-process execution.
  - Add schedule API routes.
  - Integrate schedule execution with the existing analysis task creation and runner flow.
- `frontend/`
  - Add schedule list page or panel.
  - Add schedule create/edit form.
  - Add schedule detail and execution-history UI.
  - Add manual trigger, pause, resume, and delete controls.
- `tests/`
  - Add scheduler model/API tests.
  - Add due-task calculation tests.
  - Add pause/resume/delete/manual-trigger tests.
  - Add ownership/isolation tests so users cannot access other users' schedules.
- `docs/web-ui.md`
  - Document scheduler setup, limitations, environment flags, and operational cautions.

## Non-goals

This phase does not include:

- Redis, Celery, Postgres, external queues, cloud schedulers, or distributed workers.
- Production-grade retry orchestration, dead-letter queues, or horizontal scaling.
- Multi-stock portfolio-level scheduling.
- Agent memory selection.
- Human-in-the-loop agent intervention.
- Broker integration, real trading, order placement, or fund management.
- Breaking existing CLI behavior.

## Acceptance Criteria

- Authenticated users can create scheduled analysis tasks.
- Schedule configuration supports at minimum:
  - ticker
  - analysis date policy or start date/time
  - analysts
  - research depth
  - provider/model parameters
  - output language
  - interval: `daily`, `weekly`, `monthly`
- Schedules are persisted in SQLite.
- Users can only list, view, edit, trigger, pause, resume, and delete their own schedules.
- Users can manually trigger a schedule, producing a normal Phase 1 analysis task and history record.
- Automatic due schedule execution is supported by an in-process scheduler loop or explicit service entrypoint.
- Each schedule execution is persisted with:
  - schedule id
  - generated analysis task id when available
  - status
  - started timestamp
  - completed timestamp
  - error message when failed
- UI shows schedule list, schedule status, next run time, and recent execution result.
- UI allows pause, resume, edit, delete, and manual trigger actions.
- Phase 1 history and realtime event behavior continue to work.
- Existing CLI commands continue to work.
- New backend behavior has focused tests.

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

Run CLI smoke checks:

```bash
tradingagents --help
python3 -m cli.main --help
```

Run Web scheduler smoke checks:

- Unauthenticated schedule API request returns 401 or 403.
- Authenticated user can create a schedule.
- Authenticated user can list schedules.
- Authenticated user can manually trigger a schedule.
- Manual trigger creates an analysis task/history record.
- SQLite contains schedule, execution, and generated analysis task records.

## Stop Conditions

Stop and ask the user if:

- Implementing the scheduler safely appears to require Redis, Celery, Postgres, or another external infrastructure service.
- A production deployment model or distributed scheduling semantics are required.
- Timezone semantics cannot be resolved with a reasonable default.
- Schedule execution needs to run while the web process is offline.
- Changes require altering the core TradingAgents graph execution order.
- Existing Phase 1 auth/history/realtime behavior would need to be broken or substantially redesigned.
- Tests reveal widespread unrelated failures that make regression boundaries unclear.

## Final Report Requirements

Report the following when complete:

- Branch name and commit hash.
- Major files added or changed.
- SQLite schema/table summary for schedules and executions.
- API route list for schedule operations.
- Scheduler execution model and limitations.
- Frontend schedule UI summary.
- How manual trigger maps to Phase 1 analysis tasks/history.
- Test, lint, build, and smoke results.
- Known risks and recommended Phase 3 follow-up.

## Suggested Phase 3 Follow-up

Add per-agent historical stock-analysis memory and selectable memory attachment so users can choose previous agent memories as extra context for future analyses.
