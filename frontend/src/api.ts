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
  login: (email: string, password: string) => request<{ access_token: string; user: { email: string } }>('/api/auth/login', null, { method: 'POST', body: JSON.stringify({ email, password }) }),
  register: (email: string, password: string) => request('/api/auth/register', null, { method: 'POST', body: JSON.stringify({ email, password }) }),
  logout: (token: string) => request('/api/auth/logout', token, { method: 'POST' }),
  listWorkspaces: (token: string) => request<{ items: Workspace[] }>('/api/workspaces', token),
  createWorkspace: (token: string, name: string) => request<Workspace>('/api/workspaces', token, { method: 'POST', body: JSON.stringify({ name }) }),
  getWorkspace: (token: string, id: number) => request<Workspace>(`/api/workspaces/${id}`, token),
  addWorkspaceMember: (token: string, id: number, email: string, role: WorkspaceRole) => request<WorkspaceMember>(`/api/workspaces/${id}/members`, token, { method: 'POST', body: JSON.stringify({ email, role }) }),
  updateWorkspaceMember: (token: string, id: number, userId: number, role: WorkspaceRole) => request<WorkspaceMember>(`/api/workspaces/${id}/members/${userId}`, token, { method: 'PATCH', body: JSON.stringify({ role }) }),
  removeWorkspaceMember: (token: string, id: number, userId: number) => request<void>(`/api/workspaces/${id}/members/${userId}`, token, { method: 'DELETE' }),
  listGovernanceAudit: (token: string, params: Record<string, string> = {}) => request<{ items: unknown[] }>(`/api/governance/audit?${new URLSearchParams(params)}`, token),
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
