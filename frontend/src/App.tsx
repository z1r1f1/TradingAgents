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
  streamTaskEvents
} from './api';
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
  output_language: 'English',
  memory_ids: []
};

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

function App() {
  const [token, setToken] = useState(localStorage.getItem('ta_token'));
  const [email, setEmail] = useState('demo@example.com');
  const [password, setPassword] = useState('demo-password');
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
  const [scheduleForm, setScheduleForm] = useState(defaultScheduleForm);
  const [editingScheduleId, setEditingScheduleId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const authenticated = Boolean(token);
  const analystsLabel = useMemo(() => params.analysts.join(', '), [params.analysts]);
  const scheduleAnalystsLabel = useMemo(() => scheduleForm.params.analysts.join(', '), [scheduleForm.params.analysts]);

  useEffect(() => {
    if (token) {
      void refreshHistory(token);
      void refreshSchedules(token);
      void refreshMemories(token);
      void refreshInterventions(token);
    }
  }, [token]);

  async function refreshHistory(auth = token) {
    if (!auth) return;
    const data = await api.listAnalyses(auth);
    setHistory(data.items);
  }

  async function refreshSchedules(auth = token) {
    if (!auth) return;
    const data = await api.listSchedules(auth);
    setSchedules(data.items);
  }

  async function refreshMemories(auth = token, query = memoryQuery) {
    if (!auth) return;
    const data = await api.listMemories(auth, { ...(query ? { query } : {}), archived: 'false' });
    setMemories(data.items);
  }

  async function refreshInterventions(auth = token) {
    if (!auth) return;
    const data = await api.listInterventions(auth);
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

  async function launch() {
    if (!token) return;
    setError(null);
    try {
      const task = await api.createAnalysis(token, params);
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
    const payload = buildSchedulePayload(scheduleForm);
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
  }

  if (!authenticated) {
    return <main className="mx-auto flex min-h-screen max-w-md items-center"><Card><CardTitle>TradingAgents Login</CardTitle><form className="space-y-3" onSubmit={handleLogin}><input className="w-full rounded bg-slate-800 p-2" value={email} onChange={e => setEmail(e.target.value)} /><input className="w-full rounded bg-slate-800 p-2" type="password" value={password} onChange={e => setPassword(e.target.value)} /><Button className="w-full">Log in / Register</Button>{error && <p className="text-sm text-red-300">{error}</p>}</form></Card></main>;
  }

  return <main className="mx-auto max-w-7xl space-y-5 p-6"><header className="flex items-center justify-between"><h1 className="text-3xl font-bold">TradingAgents Web Platform</h1><Button onClick={logout} className="bg-slate-200"><LogOut className="mr-2 inline" size={16}/>Logout</Button></header>{error && <p className="rounded bg-red-950 p-3 text-red-200">{error}</p>}<div className="grid gap-5 lg:grid-cols-[380px_1fr]"><Card><CardTitle><PlayCircle className="mr-2 inline"/>Configure analysis</CardTitle><div className="space-y-3"><input className="w-full rounded bg-slate-800 p-2" value={params.ticker} onChange={e => setParams({...params, ticker: e.target.value.toUpperCase()})} /><input className="w-full rounded bg-slate-800 p-2" type="date" value={params.analysis_date} onChange={e => setParams({...params, analysis_date: e.target.value})} /><input className="w-full rounded bg-slate-800 p-2" value={analystsLabel} onChange={e => setParams({...params, analysts: parseAnalystsInput(e.target.value)})} /><input className="w-full rounded bg-slate-800 p-2" type="number" min="1" max="10" value={params.research_depth} onChange={e => setParams({...params, research_depth: Number(e.target.value)})} /><input className="w-full rounded bg-slate-800 p-2" value={params.llm_provider} onChange={e => setParams({...params, llm_provider: e.target.value})} /><input className="w-full rounded bg-slate-800 p-2" value={params.quick_model} onChange={e => setParams({...params, quick_model: e.target.value})} /><input className="w-full rounded bg-slate-800 p-2" value={params.deep_model} onChange={e => setParams({...params, deep_model: e.target.value})} /><input className="w-full rounded bg-slate-800 p-2" value={params.output_language} onChange={e => setParams({...params, output_language: e.target.value})} /><div className="rounded border border-slate-700 p-2 text-sm"><p className="mb-2 text-slate-300">Attach memories</p>{memories.slice(0, 6).map(memory => <label key={memory.id} className="block"><input type="checkbox" checked={(params.memory_ids ?? []).includes(memory.id)} onChange={() => setParams({...params, memory_ids: toggleMemoryId(params.memory_ids, memory.id)})} /> {buildMemoryOptionLabel(memory)}</label>)}</div><Button onClick={launch}>Launch analysis</Button></div></Card><Card><CardTitle><Activity className="mr-2 inline"/>Realtime progress and result</CardTitle>{selected ? <div className="space-y-4"><p className="text-sm text-slate-300">Task #{selected.id} · {selected.status} · {selected.parameters?.ticker}</p><div className="max-h-72 overflow-auto rounded bg-slate-950 p-3 text-sm">{events.map(event => <p key={event.sequence}><span className="text-emerald-300">#{event.sequence} {event.agent}</span> {event.event_type}: {event.message}</p>)}</div><h3 className="font-semibold">Decision: {selected.final_decision?.decision ?? 'pending'}</h3><p className="text-slate-300">{selected.final_decision?.rationale}</p>{selected.attached_memories?.length ? <div className="rounded border border-slate-700 p-3"><h4 className="font-semibold">Attached memories</h4>{selected.attached_memories.map(memory => <p key={memory.id} className="text-sm text-slate-300">{buildMemoryOptionLabel(memory)}</p>)}</div> : null}<div className="rounded border border-slate-700 p-3"><h4 className="font-semibold">Human intervention</h4><div className="flex flex-wrap gap-2"><select className="rounded bg-slate-800 p-2" value={interventionAgent} onChange={e => setInterventionAgent(e.target.value)}><option>Market Analyst</option><option>News Analyst</option><option>Research Manager</option><option>Trader</option><option>Portfolio Manager</option></select><Button onClick={createIntervention}>Start session</Button></div>{selected.intervention_sessions?.map(session => <button key={session.id} className="mt-2 block text-left text-sm text-emerald-300" onClick={() => loadIntervention(session.id)}>{buildInterventionLabel(session)}</button>)}</div>{selected.report_sections?.map(section => <article key={section.section_name} className="rounded border border-slate-700 p-3"><h4 className="font-semibold">{section.section_name}</h4><p className="whitespace-pre-wrap text-sm text-slate-300">{section.content}</p></article>)}<div className="flex flex-wrap gap-2"><Button onClick={() => selected && setParams(buildEditableParamsFromTask(selected))}>Load parameters into form</Button><Button onClick={() => rerunSelected({})}><RotateCcw className="mr-2 inline" size={16}/>Rerun with same parameters</Button></div></div> : <p className="text-slate-400">Launch or select a historical analysis.</p>}</Card></div><Card><CardTitle><CalendarClock className="mr-2 inline"/>Scheduled analysis</CardTitle><div className="grid gap-4 lg:grid-cols-[360px_1fr]"><div className="space-y-3"><input className="w-full rounded bg-slate-800 p-2" value={scheduleForm.name} onChange={e => setScheduleForm({...scheduleForm, name: e.target.value})} /><input className="w-full rounded bg-slate-800 p-2" type="datetime-local" value={scheduleForm.start_at} onChange={e => setScheduleForm({...scheduleForm, start_at: e.target.value})} /><select className="w-full rounded bg-slate-800 p-2" value={scheduleForm.interval} onChange={e => setScheduleForm({...scheduleForm, interval: e.target.value as ScheduleInterval})}><option value="daily">daily</option><option value="weekly">weekly</option><option value="monthly">monthly</option></select><input className="w-full rounded bg-slate-800 p-2" value={scheduleForm.params.ticker} onChange={e => setScheduleForm({...scheduleForm, params: {...scheduleForm.params, ticker: e.target.value.toUpperCase()}})} /><input className="w-full rounded bg-slate-800 p-2" value={scheduleAnalystsLabel} onChange={e => setScheduleForm({...scheduleForm, params: {...scheduleForm.params, analysts: parseAnalystsInput(e.target.value)}})} /><input className="w-full rounded bg-slate-800 p-2" type="number" min="1" max="10" value={scheduleForm.params.research_depth} onChange={e => setScheduleForm({...scheduleForm, params: {...scheduleForm.params, research_depth: Number(e.target.value)}})} /><div className="rounded border border-slate-700 p-2 text-sm"><p className="mb-2 text-slate-300">Schedule memories</p>{memories.slice(0, 6).map(memory => <label key={memory.id} className="block"><input type="checkbox" checked={(scheduleForm.params.memory_ids ?? []).includes(memory.id)} onChange={() => setScheduleForm({...scheduleForm, params: {...scheduleForm.params, memory_ids: toggleMemoryId(scheduleForm.params.memory_ids, memory.id)}})} /> {buildMemoryOptionLabel(memory)}</label>)}</div><Button onClick={saveSchedule}>{editingScheduleId ? 'Save schedule' : 'Create schedule'}</Button></div><div className="space-y-2">{schedules.map(schedule => <article key={schedule.id} className="rounded border border-slate-700 p-3"><div className="flex items-start justify-between gap-2"><div><h3 className="font-semibold">{schedule.name}</h3><p className="text-sm text-slate-400">{schedule.ticker} · {schedule.interval} · {schedule.status} · next {schedule.next_run_at}</p><p className="text-xs text-slate-500">Recent: {schedule.executions?.[0]?.status ?? 'no executions yet'}</p></div><div className="flex flex-wrap justify-end gap-2"><Button onClick={() => editSchedule(schedule)}>Edit</Button><Button onClick={() => triggerSchedule(schedule)}>Trigger</Button><Button onClick={() => toggleSchedule(schedule)}>{schedule.status === 'active' ? 'Pause' : 'Resume'}</Button><Button className="bg-red-300" onClick={() => removeSchedule(schedule)}>Delete</Button></div></div></article>)}</div></div></Card><Card><CardTitle>Intervention session</CardTitle>{selectedIntervention ? <div className="space-y-3"><p className="text-sm text-slate-300">{buildInterventionLabel(selectedIntervention)}</p><textarea className="w-full rounded bg-slate-800 p-2" value={guidance} onChange={e => setGuidance(e.target.value)} placeholder="Add explicit guidance" /><div className="flex flex-wrap gap-2"><Button onClick={addGuidance}>Add guidance</Button><Button onClick={() => setInterventionStatus('pause')}>Pause</Button><Button onClick={() => setInterventionStatus('resume')}>Resume</Button><Button onClick={runContinuation}>Run continuation</Button><Button onClick={() => setInterventionStatus('close')}>Close</Button></div><div className="rounded bg-slate-950 p-3 text-sm">{selectedIntervention.messages?.map(message => <p key={message.id}><span className="text-emerald-300">{message.author}</span>: {message.content}</p>)}{selectedIntervention.events?.map(event => <p key={`e-${event.id}`}><span className="text-blue-300">{event.event_type}</span>: {event.message}</p>)}{selectedIntervention.outputs?.map(output => <p key={`o-${output.id}`} className="whitespace-pre-wrap text-slate-300">{output.content}</p>)}</div></div> : <p className="text-slate-400">Select or start an intervention session from an analysis.</p>}<div className="mt-3 grid gap-2 md:grid-cols-2 lg:grid-cols-3">{interventions.map(session => <button key={session.id} className="rounded border border-slate-700 p-2 text-left text-sm" onClick={() => loadIntervention(session.id)}>{buildInterventionLabel(session)}</button>)}</div></Card><Card><CardTitle>Agent memories</CardTitle><div className="mb-3 flex gap-2"><input className="w-full rounded bg-slate-800 p-2" placeholder="Search memories" value={memoryQuery} onChange={e => setMemoryQuery(e.target.value)} /><Button onClick={() => refreshMemories()}>Search</Button></div><div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">{memories.map(memory => <article key={memory.id} className="rounded border border-slate-700 p-3"><button className="text-left font-semibold" onClick={() => setSelectedMemory(memory)}>{buildMemoryOptionLabel(memory)}</button><p className="line-clamp-2 text-sm text-slate-400">{memory.title}</p><Button onClick={() => { if (token) void api.archiveMemory(token, memory.id).then(() => refreshMemories()); }}>Archive</Button></article>)}</div>{selectedMemory ? <div className="mt-3 rounded bg-slate-950 p-3"><h3 className="font-semibold">{selectedMemory.title}</h3><p className="whitespace-pre-wrap text-sm text-slate-300">{selectedMemory.content}</p></div> : null}</Card><Card><CardTitle><History className="mr-2 inline"/>History</CardTitle><div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">{history.map(item => <button key={item.id} onClick={() => loadTask(item.id)} className="rounded border border-slate-700 p-3 text-left hover:bg-slate-800"><strong>#{item.id} {item.ticker}</strong><p className="text-sm text-slate-400">{item.analysis_date} · {item.status} · {item.decision ?? 'no decision'}</p><span className="mt-2 inline-block rounded bg-slate-700 px-2 py-1 text-xs" onClick={event => { event.stopPropagation(); void loadTaskParameters(item.id); }}>Load/edit parameters</span></button>)}</div></Card></main>;
}

export default App;
