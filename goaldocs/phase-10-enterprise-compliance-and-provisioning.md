# Phase 10 Goal: Enterprise Compliance and Provisioning Hardening

## Objective

Close the remaining enterprise production-readiness gaps after Phase 9 by adding formal identity lifecycle provisioning, legal-hold-aware retention controls, auditable compliance exports, and live-provider operational runbooks while preserving Phase 1-9 local auth, OIDC, workspace RBAC, SQLite local mode, Postgres/Redis cluster mode, and CLI compatibility.

## Why This Follows Phase 9

Phase 9 establishes optional OIDC login, IdP group-to-workspace role mapping, identity audit visibility, and workspace-scoped retention preview/apply controls. The remaining risks are non-blocking for Phase 9 because they require policy decisions, live enterprise IdP access, legal/compliance review, or production infrastructure credentials. They should be handled as a separate phase rather than hidden inside the Phase 9 implementation.

## Scope

Allowed changes:

- `tradingagents/web/`
  - Add SCIM or equivalent admin provisioning APIs only after selecting a target enterprise provisioning contract.
  - Add legal hold models and enforcement so retention apply cannot mutate held resources.
  - Add compliance export endpoints for audit logs, identity mappings, retention decisions, usage ledger records, and legal-hold state.
  - Add operator-only runbook/status APIs for live OIDC provider checks that do not expose secrets or tokens.
- `frontend/`
  - Add admin views for legal holds, provisioning status, compliance exports, and live IdP health.
  - Keep Phase 9 SSO entry point, local login, and workspace/RBAC flows working.
- `tests/`
  - Add deterministic tests for legal-hold retention denial, compliance export shape, provisioning lifecycle events, and mocked live IdP health checks.
- `docs/`, deployment examples, and `goaldocs/`
  - Document legal-hold semantics, SCIM/provisioning setup, compliance export procedures, live IdP validation, incident response, and remaining certification limitations.

## Non-goals

This phase does not include:

- Payment billing, invoices, checkout, or provider billing APIs.
- Formal legal/compliance certification or regulated archival attestation unless separate legal requirements are supplied.
- Broker integration, trading execution, or fund management.
- Breaking local auth, SQLite local/demo mode, Postgres/Redis cluster mode, existing CLI commands, or Phase 1-9 web behavior.

## Acceptance Criteria

- Phase 9 OIDC login and local username/password auth still work.
- Provisioning changes cannot grant workspace owner without an explicit admin-controlled path.
- Legal holds can be attached to supported resources and prevent retention apply from deleting or archiving held data.
- Retention preview reports held resources distinctly from eligible resources.
- Compliance exports include audit, identity, retention, usage ledger, and legal-hold records without secrets or bearer/IdP tokens.
- Live IdP health checks validate discovery/userinfo reachability without logging tokens or client secrets.
- Admin/operator UI exposes provisioning, legal hold, compliance export, and IdP health state only to authorized workspace owner/admin roles.
- Phase 1-9 web features and CLI commands still work.

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
python3 -m ruff check tradingagents/web tests frontend
git diff --check
```

Run CLI smoke checks:

```bash
tradingagents --help
python3 -m cli.main --help
```

## Stop Conditions

Stop and ask the user if:

- The target enterprise requires a specific SCIM version, legal-hold policy, retention schedule, or certification language not supplied in this goal.
- Live IdP credentials, production deployment access, or legal/compliance approval are required.
- Retention semantics could destroy ambiguous data.
- Existing Phase 1-9 behavior or CLI behavior would need to break.
- Adding dependencies creates licensing, platform, or installation concerns.

## Final Report Requirements

Report branch/commit, changed files, provisioning and legal-hold behavior, compliance export shape, live IdP health behavior, docs, validation evidence, skipped live integration tests, and remaining follow-up risks.

## Codex /goal Objective

Implement Phase 10 enterprise compliance and provisioning hardening for TradingAgents by adding formal provisioning lifecycle controls, legal-hold-aware retention, compliance exports, and live IdP operational checks while preserving Phase 1-9 behavior, SQLite local mode, Postgres/Redis cluster mode, and CLI compatibility.
