# Phase 6 Goal: Workspace RBAC, Governance Console, and Cost Guardrails

## Objective

Build the enterprise collaboration foundation for the authenticated TradingAgents web platform by adding workspace-scoped analysis, role-based access control, an audit/governance console, and practical real-runner cost guardrails while preserving Phase 1-5 behavior and CLI compatibility.

## Scope

Allowed changes:

- `tradingagents/web/`
  - Add SQLite-backed workspace/team membership models, role checks, and owner/workspace scoping helpers.
  - Add endpoints for workspace CRUD, member invitation/provisioning, role updates, workspace-scoped analyses, schedules, memories, interventions, exports, and audit views.
  - Add cost/budget guardrails for real-runner usage, including per-user/workspace limits, configurable caps, and audit events for blocked runs.
  - Harden backup/maintenance helpers where needed, including rejecting missing source databases and validating `pragma integrity_check` results.
- `frontend/`
  - Add workspace switcher, member/role management UI, governance/audit console, and budget/status indicators.
  - Keep the existing single-user/demo workflow usable with a default personal workspace.
- `tests/`
  - Add focused backend and frontend tests for RBAC, workspace isolation, governance views, export/delete scoping, budget blocking, and backup safety.
- `docs/`, `README.md`, and `goaldocs/`
  - Document role semantics, workspace deployment settings, budget guardrails, operational limits, and migration notes.

## Non-goals

This phase does not include:

- SSO/OAuth/SAML, SCIM, billing, or enterprise identity-provider integrations.
- Migrating from SQLite to Postgres or adding Redis/Celery/distributed workers.
- Real broker integration, order placement, or fund management.
- Legal/compliance certification, legal hold, or regulated retention workflows.
- Rewriting the core TradingAgents graph or breaking existing CLI behavior.

## Acceptance Criteria

- Existing users are assigned to a personal workspace through an idempotent migration path.
- Workspace roles exist at minimum: owner/admin/member/viewer, with documented permissions.
- Users can create or switch workspaces and see only authorized workspace data.
- Admin/owner users can invite or provision members, change roles, and remove members without orphaning owned data.
- Analysis tasks, histories, schedules, memories, and intervention sessions can be scoped to a workspace.
- Owner isolation remains enforced: unauthorized cross-workspace access returns 403/404 and never leaks sensitive data.
- Audit/governance UI can filter security events by workspace, user, event type, and time range.
- Account/workspace export returns only authorized data and includes enough metadata to distinguish personal vs workspace records.
- Cost guardrails can block real-runner analysis/continuation when configured user or workspace budgets are exceeded.
- Budget decisions and blocked runs are recorded in audit logs.
- SQLite backup helper fails clearly for missing source databases and failed integrity checks.
- Phase 1 analysis/history/realtime still works.
- Phase 2 scheduling still works.
- Phase 3 memory selection/attachment still works.
- Phase 4 intervention continuation still works.
- Phase 5 production hardening controls still work.
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

Run Web smoke checks:

- Existing user receives a personal workspace after migration.
- Workspace owner can invite/add a member and change that member's role.
- Viewer cannot create analysis, schedules, memories, or interventions.
- Member/admin permissions behave according to documented role matrix.
- Cross-workspace data access is denied.
- Workspace audit console filters events correctly.
- Workspace export excludes another workspace's data.
- Configured budget cap blocks real-runner analysis/continuation and writes an audit event.
- SQLite backup command rejects a nonexistent database and succeeds for a valid database.

## Stop Conditions

Stop and ask the user if:

- Requirements require SSO/OAuth/SAML, SCIM, billing, or external identity providers.
- Requirements require migrating from SQLite or adding distributed workers/queues.
- Role semantics become ambiguous or imply regulated compliance/legal-hold behavior.
- Existing single-user behavior or CLI behavior would need to break.
- Data migration could destroy or reassign existing records ambiguously.
- Provider cost controls require live provider billing APIs or credentials.
- Tests reveal widespread unrelated failures that make regression boundaries unclear.

## Final Report Requirements

Report the following when complete:

- Branch name and commit hash pushed to remote.
- Major files added or changed.
- Workspace schema and migration summary.
- Role/permission matrix and enforced endpoint list.
- Workspace scoping behavior for analyses, schedules, memories, interventions, audit logs, exports, and deletes.
- Cost guardrail settings and blocked-run behavior.
- Backup helper hardening summary.
- Documentation locations.
- Test, lint, build, diff-check, CLI smoke, and Web smoke results.
- Remaining risks and recommended Phase 7 follow-up.

## Codex /goal Objective

Implement Phase 6 workspace RBAC, governance audit UI, and cost guardrails for the TradingAgents web platform on a new feature branch, preserving Phase 1-5 behavior and CLI compatibility, with the full task contract in `goaldocs/phase-6-workspace-rbac-governance.md`.

## Preflight Instructions

Before code changes, confirm the current branch is clean and pushed, then create a new feature branch such as `feat/workspace-rbac-governance`. Do not overwrite or delete user data; use idempotent migrations and stop on ambiguous migration semantics.
