export type AnalysisParams = {
  ticker: string;
  analysis_date: string;
  analysts: string[];
  research_depth: number;
  llm_provider: string;
  backend_url?: string | null;
  quick_model: string;
  deep_model: string;
  output_language: string;
};

export type AnalysisTask = {
  id: number;
  status: string;
  ticker?: string;
  analysis_date?: string;
  decision?: string | null;
  parameters?: AnalysisParams;
  final_decision?: { decision: string; rationale: string } | null;
  report_sections?: { section_name: string; content: string }[];
  events?: AgentEvent[];
};

export type AgentEvent = { sequence: number; agent: string; event_type: string; message: string; created_at: string };
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
  createAnalysis: (token: string, payload: AnalysisParams) => request<AnalysisTask>('/api/analyses', token, { method: 'POST', body: JSON.stringify(payload) }),
  listAnalyses: (token: string) => request<{ items: AnalysisTask[] }>('/api/analyses', token),
  getAnalysis: (token: string, id: number) => request<AnalysisTask>(`/api/analyses/${id}`, token),
  rerun: (token: string, id: number, overrides: Partial<AnalysisParams>) => request<AnalysisTask>(`/api/analyses/${id}/rerun`, token, { method: 'POST', body: JSON.stringify(overrides) }),
  listSchedules: (token: string) => request<{ items: Schedule[] }>('/api/schedules', token),
  getSchedule: (token: string, id: number) => request<Schedule>(`/api/schedules/${id}`, token),
  createSchedule: (token: string, payload: SchedulePayload) => request<Schedule>('/api/schedules', token, { method: 'POST', body: JSON.stringify(payload) }),
  updateSchedule: (token: string, id: number, payload: Partial<SchedulePayload>) => request<Schedule>(`/api/schedules/${id}`, token, { method: 'PATCH', body: JSON.stringify(payload) }),
  pauseSchedule: (token: string, id: number) => request<Schedule>(`/api/schedules/${id}/pause`, token, { method: 'POST' }),
  resumeSchedule: (token: string, id: number) => request<Schedule>(`/api/schedules/${id}/resume`, token, { method: 'POST' }),
  deleteSchedule: (token: string, id: number) => request<void>(`/api/schedules/${id}`, token, { method: 'DELETE' }),
  triggerSchedule: (token: string, id: number) => request<ScheduleExecution>(`/api/schedules/${id}/trigger`, token, { method: 'POST' }),
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
