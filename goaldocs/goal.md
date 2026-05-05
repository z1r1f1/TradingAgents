# TradingAgents Web Platform Phase 1 Goal

## Objective

Build Phase 1 of an authenticated web platform for TradingAgents. Before modifying implementation code, inspect git status, ensure no secrets are included, commit and push the current uncommitted work using the repository’s Lore commit protocol, then create a new feature branch. Implement a FastAPI + SQLite backend and a React + Vite + TypeScript + Tailwind/shadcn UI that allows a logged-in user to configure and launch one stock analysis, watch each agent’s output in real time, view the final report and decision, browse persisted analysis history, and rerun from history, while preserving the existing CLI behavior and leaving clear extension points for scheduled analysis, per-agent memory selection, and future human-in-the-loop agent intervention.

## Scope

Allowed changes:

- Git workflow:
  - Check `git status` before implementation.
  - Ensure no `.env`, API keys, tokens, SQLite runtime databases, or secrets are included.
  - Commit and push current uncommitted work before feature implementation.
  - Create a new development branch, for example `feat/web-analysis-platform`.
- Backend:
  - Add `tradingagents/web/` for FastAPI service code.
  - Use SQLite for users, sessions, analysis tasks, task parameters, agent event logs, report sections, and final decisions.
  - Add authentication for externally accessible usage.
  - Wrap or lightly adapt existing analysis flow so Web tasks can receive status and event updates.
  - Modify core flow only where needed for event callbacks, task status, persistence, or future extension points.
- Frontend:
  - Add a React + Vite + TypeScript UI using Tailwind CSS and shadcn/ui.
  - Include login, analysis configuration, realtime analysis, final report, history list, and history detail screens.
- Tests:
  - Add tests for auth, API routes, SQLite persistence, task status, history, and realtime event behavior.
- Documentation:
  - Update `README.md` or add `docs/web-ui.md` with setup, run, and known limitations.

## Non-goals

This phase does not include:

- Multi-stock portfolio-level analysis.
- Broker integration, real trading, order placement, or fund management.
- Production-grade RBAC, OAuth, multi-tenant permissions, billing, or team collaboration.
- A full scheduler implementation; only reserve architecture/API boundaries for scheduled analysis.
- Full human-in-the-loop agent takeover; only reserve extension points.
- External databases, Redis, Celery, object storage, or queue infrastructure unless explicitly approved.
- Breaking existing CLI behavior.

## Acceptance Criteria

- Current uncommitted work is reviewed for secrets, committed with Lore commit protocol, and pushed before feature work starts.
- Feature work is completed on a new branch.
- Web service can bind to `0.0.0.0`.
- Protected UI/API routes require authentication.
- User can log in and log out.
- SQLite persists users/session metadata, analysis tasks, task parameters, agent event logs, final decision, and report sections.
- UI supports configuring ticker, analysis date, analysts, research depth, provider/model parameters, and output language.
- User can launch one stock analysis from the UI.
- UI shows realtime per-agent progress, messages, and key events during analysis.
- UI displays final report and final trading decision after completion.
- UI provides history list and detail pages.
- User can rerun an analysis from a historical record, with parameters reused or adjustable.
- Existing CLI commands still work.
- New backend interfaces have focused tests.

## Validation

Run required backend validation:

```bash
pytest
```

Run frontend validation if a frontend package is added:

```bash
npm install
npm run build
npm test
```

Run configured lint/type checks if available:

```bash
ruff check .
mypy .
npm run lint
```

Run smoke checks:

```bash
tradingagents --help
python -m cli.main --help
python -m tradingagents.web.main
```

Also verify:

- Health check endpoint is reachable.
- Unauthenticated access to protected API returns 401 or 403.
- Authenticated user can create an analysis task.
- SQLite contains created task, events, and final result records.

## Stop Conditions

Stop and ask the user if:

- Current uncommitted files include `.env`, API keys, tokens, credentials, private data, generated DB files, or suspected secrets.
- `git push` fails due to remote, permission, or credential issues.
- Existing branch state cannot be safely committed or has conflicts.
- Implementation requires Redis, Postgres, Celery, external object storage, or other infrastructure.
- Implementation requires production-grade RBAC, OAuth, or multi-tenant security design.
- Core graph execution order must change, beyond adding callbacks/status/persistence hooks.
- True mid-run agent takeover or conversational intervention becomes necessary in Phase 1.
- Existing test failures are widespread and unrelated to this task, making regression boundaries unclear.

## Final Report Requirements

Report the following when complete:

- Commit hash for pre-work commit and feature branch name.
- Push result.
- Major files added or changed.
- Backend startup command.
- Frontend startup/build commands.
- Web access URL.
- Authentication design summary.
- SQLite file location and table summary.
- API route list.
- Realtime output implementation approach.
- Completed versus deferred requirements.
- Test, lint, build, and smoke results with command output summaries.
- Known risks and recommended follow-up phases.

## Follow-up Phases

- Phase 2: Scheduled analysis tasks.
- Phase 3: Per-agent historical stock-analysis memory and selectable memory attachment.
- Phase 4: Human-in-the-loop continuation and agent-specific dialogue intervention.
- Phase 5: Production hardening, deployment, security, and multi-user permissions.
