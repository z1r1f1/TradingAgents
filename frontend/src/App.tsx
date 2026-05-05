import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Activity, History, LogOut, PlayCircle, RotateCcw } from 'lucide-react';
import { api, AgentEvent, AnalysisParams, AnalysisTask, streamTaskEvents } from './api';
import { Button } from './components/ui/button';
import { Card, CardTitle } from './components/ui/card';

export const defaultParams: AnalysisParams = {
  ticker: 'SPY',
  analysis_date: new Date().toISOString().slice(0, 10),
  analysts: ['market', 'news'],
  research_depth: 1,
  llm_provider: 'openai',
  quick_model: 'gpt-5.4-mini',
  deep_model: 'gpt-5.5',
  output_language: 'English'
};

export function parseAnalystsInput(value: string): string[] {
  return value
    .split(',')
    .map(item => item.trim().toLowerCase())
    .filter((item, index, items) => Boolean(item) && items.indexOf(item) === index);
}

export function buildEditableParamsFromTask(task: AnalysisTask): AnalysisParams {
  if (!task.parameters) {
    return defaultParams;
  }
  return { ...defaultParams, ...task.parameters, analysts: [...task.parameters.analysts] };
}

function App() {
  const [token, setToken] = useState(localStorage.getItem('ta_token'));
  const [email, setEmail] = useState('demo@example.com');
  const [password, setPassword] = useState('demo-password');
  const [params, setParams] = useState(defaultParams);
  const [history, setHistory] = useState<AnalysisTask[]>([]);
  const [selected, setSelected] = useState<AnalysisTask | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const authenticated = Boolean(token);
  const analystsLabel = useMemo(() => params.analysts.join(', '), [params.analysts]);

  useEffect(() => { if (token) void refreshHistory(token); }, [token]);

  async function refreshHistory(auth = token) {
    if (!auth) return;
    const data = await api.listAnalyses(auth);
    setHistory(data.items);
  }

  async function handleLogin(e: FormEvent) {
    e.preventDefault(); setError(null);
    try { await api.register(email, password).catch(() => undefined); const result = await api.login(email, password); localStorage.setItem('ta_token', result.access_token); setToken(result.access_token); }
    catch (err) { setError(String(err)); }
  }

  async function launch() {
    if (!token) return;
    setError(null);
    try {
      const task = await api.createAnalysis(token, params);
      setSelected(task);
      setEvents([]);
      await streamTaskEvents(token, task.id, event => setEvents(current => [...current.filter(item => item.sequence !== event.sequence), event].sort((a, b) => a.sequence - b.sequence)));
      const detail = await api.getAnalysis(token, task.id);
      setSelected(detail); setEvents(detail.events ?? []); await refreshHistory(token);
    } catch (err) { setError(String(err)); }
  }

  async function loadTask(id: number) {
    if (!token) return;
    const detail = await api.getAnalysis(token, id);
    setSelected(detail); setEvents(detail.events ?? []);
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
    await loadTask(task.id); await refreshHistory(token);
  }

  function logout() { if (token) void api.logout(token).catch(() => undefined); localStorage.removeItem('ta_token'); setToken(null); setSelected(null); setHistory([]); }

  if (!authenticated) return <main className="mx-auto flex min-h-screen max-w-md items-center"><Card><CardTitle>TradingAgents Login</CardTitle><form className="space-y-3" onSubmit={handleLogin}><input className="w-full rounded bg-slate-800 p-2" value={email} onChange={e => setEmail(e.target.value)} /><input className="w-full rounded bg-slate-800 p-2" type="password" value={password} onChange={e => setPassword(e.target.value)} /><Button className="w-full">Log in / Register</Button>{error && <p className="text-sm text-red-300">{error}</p>}</form></Card></main>;

  return <main className="mx-auto max-w-7xl space-y-5 p-6"><header className="flex items-center justify-between"><h1 className="text-3xl font-bold">TradingAgents Web Platform</h1><Button onClick={logout} className="bg-slate-200"><LogOut className="mr-2 inline" size={16}/>Logout</Button></header>{error && <p className="rounded bg-red-950 p-3 text-red-200">{error}</p>}<div className="grid gap-5 lg:grid-cols-[380px_1fr]"><Card><CardTitle><PlayCircle className="mr-2 inline"/>Configure analysis</CardTitle><div className="space-y-3"><input className="w-full rounded bg-slate-800 p-2" value={params.ticker} onChange={e => setParams({...params, ticker: e.target.value.toUpperCase()})} /><input className="w-full rounded bg-slate-800 p-2" type="date" value={params.analysis_date} onChange={e => setParams({...params, analysis_date: e.target.value})} /><input className="w-full rounded bg-slate-800 p-2" value={analystsLabel} onChange={e => setParams({...params, analysts: parseAnalystsInput(e.target.value)})} /><input className="w-full rounded bg-slate-800 p-2" type="number" min="1" max="10" value={params.research_depth} onChange={e => setParams({...params, research_depth: Number(e.target.value)})} /><input className="w-full rounded bg-slate-800 p-2" value={params.llm_provider} onChange={e => setParams({...params, llm_provider: e.target.value})} /><input className="w-full rounded bg-slate-800 p-2" value={params.quick_model} onChange={e => setParams({...params, quick_model: e.target.value})} /><input className="w-full rounded bg-slate-800 p-2" value={params.deep_model} onChange={e => setParams({...params, deep_model: e.target.value})} /><input className="w-full rounded bg-slate-800 p-2" value={params.output_language} onChange={e => setParams({...params, output_language: e.target.value})} /><Button onClick={launch}>Launch analysis</Button></div></Card><Card><CardTitle><Activity className="mr-2 inline"/>Realtime progress and result</CardTitle>{selected ? <div className="space-y-4"><p className="text-sm text-slate-300">Task #{selected.id} · {selected.status} · {selected.parameters?.ticker}</p><div className="max-h-72 overflow-auto rounded bg-slate-950 p-3 text-sm">{events.map(event => <p key={event.sequence}><span className="text-emerald-300">#{event.sequence} {event.agent}</span> {event.event_type}: {event.message}</p>)}</div><h3 className="font-semibold">Decision: {selected.final_decision?.decision ?? 'pending'}</h3><p className="text-slate-300">{selected.final_decision?.rationale}</p>{selected.report_sections?.map(section => <article key={section.section_name} className="rounded border border-slate-700 p-3"><h4 className="font-semibold">{section.section_name}</h4><p className="whitespace-pre-wrap text-sm text-slate-300">{section.content}</p></article>)}<div className="flex flex-wrap gap-2"><Button onClick={() => selected && setParams(buildEditableParamsFromTask(selected))}>Load parameters into form</Button><Button onClick={() => rerunSelected({})}><RotateCcw className="mr-2 inline" size={16}/>Rerun with same parameters</Button></div></div> : <p className="text-slate-400">Launch or select a historical analysis.</p>}</Card></div><Card><CardTitle><History className="mr-2 inline"/>History</CardTitle><div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">{history.map(item => <button key={item.id} onClick={() => loadTask(item.id)} className="rounded border border-slate-700 p-3 text-left hover:bg-slate-800"><strong>#{item.id} {item.ticker}</strong><p className="text-sm text-slate-400">{item.analysis_date} · {item.status} · {item.decision ?? 'no decision'}</p><span className="mt-2 inline-block rounded bg-slate-700 px-2 py-1 text-xs" onClick={event => { event.stopPropagation(); void loadTaskParameters(item.id); }}>Load/edit parameters</span></button>)}</div></Card></main>;
}

export default App;
