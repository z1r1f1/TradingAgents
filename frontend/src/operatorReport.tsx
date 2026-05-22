import type { RuntimeHealth } from './api';

export type GovernanceAuditEvent = {
  id: number;
  user_id?: number | null;
  workspace_id?: number | null;
  event_type: string;
  resource_type?: string | null;
  resource_id?: string | null;
  metadata: Record<string, unknown>;
  ip_address?: string | null;
  created_at: string;
};

export type OperatorUsageSummary = {
  totalEvents: number;
  analysisCreates: number;
  scheduleTriggers: number;
  continuationRuns: number;
  blockedRuns: number;
  duplicateSuppressions: number;
  blockedReasons: Array<{ reason: string; count: number }>;
  recentEvents: GovernanceAuditEvent[];
  warnings: string[];
};

function countEvents(events: GovernanceAuditEvent[], eventType: string): number {
  return events.filter(event => event.event_type === eventType).length;
}

function readBlockedReason(event: GovernanceAuditEvent): string {
  const reason = event.metadata.reason;
  return typeof reason === 'string' && reason.trim() ? reason : '未说明的预算拦截';
}

export function summarizeGovernanceEvents(
  events: GovernanceAuditEvent[],
  runtimeHealth: RuntimeHealth | null,
  showClusterRuntimeWarning: boolean
): OperatorUsageSummary {
  const blockedEvents = events.filter(event => event.event_type === 'cost.blocked');
  const blockedReasonCounts = new Map<string, number>();
  for (const event of blockedEvents) {
    const reason = readBlockedReason(event);
    blockedReasonCounts.set(reason, (blockedReasonCounts.get(reason) ?? 0) + 1);
  }

  const warnings: string[] = [];
  if (showClusterRuntimeWarning) {
    warnings.push('集群运行状态不一致；依赖多实例治理报表前，请确认 Postgres 存储与 Redis 协调均正常。');
  }
  if (runtimeHealth && runtimeHealth.status !== 'ok') {
    warnings.push(`运行时健康状态：${runtimeHealth.status}。`);
  }
  if (blockedEvents.length > 0) {
    const reasons = [...blockedReasonCounts.entries()].map(([reason, count]) => `${reason} (${count})`).join(', ');
    warnings.push(`已记录真实 Runner 拦截：${reasons}。`);
  }
  if (events.length === 0) {
    warnings.push('当前工作区与筛选条件下暂无治理审计事件。');
  }

  return {
    totalEvents: events.length,
    analysisCreates: countEvents(events, 'analysis.create'),
    scheduleTriggers: countEvents(events, 'schedule.trigger'),
    continuationRuns: countEvents(events, 'intervention.run'),
    blockedRuns: blockedEvents.length,
    duplicateSuppressions: countEvents(events, 'schedule.duplicate_suppressed') + countEvents(events, 'idempotency.replay'),
    blockedReasons: [...blockedReasonCounts.entries()].map(([reason, count]) => ({ reason, count })),
    recentEvents: events.slice(0, 5),
    warnings
  };
}

function formatEventMetadata(event: GovernanceAuditEvent): string {
  if (event.event_type === 'cost.blocked') return readBlockedReason(event);
  if (event.resource_type && event.resource_id) return `${event.resource_type} #${event.resource_id}`;
  if (event.resource_id) return `资源 #${event.resource_id}`;
  return '无附加元数据';
}

export function OperatorUsageReport({
  auditEvents,
  runtimeHealth,
  showClusterRuntimeWarning
}: {
  auditEvents: GovernanceAuditEvent[];
  runtimeHealth: RuntimeHealth | null;
  showClusterRuntimeWarning: boolean;
}) {
  const summary = summarizeGovernanceEvents(auditEvents, runtimeHealth, showClusterRuntimeWarning);

  return (
    <div className="space-y-3 rounded border border-slate-700 p-3">
      <div>
        <h3 className="text-sm font-semibold text-slate-200">运营用量报告</h3>
        <p className="text-xs text-slate-400">
          基于 <code>GET /api/governance/audit</code> 与运行时健康状态生成；仅汇总当前版本已暴露的后端能力。
        </p>
      </div>
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        <Metric label="审计事件" value={summary.totalEvents} />
        <Metric label="分析启动" value={summary.analysisCreates} />
        <Metric label="计划触发" value={summary.scheduleTriggers} />
        <Metric label="延续分析" value={summary.continuationRuns} />
        <Metric label="拦截运行" value={summary.blockedRuns} />
        <Metric label="重复抑制" value={summary.duplicateSuppressions} />
      </div>
      {summary.blockedReasons.length ? (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">拦截原因</p>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-amber-200">
            {summary.blockedReasons.map(item => (
              <span key={item.reason} className="rounded border border-amber-700 bg-amber-950 px-2 py-1">
                {item.reason} · {item.count}
              </span>
            ))}
          </div>
        </div>
      ) : null}
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">风险与备注</p>
        {summary.warnings.map(message => (
          <p key={message} className="rounded bg-slate-950 p-2 text-xs text-slate-300">
            {message}
          </p>
        ))}
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">最近审计事件</p>
        <div className="mt-2 max-h-40 space-y-2 overflow-auto rounded bg-slate-950 p-2 text-xs text-slate-300">
          {summary.recentEvents.map(event => (
            <div key={event.id} className="rounded border border-slate-800 p-2">
              <p className="font-medium text-slate-200">{event.event_type}</p>
              <p>{event.created_at}</p>
              <p>{formatEventMetadata(event)}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded bg-slate-950 p-2">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="text-lg font-semibold text-slate-100">{value}</p>
    </div>
  );
}
