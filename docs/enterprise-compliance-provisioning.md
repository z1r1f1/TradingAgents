# Enterprise Compliance and Provisioning Runbook

Phase 10 adds conservative enterprise lifecycle controls without claiming SCIM or legal certification.

## Provisioning lifecycle

Workspace owners and admins can use `/api/provisioning/users` to create or attach users to a workspace as `viewer`, `member`, or `admin`. The provisioning API rejects `owner`; owner changes remain an explicit workspace-admin action outside automated provisioning. `/api/provisioning/workspaces/{workspace_id}/users/{user_id}` supports role updates and deactivation. Every lifecycle change writes `provisioning_events` and an audit event.

## Legal holds and retention

Legal holds are managed through `/api/governance/legal-holds`. A hold can target a specific retained resource id or an entire resource type by omitting `resource_id`. Retention preview/apply returns `matched_count`, `eligible_count`, `held_count`, and `held_resources`. Retention apply skips held resources and therefore will not delete or archive them until the hold is released.

## Compliance exports

`/api/governance/compliance-export?workspace_id=...` is owner/admin only and returns:

- audit logs
- identity mappings
- retention decisions
- usage ledger records
- legal holds
- provisioning events

The export is JSON, excludes bearer tokens and OIDC client secrets, and records a `compliance.export` audit event after generation.

## IdP health checks

`/api/identity/idp-health?workspace_id=...` is owner/admin only. It checks OIDC discovery and userinfo endpoint reachability without sending bearer tokens or client secrets. A 4xx userinfo response is treated as reachable; 5xx/network errors are not.

## Limitations

This build exposes SCIM-compatible lifecycle seams, but it is not a formal SCIM 2.0 certification implementation. Live provider validation requires enterprise IdP credentials and legal/compliance approval in the deployment environment.
