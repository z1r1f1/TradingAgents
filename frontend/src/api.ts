export type AnalysisParams = {
  workspace_id?: number | null;
  ticker: string;
  analysis_date: string;
  analysts: string[];
  research_depth: number;
  llm_provider: string;
  backend_url?: string | null;
  quick_model: string;
  deep_model: string;
  output_language: string;
  memory_ids?: number[];
};

export type AnalysisTask = {
  id: number;
  workspace_id?: number | null;
  status: string;
  ticker?: string;
  analysis_date?: string;
  decision?: string | null;
  parameters?: AnalysisParams;
  final_decision?: { decision: string; rationale: string } | null;
  report_sections?: { section_name: string; content: string }[];
  events?: AgentEvent[];
  attached_memories?: AgentMemory[];
  intervention_sessions?: InterventionSession[];
};

export type AgentEvent = { sequence: number; agent: string; event_type: string; message: string; created_at: string };
export type AgentMemory = {
  id: number;
  user_id: number;
  workspace_id?: number | null;
  source_analysis_task_id: number;
  ticker: string;
  analysis_date: string;
  agent_name: string;
  title: string;
  content: string;
  tags: Record<string, unknown>;
  archived: boolean;
  created_at: string;
};
export type ScheduleInterval = 'daily' | 'weekly' | 'monthly';
export type ScheduleStatus = 'active' | 'paused';

export type SchedulePayload = Omit<AnalysisParams, 'analysis_date'> & {
  name: string;
  analysis_date?: string;
  start_at: string;
  interval: ScheduleInterval;
  analysis_date_policy?: 'run_date' | 'fixed';
};

export type Schedule = SchedulePayload & {
  id: number;
  status: ScheduleStatus;
  next_run_at: string;
  last_run_at?: string | null;
  executions?: ScheduleExecution[];
};

export type InterventionStatus = 'open' | 'paused' | 'closed' | 'failed';
export type InterventionMessage = { id: number; session_id: number; sequence: number; author: string; content: string; created_at: string };
export type InterventionEvent = { id: number; session_id: number; sequence: number; event_type: string; message: string; payload: Record<string, unknown>; created_at: string };
export type InterventionOutput = { id: number; session_id: number; target_agent_name: string; content: string; context: Record<string, unknown>; created_at: string };
export type InterventionSession = {
  id: number;
  user_id: number;
  workspace_id?: number | null;
  source_analysis_task_id: number;
  target_agent_name: string;
  status: InterventionStatus;
  created_at: string;
  updated_at: string;
  closed_at?: string | null;
  messages?: InterventionMessage[];
  events?: InterventionEvent[];
  outputs?: InterventionOutput[];
};

export type ScheduleExecution = {
  id: number;
  schedule_id: number;
  analysis_task_id?: number | null;
  status: string;
  triggered_by: string;
  started_at: string;
  completed_at?: string | null;
  error?: string | null;
};

export type AccountExport = {
  format: string;
  exported_at: string;
  workspace?: Workspace | null;
  analyses: AnalysisTask[];
  memories: AgentMemory[];
  schedules: Schedule[];
  interventions: InterventionSession[];
};

export type WorkspaceRole = 'owner' | 'admin' | 'member' | 'viewer';
export type WorkspaceMember = { workspace_id: number; user_id: number; email: string; role: WorkspaceRole; created_at: string; updated_at: string };
export type Workspace = {
  id: number;
  name: string;
  kind: 'personal' | 'shared';
  role: WorkspaceRole;
  created_by_user_id: number;
  created_at: string;
  updated_at: string;
  members?: WorkspaceMember[];
};

export type RuntimeHealth = {
  status: string;
  runtime_mode?: string;
  storage_backend?: string;
  coordination_backend?: string;
  postgres_configured?: boolean;
  redis_configured?: boolean;
};

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

export type IdentityStatus = {
  oidc_enabled: boolean;
  issuer_url?: string | null;
  authorization_endpoint?: string | null;
  client_id?: string | null;
  redirect_uri?: string | null;
  scope?: string | null;
  group_claim: string;
  mapped_groups: string[];
};

