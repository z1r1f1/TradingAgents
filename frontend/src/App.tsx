import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Activity, CalendarClock, History, LogOut, PlayCircle, RotateCcw } from 'lucide-react';
import {
  api,
  AgentEvent,
  AnalysisParams,
  AnalysisTask,
  InterventionSession,
  AgentMemory,
  Schedule,
  ScheduleInterval,
  SchedulePayload,
  Workspace,
  WorkspaceRole,
  RuntimeHealth,
  GovernanceAuditEvent,
  IdentityStatus,
  IdentityUser,
  RetentionResourceType,
  RetentionResult,
  streamTaskEvents
} from './api';
import { Button } from './components/ui/button';
import { Card, CardTitle } from './components/ui/card';
import { OperatorUsageReport } from './operatorReport';

export const defaultParams: AnalysisParams = {
  ticker: 'SPY',
  analysis_date: new Date().toISOString().slice(0, 10),
  analysts: ['market', 'news'],
  research_depth: 1,
  llm_provider: 'openai',
  quick_model: 'gpt-5.4-mini',
  deep_model: 'gpt-5.5',
  output_language: 'English',
  memory_ids: []
};

const isProductionWeb = import.meta.env.VITE_TRADINGAGENTS_WEB_ENV === 'production';
const initialEmail = isProductionWeb ? '' : 'demo@example.com';
const initialPassword = isProductionWeb ? '' : 'demo-password';

export function shouldShowProductionSafetyWarning(webEnv: string | undefined, apiBase: string | undefined): boolean {
  return webEnv !== 'production' || !apiBase || apiBase.includes('localhost') || apiBase.includes('127.0.0.1');
}

export function accountExportFilename(exportedAt: string): string {
  return `tradingagents-export-${exportedAt.slice(0, 10)}.json`;
}

export type ScheduleForm = {
  name: string;
  start_at: string;
  interval: ScheduleInterval;
  params: AnalysisParams;
};

export const defaultScheduleForm: ScheduleForm = {
  name: 'Daily SPY',
  start_at: `${new Date().toISOString().slice(0, 10)}T09:30`,
  interval: 'daily',
  params: defaultParams
};

export function parseAnalystsInput(value: string): string[] {
  return value
    .split(',')
    .map(item => item.trim().toLowerCase())
    .filter((item, index, items) => Boolean(item) && items.indexOf(item) === index);
}

export function buildEditableParamsFromTask(task: AnalysisTask): AnalysisParams {
  if (!task.parameters) return defaultParams;
  return { ...defaultParams, ...task.parameters, analysts: [...task.parameters.analysts] };
}

function normalizeDatetimeLocal(value: string): string {
  return value.length === 16 ? `${value}:00` : value;
}

export function buildSchedulePayload(form: ScheduleForm): SchedulePayload {
  return {
    ...form.params,
    ticker: form.params.ticker.toUpperCase(),
    name: form.name,
    start_at: normalizeDatetimeLocal(form.start_at),
    interval: form.interval,
    analysis_date_policy: 'run_date'
  };
}

export function buildScheduleFormFromSchedule(schedule: Schedule): ScheduleForm {
  return {
    name: schedule.name,
    start_at: schedule.start_at.slice(0, 16),
    interval: schedule.interval,
    params: {
      ticker: schedule.ticker,
      analysis_date: schedule.analysis_date ?? defaultParams.analysis_date,
      analysts: [...schedule.analysts],
      research_depth: schedule.research_depth,
      llm_provider: schedule.llm_provider,
      backend_url: schedule.backend_url,
      quick_model: schedule.quick_model,
      deep_model: schedule.deep_model,
      output_language: schedule.output_language,
      memory_ids: [...(schedule.memory_ids ?? [])]
    }
  };
}

export function buildMemoryOptionLabel(memory: AgentMemory): string {
  return `${memory.agent_name} · ${memory.ticker} · ${memory.analysis_date}`;
}

export function toggleMemoryId(current: number[] = [], memoryId: number): number[] {
  return current.includes(memoryId) ? current.filter(id => id !== memoryId) : [...current, memoryId];
}

export function buildInterventionLabel(session: InterventionSession): string {
  return `#${session.id} · Task ${session.source_analysis_task_id} · ${session.target_agent_name} · ${session.status}`;
}

export function formatWorkspaceRoleLabel(role: WorkspaceRole): string {
  return role[0].toUpperCase() + role.slice(1);
}

export function canManageWorkspaceMembers(role: WorkspaceRole | undefined): boolean {
  return role === 'owner' || role === 'admin';
}

