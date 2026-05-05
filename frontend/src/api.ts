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

export type AnalysisTask = { id: number; status: string; ticker?: string; analysis_date?: string; decision?: string | null; parameters?: AnalysisParams; final_decision?: { decision: string; rationale: string } | null; report_sections?: { section_name: string; content: string }[]; events?: AgentEvent[] };
export type AgentEvent = { sequence: number; agent: string; event_type: string; message: string; created_at: string };

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
