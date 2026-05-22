# Phase 11 Goal: Live IdP SCIM Certification and Legal Attestation

## Objective

Validate TradingAgents Phase 10 enterprise provisioning and compliance controls against a chosen enterprise IdP and formal legal/compliance requirements.

## Scope

- Select a target SCIM/vendor contract and map TradingAgents provisioning APIs to that contract.
- Run live OIDC discovery, userinfo, and lifecycle tests with approved non-production credentials.
- Define legal-hold retention schedules, evidence preservation rules, and export attestation wording with counsel/compliance stakeholders.
- Add provider-specific runbooks and certification evidence under `docs/`.

## Non-goals

- Do not claim certification without approved vendor/legal evidence.
- Do not expose bearer tokens, client secrets, or production credentials in logs, exports, or tests.

## Validation

- Provider sandbox provisioning lifecycle tests pass.
- Legal-hold retention tests pass with approved policy fixtures.
- Compliance export review confirms no secrets and accepted evidence shape.