export function canCreateWorkspaceResource(role: WorkspaceRole | undefined): boolean {
  return role === 'owner' || role === 'admin' || role === 'member';
}

export function buildAuditQuery(
  workspaceId: number,
  filters: { userId?: string; eventType?: string; startAt?: string; endAt?: string }
): Record<string, string> {
  return {
    workspace_id: String(workspaceId),
    ...(filters.userId ? { user_id: filters.userId } : {}),
    ...(filters.eventType ? { event_type: filters.eventType } : {}),
    ...(filters.startAt ? { start_at: filters.startAt } : {}),
    ...(filters.endAt ? { end_at: filters.endAt } : {})
  };
}

export function buildRetentionPolicy(
  workspaceId: number,
  resourceType: RetentionResourceType,
  cutoffBefore: string,
  explicitLedgerOrAudit = false
) {
  return {
    workspace_id: workspaceId,
    resource_type: resourceType,
    cutoff_before: cutoffBefore,
    include_audit_logs: explicitLedgerOrAudit && resourceType === 'audit_logs',
    include_usage_ledger: explicitLedgerOrAudit && resourceType === 'usage_ledger'
  };
}

export function buildOidcAuthorizeUrl(status: IdentityStatus, state = 'tradingagents-web'): string | null {
  if (!status.oidc_enabled || !status.authorization_endpoint || !status.client_id || !status.redirect_uri) return null;
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: status.client_id,
    redirect_uri: status.redirect_uri,
    scope: status.scope ?? 'openid email profile',
    state
  });
  return `${status.authorization_endpoint}?${params.toString()}`;
}

export function shouldShowClusterRuntimeWarning(health: RuntimeHealth | null): boolean {
  if (!health || health.runtime_mode !== 'production-cluster') return false;
  return health.storage_backend !== 'postgres' || health.coordination_backend !== 'redis' || !health.postgres_configured || !health.redis_configured;
}

