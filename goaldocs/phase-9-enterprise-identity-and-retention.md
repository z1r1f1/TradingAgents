# Phase 9 Goal: Enterprise Identity and Retention Governance

## Objective

Add enterprise identity and retention-governance foundations for the TradingAgents web platform by implementing optional OIDC/OAuth login, identity-to-workspace role mapping, admin-visible identity audit controls, and configurable retention/delete policies while preserving Phase 1-8 behavior and CLI compatibility.

## Scope

Allowed changes:

- `tradingagents/web/`
  - Add optional OIDC/OAuth login alongside existing local auth/bootstrap accounts.
  - Add IdP subject/email/group mapping to users, workspaces, and roles.
  - Add admin/operator APIs for identity-provider status, mapped users, and login audit review.
  - Add configurable retention policies for analyses, schedules, memories, interventions, audit logs, and usage ledger records.
  - Add retention preview/apply helpers with dry-run, audit logging, owner/workspace isolation, and legal-hold-compatible extension points.
- `frontend/`
  - Add optional SSO login entry point and admin identity/retention governance views when backend APIs exist.
  - Keep local login and existing workspace/RBAC flows working.
- `tests/`
  - Add deterministic tests using mocked OIDC discovery/token/userinfo responses.
  - Add retention dry-run/apply tests for owner/workspace isolation and audit events.
- `docs/`, `README.md`, deployment examples, and `goaldocs/`
  - Document identity-provider setup, group-role mapping, local-auth fallback, retention policies, and remaining compliance limitations.

## Non-goals

This phase does not include:

- SAML or SCIM unless OIDC group mapping cannot satisfy the target use case.
- Payment billing, invoices, customer checkout, or provider billing APIs.
- Formal legal/compliance certification, legal hold enforcement, or regulated archival attestations.
- Multi-region Redis consensus or split-brain recovery.
- Broker integration, trading execution, or fund management.
- Breaking local auth, SQLite local/demo mode, Postgres/Redis cluster mode, existing CLI commands, or Phase 1-8 web behavior.

## Acceptance Criteria

- Local username/password auth still works.
- OIDC/OAuth can be enabled by configuration and disabled by default.
- Production startup validates required OIDC settings when OIDC is enabled.
- Mocked OIDC login can provision or link a user by issuer+subject and normalized email.
- IdP groups can map to workspace roles without allowing privilege escalation by ordinary users.
- Login success/failure/link/provision events are audit logged with no tokens or secrets stored in logs.
- Admin/operator view or API shows mapped identity metadata without leaking tokens.
- Retention policies can dry-run affected rows by workspace, resource type, and cutoff date.
- Retention apply deletes/archives only authorized resources and writes audit events.
- Retention never deletes audit logs or usage ledger records unless explicitly configured and documented.
- Phase 1-8 web features and CLI commands still work.

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
ruff check tradingagents/web tests/test_web_backend.py tests/test_web_cluster_runtime.py tests/test_usage_governance.py frontend
git diff --check
```

Run CLI smoke checks:

```bash
tradingagents --help
python3 -m cli.main --help
```

Run Web smoke checks:

- Local login still works.
- Mock OIDC login provisions or links a user.
- Group-to-role mapping grants expected workspace access and denies unauthorized access.
- Identity audit records exist without secrets.
- Retention dry-run reports expected rows without mutation.
- Retention apply modifies only expected owner/workspace-scoped rows.
- Existing migration, usage reconciliation, cluster runtime, workspace RBAC, memory, schedule, intervention, and export/delete flows still work.

## Stop Conditions

Stop and ask the user if:

- Requirements require SAML, SCIM, legal hold, regulated archival certification, or payment billing.
- Live IdP credentials or production deployment access are required.
- Retention semantics could destroy ambiguous data.
- Existing Phase 1-8 behavior or CLI behavior would need to break.
- Adding dependencies creates licensing, platform, or installation concerns.

## Final Report Requirements

Report branch/commit, changed files, OIDC configuration, role-mapping rules, retention policy behavior, audit events, docs, validation evidence, skipped integration tests, and remaining Phase 10 follow-up risks.

## Codex /goal Objective

Implement Phase 9 enterprise identity and retention governance for the TradingAgents web platform by adding optional mocked-testable OIDC/OAuth login, identity-to-workspace role mapping, admin identity audit controls, and configurable retention dry-run/apply policies, while preserving Phase 1-8 behavior and CLI compatibility, with the full task contract in `goaldocs/phase-9-enterprise-identity-and-retention.md`.