export type IdentityUser = {
  id: number;
  user_id: number;
  provider: string;
  issuer: string;
  subject: string;
  email: string;
  groups: string[];
  created_at: string;
  updated_at: string;
  last_login_at: string;
};

export type RetentionResourceType = 'analyses' | 'schedules' | 'memories' | 'interventions' | 'audit_logs' | 'usage_ledger';
export type RetentionPolicy = {
  workspace_id: number;
  resource_type: RetentionResourceType;
  cutoff_before: string;
  archive_memories?: boolean;
  include_audit_logs?: boolean;
  include_usage_ledger?: boolean;
};
export type RetentionResult = {
  workspace_id: number;
  resource_type: RetentionResourceType;
  cutoff_before: string;
  matched_count?: number;
  eligible_count?: number;
  held_count?: number;
  held_resources?: { id: string; resource_type: string }[];
  affected_count?: number;
  dry_run?: boolean;
  applied?: boolean;
  mode?: string;
};

export type LegalHold = {
  id: number;
  workspace_id: number;
  resource_type: RetentionResourceType;
  resource_id?: string | null;
  reason: string;
  expires_at?: string | null;
  created_by_user_id?: number | null;
  created_at: string;
  released_at?: string | null;
  release_reason?: string | null;
  active: boolean;
};

