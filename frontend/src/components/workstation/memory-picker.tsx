import type { AgentMemory } from '../../api';

const agentLabels: Record<string, string> = {
  'Market Analyst': '市场分析师',
  'Social Analyst': '社媒分析师',
  'News Analyst': '新闻分析师',
  'Fundamentals Analyst': '基本面分析师',
  'Research Manager': '研究经理',
  Trader: '交易员',
  'Portfolio Manager': '组合经理',
  'Bull Researcher': '多方研究员',
  'Bear Researcher': '空方研究员',
  'Aggressive Risk Analyst': '激进风控分析师',
  'Conservative Risk Analyst': '保守风控分析师',
  'Neutral Risk Analyst': '中性风控分析师'
};

function formatAgentName(agentName: string): string {
  return agentLabels[agentName] ?? agentName;
}

function buildMemoryOptionLabel(memory: AgentMemory): string {
  return [formatAgentName(memory.agent_name), memory.ticker, memory.analysis_date].filter(Boolean).join(' · ');
}

export function MemoryPicker({ title, memories, selectedIds, onToggle }: { title: string; memories: AgentMemory[]; selectedIds: number[]; onToggle: (memoryId: number) => void }) {
  return <div className="rounded-2xl border border-slate-200 bg-slate-50/90 p-3 text-sm"><p className="mb-2 font-medium text-slate-800">{title}</p>{memories.length ? memories.map(memory => <label key={memory.id} className="flex items-center gap-2 py-1 text-slate-600"><input type="checkbox" checked={selectedIds.includes(memory.id)} onChange={() => onToggle(memory.id)} /> <span>{buildMemoryOptionLabel(memory)}</span></label>) : <p className="text-xs text-slate-400">暂无可选记忆</p>}</div>;
}
