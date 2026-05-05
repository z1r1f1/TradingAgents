import { describe, expect, it } from 'vitest';
import { summarizeGovernanceEvents, type GovernanceAuditEvent } from './operatorReport';
import type { RuntimeHealth } from './api';

function auditEvent(overrides: Partial<GovernanceAuditEvent>): GovernanceAuditEvent {
  return {
    id: 1,
    event_type: 'analysis.create',
    metadata: {},
    created_at: '2026-05-05T15:00:00+00:00',
    ...overrides
  };
}

describe('operator usage report helpers', () => {
  it('summarizes current governance events into operator metrics', () => {
    const events: GovernanceAuditEvent[] = [
      auditEvent({ id: 1, event_type: 'analysis.create', resource_id: '11' }),
      auditEvent({ id: 2, event_type: 'schedule.trigger', resource_id: '12' }),
      auditEvent({ id: 3, event_type: 'intervention.run', resource_id: '13' }),
      auditEvent({ id: 4, event_type: 'cost.blocked', metadata: { reason: 'user budget exceeded' } }),
      auditEvent({ id: 5, event_type: 'idempotency.replay' }),
      auditEvent({ id: 6, event_type: 'schedule.duplicate_suppressed' })
    ];
    const runtime: RuntimeHealth = { status: 'ok', runtime_mode: 'production-cluster', storage_backend: 'postgres', coordination_backend: 'redis', postgres_configured: true, redis_configured: true };

    const summary = summarizeGovernanceEvents(events, runtime, false);

    expect(summary.analysisCreates).toBe(1);
    expect(summary.scheduleTriggers).toBe(1);
    expect(summary.continuationRuns).toBe(1);
    expect(summary.blockedRuns).toBe(1);
    expect(summary.duplicateSuppressions).toBe(2);
    expect(summary.blockedReasons).toEqual([{ reason: 'user budget exceeded', count: 1 }]);
    expect(summary.warnings).toContain('Blocked real-runner attempts recorded: user budget exceeded (1).');
    expect(summary.recentEvents).toHaveLength(5);
  });

  it('adds warnings when cluster runtime is unhealthy or no events match', () => {
    const runtime: RuntimeHealth = { status: 'degraded', runtime_mode: 'production-cluster', storage_backend: 'sqlite', coordination_backend: 'memory', postgres_configured: false, redis_configured: false };

    const summary = summarizeGovernanceEvents([], runtime, true);

    expect(summary.totalEvents).toBe(0);
    expect(summary.warnings).toEqual([
      'Cluster runtime health is inconsistent; verify Postgres storage and Redis coordination before relying on multi-instance governance reporting.',
      'Runtime health reported status degraded.',
      'No governance audit events matched the current workspace and filters yet.'
    ]);
  });
});