export type ProvisioningEvent = {
  id: number;
  workspace_id: number;
  actor_user_id?: number | null;
  target_user_id?: number | null;
  target_email: string;
  action: string;
  role?: WorkspaceRole | null;
  status: string;
  external_id?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type IdpHealth = {
  ok: boolean;
  oidc_enabled: boolean;
  issuer_url?: string | null;
  checks: { name: string; ok: boolean; status_code?: number | null; reason?: string }[];
  reason?: string;
};

export type ComplianceExport = {
  format: string;
  exported_at: string;
  workspace?: Workspace | null;
  audit_logs: GovernanceAuditEvent[];
  identity_mappings: IdentityUser[];
  retention_decisions: GovernanceAuditEvent[];
  usage_ledger: unknown[];
  legal_holds: LegalHold[];
  provisioning_events: ProvisioningEvent[];
};

const API_BASE = import.meta.env.VITE_TRADINGAGENTS_API ?? 'http://localhost:8000';

async function request<T>(path: string, token: string | null, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init.headers ?? {}) }
  });
  if (!response.ok) throw new Error(await response.text());
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<RuntimeHealth>('/api/health', null),
  login: (email: string, password: string) => request<{ access_token: string; user: { email: string } }>('/api/auth/login', null, { method: 'POST', body: JSON.stringify({ email, password }) }),
  register: (email: string, password: string) => request('/api/auth/register', null, { method: 'POST', body: JSON.stringify({ email, password }) }),
  logout: (token: string) => request('/api/auth/logout', token, { method: 'POST' }),
  listWorkspaces: (token: string) => request<{ items: Workspace[] }>('/api/workspaces', token),
  createWorkspace: (token: string, name: string) => request<Workspace>('/api/workspaces', token, { method: 'POST', body: JSON.stringify({ name }) }),
  getWorkspace: (token: string, id: number) => request<Workspace>(`/api/workspaces/${id}`, token),
  addWorkspaceMember: (token: string, id: number, email: string, role: WorkspaceRole) => request<WorkspaceMember>(`/api/workspaces/${id}/members`, token, { method: 'POST', body: JSON.stringify({ email, role }) }),
  updateWorkspaceMember: (token: string, id: number, userId: number, role: WorkspaceRole) => request<WorkspaceMember>(`/api/workspaces/${id}/members/${userId}`, token, { method: 'PATCH', body: JSON.stringify({ role }) }),
  removeWorkspaceMember: (token: string, id: number, userId: number) => request<void>(`/api/workspaces/${id}/members/${userId}`, token, { method: 'DELETE' }),
  listGovernanceAudit: (token: string, params: Record<string, string> = {}) => request<{ items: GovernanceAuditEvent[] }>(`/api/governance/audit?${new URLSearchParams(params)}`, token),
  oidcStatus: () => request<IdentityStatus>('/api/auth/oidc/status', null),
  oidcCallback: (code: string, redirectUri?: string) => request<{ access_token: string; user: { email: string } }>('/api/auth/oidc/callback', null, { method: 'POST', body: JSON.stringify({ code, redirect_uri: redirectUri }) }),
  identityStatus: (token: string) => request<IdentityStatus>('/api/identity/status', token),
  listIdentityUsers: (token: string, params: Record<string, string> = {}) => request<{ items: IdentityUser[] }>(`/api/identity/users?${new URLSearchParams(params)}`, token),
  idpHealth: (token: string, workspaceId: number) => request<IdpHealth>(`/api/identity/idp-health?${new URLSearchParams({ workspace_id: String(workspaceId) })}`, token),
  provisionUser: (token: string, workspaceId: number, email: string, role: Exclude<WorkspaceRole, 'owner'>) => request<WorkspaceMember>('/api/provisioning/users', token, { method: 'POST', body: JSON.stringify({ workspace_id: workspaceId, email, role }) }),
  updateProvisionedUser: (token: string, workspaceId: number, userId: number, payload: { role?: Exclude<WorkspaceRole, 'owner'>; active?: boolean }) => request<WorkspaceMember>(`/api/provisioning/workspaces/${workspaceId}/users/${userId}`, token, { method: 'PATCH', body: JSON.stringify(payload) }),
  listProvisioningEvents: (token: string, workspaceId: number) => request<{ items: ProvisioningEvent[] }>(`/api/provisioning/events?${new URLSearchParams({ workspace_id: String(workspaceId) })}`, token),
  retentionPreview: (token: string, payload: RetentionPolicy) => request<RetentionResult>('/api/governance/retention/preview', token, { method: 'POST', body: JSON.stringify(payload) }),
  retentionApply: (token: string, payload: RetentionPolicy) => request<RetentionResult>('/api/governance/retention/apply', token, { method: 'POST', body: JSON.stringify(payload) }),
  listLegalHolds: (token: string, workspaceId: number) => request<{ items: LegalHold[] }>(`/api/governance/legal-holds?${new URLSearchParams({ workspace_id: String(workspaceId) })}`, token),
  createLegalHold: (token: string, workspaceId: number, resourceType: RetentionResourceType, resourceId: string | null, reason: string) => request<LegalHold>('/api/governance/legal-holds', token, { method: 'POST', body: JSON.stringify({ workspace_id: workspaceId, resource_type: resourceType, resource_id: resourceId || null, reason }) }),
  releaseLegalHold: (token: string, workspaceId: number, holdId: number, reason: string) => request<LegalHold>(`/api/governance/legal-holds/${holdId}/release?${new URLSearchParams({ workspace_id: String(workspaceId) })}`, token, { method: 'POST', body: JSON.stringify({ reason }) }),
  complianceExport: (token: string, workspaceId: number) => request<ComplianceExport>(`/api/governance/compliance-export?${new URLSearchParams({ workspace_id: String(workspaceId) })}`, token),
  createAnalysis: (token: string, payload: AnalysisParams) => request<AnalysisTask>('/api/analyses', token, { method: 'POST', body: JSON.stringify(payload) }),
  listAnalyses: (token: string, params: Record<string, string> = {}) => request<{ items: AnalysisTask[] }>(`/api/analyses?${new URLSearchParams(params)}`, token),
  getAnalysis: (token: string, id: number) => request<AnalysisTask>(`/api/analyses/${id}`, token),
  rerun: (token: string, id: number, overrides: Partial<AnalysisParams>) => request<AnalysisTask>(`/api/analyses/${id}/rerun`, token, { method: 'POST', body: JSON.stringify(overrides) }),
  deleteAnalysis: (token: string, id: number) => request<void>(`/api/analyses/${id}`, token, { method: 'DELETE' }),
  exportAccount: (token: string) => request<AccountExport>('/api/account/export', token),
  listSchedules: (token: string, params: Record<string, string> = {}) => request<{ items: Schedule[] }>(`/api/schedules?${new URLSearchParams(params)}`, token),
  getSchedule: (token: string, id: number) => request<Schedule>(`/api/schedules/${id}`, token),
  createSchedule: (token: string, payload: SchedulePayload) => request<Schedule>('/api/schedules', token, { method: 'POST', body: JSON.stringify(payload) }),
  updateSchedule: (token: string, id: number, payload: Partial<SchedulePayload>) => request<Schedule>(`/api/schedules/${id}`, token, { method: 'PATCH', body: JSON.stringify(payload) }),
  pauseSchedule: (token: string, id: number) => request<Schedule>(`/api/schedules/${id}/pause`, token, { method: 'POST' }),
  resumeSchedule: (token: string, id: number) => request<Schedule>(`/api/schedules/${id}/resume`, token, { method: 'POST' }),
  deleteSchedule: (token: string, id: number) => request<void>(`/api/schedules/${id}`, token, { method: 'DELETE' }),
  triggerSchedule: (token: string, id: number) => request<ScheduleExecution>(`/api/schedules/${id}/trigger`, token, { method: 'POST' }),
  listMemories: (token: string, params: Record<string, string> = {}) => request<{ items: AgentMemory[] }>(`/api/memories?${new URLSearchParams(params)}`, token),
  getMemory: (token: string, id: number) => request<AgentMemory>(`/api/memories/${id}`, token),
  archiveMemory: (token: string, id: number) => request<AgentMemory>(`/api/memories/${id}/archive`, token, { method: 'POST' }),
  unarchiveMemory: (token: string, id: number) => request<AgentMemory>(`/api/memories/${id}/unarchive`, token, { method: 'POST' }),
  listInterventions: (token: string, params: Record<string, string> = {}) => request<{ items: InterventionSession[] }>(`/api/interventions?${new URLSearchParams(params)}`, token),
  getIntervention: (token: string, id: number) => request<InterventionSession>(`/api/interventions/${id}`, token),
  createIntervention: (token: string, sourceTaskId: number, targetAgentName: string) => request<InterventionSession>('/api/interventions', token, { method: 'POST', body: JSON.stringify({ source_analysis_task_id: sourceTaskId, target_agent_name: targetAgentName }) }),
  appendInterventionMessage: (token: string, id: number, content: string) => request<InterventionMessage>(`/api/interventions/${id}/messages`, token, { method: 'POST', body: JSON.stringify({ content }) }),
  pauseIntervention: (token: string, id: number) => request<InterventionSession>(`/api/interventions/${id}/pause`, token, { method: 'POST' }),
  resumeIntervention: (token: string, id: number) => request<InterventionSession>(`/api/interventions/${id}/resume`, token, { method: 'POST' }),
  closeIntervention: (token: string, id: number) => request<InterventionSession>(`/api/interventions/${id}/close`, token, { method: 'POST' }),
  runIntervention: (token: string, id: number) => request<InterventionOutput>(`/api/interventions/${id}/run`, token, { method: 'POST' }),
  deleteIntervention: (token: string, id: number) => request<void>(`/api/interventions/${id}`, token, { method: 'DELETE' }),
  streamUrl: (id: number) => `${API_BASE}/api/analyses/${id}/events`
};

export async function streamTaskEvents(token: string, taskId: number, onEvent: (event: AgentEvent) => void): Promise<void> {
  const response = await fetch(api.streamUrl(taskId), { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok || !response.body) throw new Error(await response.text());
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() ?? '';
    for (const chunk of chunks) {
      if (chunk.includes('event: end')) return;
      const dataLine = chunk.split('\n').find(line => line.startsWith('data: '));
      if (dataLine) onEvent(JSON.parse(dataLine.slice(6)) as AgentEvent);
    }
  }
}