function App() {
  const [token, setToken] = useState(localStorage.getItem('ta_token'));
  const [email, setEmail] = useState(initialEmail);
  const [password, setPassword] = useState(initialPassword);
  const [params, setParams] = useState(defaultParams);
  const [history, setHistory] = useState<AnalysisTask[]>([]);
  const [selected, setSelected] = useState<AnalysisTask | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [memories, setMemories] = useState<AgentMemory[]>([]);
  const [selectedMemory, setSelectedMemory] = useState<AgentMemory | null>(null);
  const [memoryQuery, setMemoryQuery] = useState('');
  const [interventions, setInterventions] = useState<InterventionSession[]>([]);
  const [selectedIntervention, setSelectedIntervention] = useState<InterventionSession | null>(null);
  const [interventionAgent, setInterventionAgent] = useState('Market Analyst');
  const [guidance, setGuidance] = useState('');
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<number | null>(null);
  const selectedWorkspace = workspaces.find(workspace => workspace.id === selectedWorkspaceId);
  const [workspaceName, setWorkspaceName] = useState('Research Desk');
  const [memberEmail, setMemberEmail] = useState('');
  const [memberRole, setMemberRole] = useState<WorkspaceRole>('viewer');
  const [auditUserId, setAuditUserId] = useState('');
  const [auditEventType, setAuditEventType] = useState('');
  const [auditStartAt, setAuditStartAt] = useState('');
  const [auditEndAt, setAuditEndAt] = useState('');
  const [auditEvents, setAuditEvents] = useState<GovernanceAuditEvent[]>([]);
  const [identityStatus, setIdentityStatus] = useState<IdentityStatus | null>(null);
  const [identityUsers, setIdentityUsers] = useState<IdentityUser[]>([]);
  const [retentionResourceType, setRetentionResourceType] = useState<RetentionResourceType>('analyses');
  const [retentionCutoff, setRetentionCutoff] = useState('2026-01-01T00:00:00+00:00');
  const [retentionResult, setRetentionResult] = useState<RetentionResult | null>(null);
  const [runtimeHealth, setRuntimeHealth] = useState<RuntimeHealth | null>(null);
  const [scheduleForm, setScheduleForm] = useState(defaultScheduleForm);
  const [editingScheduleId, setEditingScheduleId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const authenticated = Boolean(token);
  const analystsLabel = useMemo(() => params.analysts.join(', '), [params.analysts]);
  const scheduleAnalystsLabel = useMemo(() => scheduleForm.params.analysts.join(', '), [scheduleForm.params.analysts]);
  const showProductionSafetyWarning = shouldShowProductionSafetyWarning(import.meta.env.VITE_TRADINGAGENTS_WEB_ENV, import.meta.env.VITE_TRADINGAGENTS_API);

  useEffect(() => {
    void api.oidcStatus().then(setIdentityStatus).catch(() => setIdentityStatus(null));
  }, []);

  useEffect(() => {
    if (token) {
      void refreshHistory(token);
      void refreshSchedules(token);
      void refreshMemories(token);
      void refreshInterventions(token);
      void refreshWorkspaces(token);
      void api.health().then(setRuntimeHealth).catch(() => setRuntimeHealth(null));
    }
  }, [token]);

  useEffect(() => {
    if (token && selectedWorkspaceId) {
      void refreshHistory(token);
      void refreshSchedules(token);
      void refreshMemories(token);
      void refreshInterventions(token);
      void refreshAuditConsole();
    }
  }, [selectedWorkspaceId]);

  async function refreshWorkspaces(auth = token) {
    if (!auth) return;
    const data = await api.listWorkspaces(auth);
    setWorkspaces(data.items);
    setSelectedWorkspaceId(current => current ?? data.items[0]?.id ?? null);
  }

  async function refreshHistory(auth = token) {
    if (!auth) return;
    const data = await api.listAnalyses(auth, selectedWorkspaceId ? { workspace_id: String(selectedWorkspaceId) } : {});
    setHistory(data.items);
  }

  async function refreshSchedules(auth = token) {
    if (!auth) return;
    const data = await api.listSchedules(auth, selectedWorkspaceId ? { workspace_id: String(selectedWorkspaceId) } : {});
    setSchedules(data.items);
  }

  async function refreshMemories(auth = token, query = memoryQuery) {
    if (!auth) return;
    const data = await api.listMemories(auth, { ...(query ? { query } : {}), ...(selectedWorkspaceId ? { workspace_id: String(selectedWorkspaceId) } : {}), archived: 'false' });
    setMemories(data.items);
  }

  async function refreshInterventions(auth = token) {
    if (!auth) return;
    const data = await api.listInterventions(auth, selectedWorkspaceId ? { workspace_id: String(selectedWorkspaceId) } : {});
    setInterventions(data.items);
  }

  async function handleLogin(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.register(email, password).catch(() => undefined);
      const result = await api.login(email, password);
      localStorage.setItem('ta_token', result.access_token);
      setToken(result.access_token);
    } catch (err) {
      setError(String(err));
    }
  }

  function startOidcLogin() {
    const authorizeUrl = identityStatus ? buildOidcAuthorizeUrl(identityStatus) : null;
    if (authorizeUrl) window.location.href = authorizeUrl;
    else setError('SSO login is not configured.');
  }

  async function launch() {
    if (!token) return;
    setError(null);
    try {
      const task = await api.createAnalysis(token, { ...params, workspace_id: selectedWorkspaceId });
      setSelected(task);
      setEvents([]);
      await streamTaskEvents(token, task.id, event => setEvents(current => [...current.filter(item => item.sequence !== event.sequence), event].sort((a, b) => a.sequence - b.sequence)));
      const detail = await api.getAnalysis(token, task.id);
      setSelected(detail);
      setEvents(detail.events ?? []);
      await refreshHistory(token);
      await refreshMemories(token);
    } catch (err) {
      setError(String(err));
    }
  }

  async function loadTask(id: number) {
    if (!token) return;
    const detail = await api.getAnalysis(token, id);
    setSelected(detail);
    setEvents(detail.events ?? []);
  }

  async function loadTaskParameters(id: number) {
    if (!token) return;
    const detail = await api.getAnalysis(token, id);
    setSelected(detail);
    setEvents(detail.events ?? []);
    setParams(buildEditableParamsFromTask(detail));
  }

  async function rerunSelected(overrides: Partial<AnalysisParams> = {}) {
    if (!token || !selected) return;
    const task = await api.rerun(token, selected.id, overrides);
    await loadTask(task.id);
    await refreshHistory(token);
  }

  async function saveSchedule() {
    if (!token) return;
    const payload = { ...buildSchedulePayload(scheduleForm), workspace_id: selectedWorkspaceId };
    if (editingScheduleId) {
      await api.updateSchedule(token, editingScheduleId, payload);
    } else {
      await api.createSchedule(token, payload);
    }
    setEditingScheduleId(null);
    await refreshSchedules(token);
  }

  async function editSchedule(schedule: Schedule) {
    setEditingScheduleId(schedule.id);
    setScheduleForm(buildScheduleFormFromSchedule(schedule));
  }

  async function triggerSchedule(schedule: Schedule) {
    if (!token) return;
    const execution = await api.triggerSchedule(token, schedule.id);
    if (execution.analysis_task_id) await loadTask(execution.analysis_task_id);
    await refreshHistory(token);
    await refreshSchedules(token);
  }

  async function toggleSchedule(schedule: Schedule) {
    if (!token) return;
    if (schedule.status === 'active') await api.pauseSchedule(token, schedule.id);
    else await api.resumeSchedule(token, schedule.id);
    await refreshSchedules(token);
  }

  async function removeSchedule(schedule: Schedule) {
    if (!token) return;
    await api.deleteSchedule(token, schedule.id);
    await refreshSchedules(token);
  }


  async function createIntervention() {
    if (!token || !selected) return;
    const session = await api.createIntervention(token, selected.id, interventionAgent);
    setSelectedIntervention(session);
    await refreshInterventions(token);
    const detail = await api.getAnalysis(token, selected.id);
    setSelected(detail);
  }

  async function createWorkspace() {
    if (!token || !workspaceName.trim()) return;
    const workspace = await api.createWorkspace(token, workspaceName.trim());
    setSelectedWorkspaceId(workspace.id);
    await refreshWorkspaces(token);
  }

  async function addWorkspaceMember() {
    if (!token || !selectedWorkspaceId || !memberEmail.trim()) return;
    await api.addWorkspaceMember(token, selectedWorkspaceId, memberEmail.trim(), memberRole);
    setMemberEmail('');
    await refreshWorkspaces(token);
  }

  async function updateWorkspaceMemberRole(userId: number, role: WorkspaceRole) {
    if (!token || !selectedWorkspaceId) return;
    await api.updateWorkspaceMember(token, selectedWorkspaceId, userId, role);
    await refreshWorkspaces(token);
  }

  async function removeWorkspaceMember(userId: number) {
    if (!token || !selectedWorkspaceId) return;
    await api.removeWorkspaceMember(token, selectedWorkspaceId, userId);
    await refreshWorkspaces(token);
  }

  async function refreshAuditConsole() {
    if (!token || !selectedWorkspaceId) return;
    const data = await api.listGovernanceAudit(
      token,
      buildAuditQuery(selectedWorkspaceId, {
        userId: auditUserId,
        eventType: auditEventType,
        startAt: auditStartAt,
        endAt: auditEndAt
      })
    );
    setAuditEvents(data.items);
  }

  async function refreshIdentityConsole() {
    if (!token) return;
    const status = await api.identityStatus(token);
    setIdentityStatus(status);
    const users = await api.listIdentityUsers(token, selectedWorkspaceId ? { workspace_id: String(selectedWorkspaceId) } : {});
    setIdentityUsers(users.items);
  }

  async function previewRetention() {
    if (!token || !selectedWorkspaceId) return;
    const result = await api.retentionPreview(token, buildRetentionPolicy(selectedWorkspaceId, retentionResourceType, retentionCutoff, false));
    setRetentionResult(result);
    await refreshAuditConsole();
  }

  async function loadIntervention(id: number) {
    if (!token) return;
    setSelectedIntervention(await api.getIntervention(token, id));
  }

  async function addGuidance() {
    if (!token || !selectedIntervention || !guidance.trim()) return;
    await api.appendInterventionMessage(token, selectedIntervention.id, guidance.trim());
    setGuidance('');
    await loadIntervention(selectedIntervention.id);
  }

  async function setInterventionStatus(action: 'pause' | 'resume' | 'close') {
    if (!token || !selectedIntervention) return;
    if (action === 'pause') await api.pauseIntervention(token, selectedIntervention.id);
    if (action === 'resume') await api.resumeIntervention(token, selectedIntervention.id);
    if (action === 'close') await api.closeIntervention(token, selectedIntervention.id);
    await loadIntervention(selectedIntervention.id);
    await refreshInterventions(token);
  }

  async function runContinuation() {
    if (!token || !selectedIntervention) return;
    await api.runIntervention(token, selectedIntervention.id);
    await loadIntervention(selectedIntervention.id);
  }

  async function deleteSelectedIntervention() {
    if (!token || !selectedIntervention) return;
    await api.deleteIntervention(token, selectedIntervention.id);
    setSelectedIntervention(null);
    await refreshInterventions(token);
    if (selected) setSelected(await api.getAnalysis(token, selected.id));
  }

  async function exportAccount() {
    if (!token) return;
    const data = await api.exportAccount(token);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = accountExportFilename(data.exported_at);
    link.click();
    URL.revokeObjectURL(url);
  }

  async function deleteSelectedAnalysis() {
    if (!token || !selected) return;
    await api.deleteAnalysis(token, selected.id);
    setSelected(null);
    setEvents([]);
    await refreshHistory(token);
    await refreshMemories(token);
    await refreshInterventions(token);
  }

  function logout() {
    if (token) void api.logout(token).catch(() => undefined);
    localStorage.removeItem('ta_token');
    setToken(null);
    setSelected(null);
    setHistory([]);
    setSchedules([]);
    setMemories([]);
    setInterventions([]);
    setSelectedIntervention(null);
    setWorkspaces([]);
    setSelectedWorkspaceId(null);
    setRuntimeHealth(null);
  }

  if (!authenticated) {
    return <main className="mx-auto flex min-h-screen max-w-md items-center"><Card><CardTitle>TradingAgents Login</CardTitle><form className="space-y-3" onSubmit={handleLogin}><input className="w-full rounded bg-slate-800 p-2" value={email} onChange={e => setEmail(e.target.value)} /><input className="w-full rounded bg-slate-800 p-2" type="password" value={password} onChange={e => setPassword(e.target.value)} /><Button className="w-full">Log in / Register</Button>{identityStatus?.oidc_enabled && <Button type="button" className="w-full bg-slate-200" onClick={startOidcLogin}>Continue with SSO</Button>}{error && <p className="text-sm text-red-300">{error}</p>}</form></Card></main>;
  }

  return <main className="mx-auto max-w-7xl space-y-5 p-6"><header className="flex items-center justify-between"><h1 className="text-3xl font-bold">TradingAgents Web Platform</h1><div className="flex gap-2"><Button onClick={exportAccount} className="bg-slate-200">Export account</Button><Button onClick={logout} className="bg-slate-200"><LogOut className="mr-2 inline" size={16}/>Logout</Button></div></header>{showProductionSafetyWarning && <p className="rounded border border-amber-500 bg-amber-950 p-3 text-amber-100">Production safety warning: configure TRADINGAGENTS_WEB_ENV=production, exact API origin, disabled registration, strong auth secret, HTTPS, backups, audit review, and rate limits before internet exposure.</p>}{shouldShowClusterRuntimeWarning(runtimeHealth) && <p className="rounded border border-amber-500 bg-amber-950 p-3 text-amber-100">Cluster runtime warning: production-cluster mode must report Postgres storage, Redis coordination, and configured dependencies before multi-instance use.</p>}{error && <p className="rounded bg-red-950 p-3 text-red-200">{error}</p>}<Card><CardTitle>Workspace governance</CardTitle><div className="grid gap-3 lg:grid-cols-[280px_1fr_1fr]"><div className="space-y-2"><select className="w-full rounded bg-slate-800 p-2" value={selectedWorkspaceId ?? ''} onChange={e => setSelectedWorkspaceId(Number(e.target.value))}>{workspaces.map(workspace => <option key={workspace.id} value={workspace.id}>{workspace.name} · {formatWorkspaceRoleLabel(workspace.role)}</option>)}</select><input className="w-full rounded bg-slate-800 p-2" value={workspaceName} onChange={e => setWorkspaceName(e.target.value)} /><Button onClick={createWorkspace}>Create workspace</Button><p className="text-xs text-slate-400">Budget status: real-runner caps are enforced by the API before new analysis, scheduled trigger, due schedule, or continuation runs. Phase 8 operator reporting below summarizes the audit events currently exposed by this build.</p></div><div className="space-y-2"><p className="text-sm text-slate-300">Members {selectedWorkspace ? `· ${selectedWorkspace.name}` : ''}</p><input className="w-full rounded bg-slate-800 p-2" placeholder="member@example.com" value={memberEmail} onChange={e => setMemberEmail(e.target.value)} /><select className="w-full rounded bg-slate-800 p-2" value={memberRole} onChange={e => setMemberRole(e.target.value as WorkspaceRole)}><option value="viewer">viewer</option><option value="member">member</option><option value="admin">admin</option><option value="owner">owner</option></select><Button disabled={!canManageWorkspaceMembers(selectedWorkspace?.role)} onClick={addWorkspaceMember}>Add/update member</Button>{selectedWorkspace?.members?.map(member => <div key={member.user_id} className="flex flex-wrap items-center gap-2 text-xs text-slate-400"><span>{member.email}</span><select className="rounded bg-slate-800 p-1" value={member.role} disabled={!canManageWorkspaceMembers(selectedWorkspace?.role)} onChange={e => updateWorkspaceMemberRole(member.user_id, e.target.value as WorkspaceRole)}><option value="viewer">viewer</option><option value="member">member</option><option value="admin">admin</option><option value="owner">owner</option></select><Button disabled={!canManageWorkspaceMembers(selectedWorkspace?.role)} onClick={() => removeWorkspaceMember(member.user_id)}>Remove</Button></div>)}</div><div className="space-y-2"><div className="grid gap-2 md:grid-cols-2"><input className="rounded bg-slate-800 p-2" placeholder="audit user id" value={auditUserId} onChange={e => setAuditUserId(e.target.value)} /><input className="rounded bg-slate-800 p-2" placeholder="event type" value={auditEventType} onChange={e => setAuditEventType(e.target.value)} /><input className="rounded bg-slate-800 p-2" placeholder="start ISO time" value={auditStartAt} onChange={e => setAuditStartAt(e.target.value)} /><input className="rounded bg-slate-800 p-2" placeholder="end ISO time" value={auditEndAt} onChange={e => setAuditEndAt(e.target.value)} /></div><div className="flex flex-wrap gap-2"><Button onClick={refreshAuditConsole}>Refresh operator report</Button><Button onClick={refreshIdentityConsole}>Identity mappings</Button><Button onClick={previewRetention}>Preview retention</Button></div><div className="grid gap-2 md:grid-cols-2"><select className="rounded bg-slate-800 p-2" value={retentionResourceType} onChange={e => setRetentionResourceType(e.target.value as RetentionResourceType)}><option value="analyses">analyses</option><option value="schedules">schedules</option><option value="memories">memories</option><option value="interventions">interventions</option><option value="audit_logs">audit logs</option><option value="usage_ledger">usage ledger</option></select><input className="rounded bg-slate-800 p-2" value={retentionCutoff} onChange={e => setRetentionCutoff(e.target.value)} /></div><p className="text-xs text-slate-400">SSO: {identityStatus?.oidc_enabled ? `enabled for ${identityStatus.issuer_url}` : 'disabled'} · mapped identities: {identityUsers.length}</p>{retentionResult && <p className="text-xs text-slate-400">Retention {retentionResult.resource_type}: {retentionResult.matched_count ?? retentionResult.affected_count ?? 0} rows</p>}<OperatorUsageReport auditEvents={auditEvents} runtimeHealth={runtimeHealth} showClusterRuntimeWarning={shouldShowClusterRuntimeWarning(runtimeHealth)} /><div className="max-h-36 overflow-auto rounded bg-slate-950 p-2 text-xs">{auditEvents.map(event => <p key={event.id}>{JSON.stringify(event)}</p>)}</div></div></div></Card><div className="grid gap-5 lg:grid-cols-[380px_1fr]"><Card><CardTitle><PlayCircle className="mr-2 inline"/>Configure analysis</CardTitle><div className="space-y-3"><input className="w-full rounded bg-slate-800 p-2" value={params.ticker} onChange={e => setParams({...params, ticker: e.target.value.toUpperCase()})} /><input className="w-full rounded bg-slate-800 p-2" type="date" value={params.analysis_date} onChange={e => setParams({...params, analysis_date: e.target.value})} /><input className="w-full rounded bg-slate-800 p-2" value={analystsLabel} onChange={e => setParams({...params, analysts: parseAnalystsInput(e.target.value)})} /><input className="w-full rounded bg-slate-800 p-2" type="number" min="1" max="10" value={params.research_depth} onChange={e => setParams({...params, research_depth: Number(e.target.value)})} /><input className="w-full rounded bg-slate-800 p-2" value={params.llm_provider} onChange={e => setParams({...params, llm_provider: e.target.value})} /><input className="w-full rounded bg-slate-800 p-2" value={params.quick_model} onChange={e => setParams({...params, quick_model: e.target.value})} /><input className="w-full rounded bg-slate-800 p-2" value={params.deep_model} onChange={e => setParams({...params, deep_model: e.target.value})} /><input className="w-full rounded bg-slate-800 p-2" value={params.output_language} onChange={e => setParams({...params, output_language: e.target.value})} /><div className="rounded border border-slate-700 p-2 text-sm"><p className="mb-2 text-slate-300">Attach memories</p>{memories.slice(0, 6).map(memory => <label key={memory.id} className="block"><input type="checkbox" checked={(params.memory_ids ?? []).includes(memory.id)} onChange={() => setParams({...params, memory_ids: toggleMemoryId(params.memory_ids, memory.id)})} /> {buildMemoryOptionLabel(memory)}</label>)}</div><Button disabled={!canCreateWorkspaceResource(selectedWorkspace?.role)} onClick={launch}>Launch analysis</Button></div></Card><Card><CardTitle><Activity className="mr-2 inline"/>Realtime progress and result</CardTitle>{selected ? <div className="space-y-4"><p className="text-sm text-slate-300">Task #{selected.id} · {selected.status} · {selected.parameters?.ticker}</p><div className="max-h-72 overflow-auto rounded bg-slate-950 p-3 text-sm">{events.map(event => <p key={event.sequence}><span className="text-emerald-300">#{event.sequence} {event.agent}</span> {event.event_type}: {event.message}</p>)}</div><h3 className="font-semibold">Decision: {selected.final_decision?.decision ?? 'pending'}</h3><p className="text-slate-300">{selected.final_decision?.rationale}</p>{selected.attached_memories?.length ? <div className="rounded border border-slate-700 p-3"><h4 className="font-semibold">Attached memories</h4>{selected.attached_memories.map(memory => <p key={memory.id} className="text-sm text-slate-300">{buildMemoryOptionLabel(memory)}</p>)}</div> : null}<div className="rounded border border-slate-700 p-3"><h4 className="font-semibold">Human intervention</h4><div className="flex flex-wrap gap-2"><select className="rounded bg-slate-800 p-2" value={interventionAgent} onChange={e => setInterventionAgent(e.target.value)}><option>Market Analyst</option><option>News Analyst</option><option>Research Manager</option><option>Trader</option><option>Portfolio Manager</option></select><Button disabled={!canCreateWorkspaceResource(selectedWorkspace?.role)} onClick={createIntervention}>Start session</Button></div>{selected.intervention_sessions?.map(session => <button key={session.id} className="mt-2 block text-left text-sm text-emerald-300" onClick={() => loadIntervention(session.id)}>{buildInterventionLabel(session)}</button>)}</div>{selected.report_sections?.map(section => <article key={section.section_name} className="rounded border border-slate-700 p-3"><h4 className="font-semibold">{section.section_name}</h4><p className="whitespace-pre-wrap text-sm text-slate-300">{section.content}</p></article>)}<div className="flex flex-wrap gap-2"><Button onClick={() => selected && setParams(buildEditableParamsFromTask(selected))}>Load parameters into form</Button><Button onClick={() => rerunSelected({})}><RotateCcw className="mr-2 inline" size={16}/>Rerun with same parameters</Button><Button className="bg-red-300" onClick={deleteSelectedAnalysis}>Delete analysis</Button></div></div> : <p className="text-slate-400">Launch or select a historical analysis.</p>}</Card></div><Card><CardTitle><CalendarClock className="mr-2 inline"/>Scheduled analysis</CardTitle><div className="grid gap-4 lg:grid-cols-[360px_1fr]"><div className="space-y-3"><input className="w-full rounded bg-slate-800 p-2" value={scheduleForm.name} onChange={e => setScheduleForm({...scheduleForm, name: e.target.value})} /><input className="w-full rounded bg-slate-800 p-2" type="datetime-local" value={scheduleForm.start_at} onChange={e => setScheduleForm({...scheduleForm, start_at: e.target.value})} /><select className="w-full rounded bg-slate-800 p-2" value={scheduleForm.interval} onChange={e => setScheduleForm({...scheduleForm, interval: e.target.value as ScheduleInterval})}><option value="daily">daily</option><option value="weekly">weekly</option><option value="monthly">monthly</option></select><input className="w-full rounded bg-slate-800 p-2" value={scheduleForm.params.ticker} onChange={e => setScheduleForm({...scheduleForm, params: {...scheduleForm.params, ticker: e.target.value.toUpperCase()}})} /><input className="w-full rounded bg-slate-800 p-2" value={scheduleAnalystsLabel} onChange={e => setScheduleForm({...scheduleForm, params: {...scheduleForm.params, analysts: parseAnalystsInput(e.target.value)}})} /><input className="w-full rounded bg-slate-800 p-2" type="number" min="1" max="10" value={scheduleForm.params.research_depth} onChange={e => setScheduleForm({...scheduleForm, params: {...scheduleForm.params, research_depth: Number(e.target.value)}})} /><div className="rounded border border-slate-700 p-2 text-sm"><p className="mb-2 text-slate-300">Schedule memories</p>{memories.slice(0, 6).map(memory => <label key={memory.id} className="block"><input type="checkbox" checked={(scheduleForm.params.memory_ids ?? []).includes(memory.id)} onChange={() => setScheduleForm({...scheduleForm, params: {...scheduleForm.params, memory_ids: toggleMemoryId(scheduleForm.params.memory_ids, memory.id)}})} /> {buildMemoryOptionLabel(memory)}</label>)}</div><Button disabled={!canCreateWorkspaceResource(selectedWorkspace?.role)} onClick={saveSchedule}>{editingScheduleId ? 'Save schedule' : 'Create schedule'}</Button></div><div className="space-y-2">{schedules.map(schedule => <article key={schedule.id} className="rounded border border-slate-700 p-3"><div className="flex items-start justify-between gap-2"><div><h3 className="font-semibold">{schedule.name}</h3><p className="text-sm text-slate-400">{schedule.ticker} · {schedule.interval} · {schedule.status} · next {schedule.next_run_at}</p><p className="text-xs text-slate-500">Recent: {schedule.executions?.[0]?.status ?? 'no executions yet'}</p></div><div className="flex flex-wrap justify-end gap-2"><Button onClick={() => editSchedule(schedule)}>Edit</Button><Button onClick={() => triggerSchedule(schedule)}>Trigger</Button><Button onClick={() => toggleSchedule(schedule)}>{schedule.status === 'active' ? 'Pause' : 'Resume'}</Button><Button className="bg-red-300" onClick={() => removeSchedule(schedule)}>Delete</Button></div></div></article>)}</div></div></Card><Card><CardTitle>Intervention session</CardTitle>{selectedIntervention ? <div className="space-y-3"><p className="text-sm text-slate-300">{buildInterventionLabel(selectedIntervention)}</p><textarea className="w-full rounded bg-slate-800 p-2" value={guidance} onChange={e => setGuidance(e.target.value)} placeholder="Add explicit guidance" /><div className="flex flex-wrap gap-2"><Button onClick={addGuidance}>Add guidance</Button><Button onClick={() => setInterventionStatus('pause')}>Pause</Button><Button onClick={() => setInterventionStatus('resume')}>Resume</Button><Button onClick={runContinuation}>Run continuation</Button><Button onClick={() => setInterventionStatus('close')}>Close</Button><Button className="bg-red-300" onClick={deleteSelectedIntervention}>Delete session</Button></div><div className="rounded bg-slate-950 p-3 text-sm">{selectedIntervention.messages?.map(message => <p key={message.id}><span className="text-emerald-300">{message.author}</span>: {message.content}</p>)}{selectedIntervention.events?.map(event => <p key={`e-${event.id}`}><span className="text-blue-300">{event.event_type}</span>: {event.message}</p>)}{selectedIntervention.outputs?.map(output => <p key={`o-${output.id}`} className="whitespace-pre-wrap text-slate-300">{output.content}</p>)}</div></div> : <p className="text-slate-400">Select or start an intervention session from an analysis.</p>}<div className="mt-3 grid gap-2 md:grid-cols-2 lg:grid-cols-3">{interventions.map(session => <button key={session.id} className="rounded border border-slate-700 p-2 text-left text-sm" onClick={() => loadIntervention(session.id)}>{buildInterventionLabel(session)}</button>)}</div></Card><Card><CardTitle>Agent memories</CardTitle><div className="mb-3 flex gap-2"><input className="w-full rounded bg-slate-800 p-2" placeholder="Search memories" value={memoryQuery} onChange={e => setMemoryQuery(e.target.value)} /><Button onClick={() => refreshMemories()}>Search</Button></div><div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">{memories.map(memory => <article key={memory.id} className="rounded border border-slate-700 p-3"><button className="text-left font-semibold" onClick={() => setSelectedMemory(memory)}>{buildMemoryOptionLabel(memory)}</button><p className="line-clamp-2 text-sm text-slate-400">{memory.title}</p><Button onClick={() => { if (token) void api.archiveMemory(token, memory.id).then(() => refreshMemories()); }}>Archive</Button></article>)}</div>{selectedMemory ? <div className="mt-3 rounded bg-slate-950 p-3"><h3 className="font-semibold">{selectedMemory.title}</h3><p className="whitespace-pre-wrap text-sm text-slate-300">{selectedMemory.content}</p></div> : null}</Card><Card><CardTitle><History className="mr-2 inline"/>History</CardTitle><div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">{history.map(item => <button key={item.id} onClick={() => loadTask(item.id)} className="rounded border border-slate-700 p-3 text-left hover:bg-slate-800"><strong>#{item.id} {item.ticker}</strong><p className="text-sm text-slate-400">{item.analysis_date} · {item.status} · {item.decision ?? 'no decision'}</p><span className="mt-2 inline-block rounded bg-slate-700 px-2 py-1 text-xs" onClick={event => { event.stopPropagation(); void loadTaskParameters(item.id); }}>Load/edit parameters</span></button>)}</div></Card></main>;
}

export default App;
