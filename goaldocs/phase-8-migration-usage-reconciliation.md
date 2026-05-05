# Phase 8 Goal: Migration, Usage Reconciliation, and Operational Cost Governance

## Status

- State: In progress
- Team execution is underway; do not mark this phase complete until implementation and required validation are finished.

## Objective

Add production operations tooling for the Phase 7 cluster runtime by implementing an auditable SQLite-to-Postgres migration path, Redis budget reset/reconciliation workflows, provider-usage reconciliation seams, and operator-facing cost/governance reports while preserving Phase 1-7 behavior and CLI compatibility.

## Scope

Allowed changes:

- `tradingagents/web/`
  - Add a safe SQLite-to-Postgres migration utility for existing Phase 1-7 web data.
  - Add migration dry-run, validation, resumability, idempotency, and rollback/backup guidance.
  - Add budget ledger tables or records that allow Redis counters to be reconciled against durable database state.
  - Add budget reset policies for daily/monthly user and workspace limits.
  - Add provider-usage import/reconciliation seams using mockable adapters; consult official provider documentation before implementing any live provider API behavior.
  - Add operator APIs or maintenance commands for usage summaries, reconciliation status, and blocked-run audit review.
  - Preserve existing runtime modes: SQLite local, production-single, and production-cluster.
- `frontend/`
  - Add operator/governance UI for usage summaries, budget status, reconciliation warnings, and blocked-run review if backend APIs are exposed.
  - Do not disrupt existing analysis, schedule, memory, intervention, workspace, or governance workflows.
- `tests/`
  - Add focused tests for migration dry-run/apply/idempotency, owner/workspace preservation, budget reset/reconciliation, provider-usage mock adapters, and operator reports.
  - Add integration tests for SQLite-to-Postgres migration when Postgres is available; skip clearly when unavailable.
- `docs/`, `README.md`, deployment examples, and `goaldocs/`
  - Document migration runbooks, backup requirements, reconciliation schedules, provider API limitations, and operational recovery steps.

## Non-goals

This phase does not include:

- SSO/OAuth/SAML/SCIM or enterprise identity-provider integration.
- Billing subscriptions, payment collection, invoices, or customer-facing checkout.
- Legal hold, regulated retention certification, or compliance attestations.
- Multi-region Redis split-brain resolution beyond documenting known limitations and safe deployment assumptions.
- Cloud-specific Terraform, Helm, Kubernetes operators, or managed-service provisioning.
- Real broker integration, trading execution, or fund management.
- Rewriting the core TradingAgents graph execution.
- Breaking SQLite local/demo mode, Postgres cluster mode, existing CLI commands, or Phase 1-7 web behavior.

## Acceptance Criteria

- A documented migration command or helper can dry-run migration from a Phase 1-7 SQLite database into Postgres without modifying the target.
- Migration dry-run reports row counts, table coverage, unsupported data, and owner/workspace mapping before apply.
- Migration apply copies users, sessions where appropriate, workspaces, memberships, analyses, events, reports, schedules, memories, interventions, audit logs, schema migrations, and budget/usage records.
- Migration apply is idempotent: rerunning it does not duplicate records or corrupt relationships.
- Migration refuses to run without a recent SQLite backup or explicit documented override.
- Migration validation compares source and target counts plus key relationship checks and reports a machine-readable summary.
- Budget usage is durably recorded so Redis counters can be reconstructed after Redis loss or restart.
- Daily/monthly budget reset behavior is explicit, configurable, and covered by tests for user and workspace limits.
- Reconciliation can compare Redis counter state with durable usage ledger state and repair or report drift according to documented policy.
- Provider-usage adapters are mockable and optional; tests do not require live provider credentials.
- Provider usage imports can attach external usage/cost records to user, workspace, provider, model, and time window where enough metadata exists.
- Blocked runs, budget resets, reconciliation repairs, and provider usage imports are audit logged.
- Operator/governance view or API can show usage by user, workspace, provider, model, date range, and blocked/allowed status.
- Phase 1 analysis/history/realtime still works.
- Phase 2 scheduling still works.
- Phase 3 memory selection/attachment still works.
- Phase 4 intervention continuation still works.
- Phase 5 production hardening controls still work.
- Phase 6 workspace RBAC/governance/cost guardrails still work.
- Phase 7 Postgres/Redis cluster runtime still works.
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
ruff check tradingagents/web tests/test_web_backend.py tests/test_web_cluster_runtime.py frontend
git diff --check
```

Run CLI smoke checks:

```bash
tradingagents --help
python3 -m cli.main --help
```

Run migration and reconciliation smoke checks:

- Create a SQLite database with representative Phase 1-7 data.
- Run migration dry-run and verify no Postgres writes occur.
- Run migration apply into an empty Postgres database.
- Re-run migration apply and verify no duplicates.
- Validate migrated row counts and owner/workspace relationships.
- Simulate Redis counter loss and reconstruct budget counters from durable ledger state.
- Simulate Redis/database counter drift and verify reconciliation reports or repairs according to configured policy.
- Import mocked provider usage records and verify user/workspace/provider/model/date attribution.
- Verify audit logs for migration, reset, reconciliation, provider import, and blocked-run events.

Run Web smoke checks:

- Existing SQLite/local mode still supports auth, analysis, schedule, memory, intervention, workspace RBAC, export/delete, and audit.
- Production-cluster mode still supports Postgres shared persistence and Redis shared coordination.
- Operator usage/governance report excludes unauthorized workspace data.

If local Postgres/Redis services are unavailable, integration tests must skip with explicit messages, and unit/mocked tests must still cover migration planning and reconciliation logic.

## Stop Conditions

Stop and ask the user if:

- Migration semantics for users, workspaces, sessions, or audit logs are ambiguous and could reassign, duplicate, or destroy data.
- Requirements imply removing SQLite local/demo support or making Postgres mandatory for all users.
- Requirements require live provider billing credentials, paid API access, or external production deployment access.
- Provider APIs do not expose enough metadata to safely attribute usage to user/workspace/model without additional instrumentation.
- Requirements expand into SSO/OAuth/SAML/SCIM, payment billing, legal hold, or regulated compliance certification.
- Requirements require multi-region Redis consensus or split-brain recovery beyond documented single-region assumptions.
- Adding dependencies creates licensing, platform, or installation concerns.
- Existing CLI behavior or Phase 1-7 behavior would need to break.
- Tests reveal widespread unrelated failures that make regression boundaries unclear.

## Final Report Requirements

Report the following when complete:

- Branch name and commit hash pushed to remote.
- Major files added or changed.
- SQLite-to-Postgres migration command, dry-run/apply/validate behavior, and backup requirements.
- Migration coverage table and any excluded data.
- Budget ledger/reset/reconciliation design and Redis drift handling.
- Provider-usage adapter design, supported mock/live modes, and attribution limitations.
- Operator/governance usage report behavior and authorization guarantees.
- Documentation locations and operational runbooks.
- Test, lint, build, diff-check, CLI smoke, migration smoke, reconciliation smoke, and Web smoke results.
- Any integration tests skipped and exact reason.
- Remaining risks and recommended Phase 9 follow-up.

## Codex /goal Objective

Implement Phase 8 migration, usage reconciliation, and operational cost governance for the TradingAgents web platform by adding an auditable SQLite-to-Postgres migration path, durable budget ledger/reset/reconciliation workflows, mockable provider-usage import seams, and operator usage reports, while preserving Phase 1-7 behavior and CLI compatibility, with the full task contract in `goaldocs/phase-8-migration-usage-reconciliation.md`.

## Preflight Instructions

Before code changes, confirm the current branch is clean and pushed, then create a new feature branch such as `feat/migration-usage-reconciliation`. Do not overwrite, delete, or auto-migrate existing SQLite data without an explicit backup and dry-run validation report.
