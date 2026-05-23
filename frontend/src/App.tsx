import { FormEvent, type ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, Brain, CalendarClock, Database, History, LogOut, Moon, PlayCircle, RotateCcw, Search, ShieldCheck, Sun, Users } from 'lucide-react';
import {
  api,
  AUTH_EXPIRED_EVENT,
  AgentEvent,
  AnalysisParams,
  AnalysisTask,
  InterventionSession,
  AgentMemory,
  Schedule,
  ScheduleInterval,
  SchedulePayload,
  StockSearchSuggestion,
  Workspace,
  WorkspaceRole,
  RuntimeHealth,
  GovernanceAuditEvent,
  IdentityStatus,
  IdentityUser,
  IdpHealth,
  LegalHold,
  ProvisioningEvent,
  RetentionResourceType,
  RetentionResult,
  streamTaskEvents
} from './api';
import { Button } from './components/ui/button';
import { Card, CardTitle } from './components/ui/card';
import { OperatorUsageReport } from './operatorReport';

export type WorkspacePageId = 'analysis' | 'history' | 'memories' | 'schedules' | 'interventions' | 'governance' | 'compliance';

export type WorkspacePageMeta = {
  id: WorkspacePageId;
  title: string;
  description: string;
  badge: string;
};

export const workspacePages: WorkspacePageMeta[] = [
  { id: 'analysis', title: '股票分析', description: '发起研究并查看实时 Agent 输出', badge: '实时' },
  { id: 'history', title: '分析历史', description: '查看、复用、删除历史分析', badge: '复盘' },
  { id: 'memories', title: '智能体记忆', description: '搜索和管理 Agent 历史知识', badge: '知识' },
  { id: 'schedules', title: '定时任务', description: '维护周期性自动分析计划', badge: '自动' },
  { id: 'interventions', title: '人工介入', description: '与单个 Agent 延续对话分析', badge: 'HITL' },
  { id: 'governance', title: '工作区治理', description: '管理工作区、成员和用户预配', badge: '权限' },
  { id: 'compliance', title: '合规与身份', description: '审计、保留、SSO 与法律保全', badge: '安全' }
];

export function getWorkspacePageMeta(pageId: WorkspacePageId): WorkspacePageMeta | undefined {
  return workspacePages.find(page => page.id === pageId);
}

export type ThinkingDepth = 'default' | 'low' | 'medium' | 'high' | 'xhigh';

export const thinkingDepthOptions: { value: ThinkingDepth; label: string; hint: string }[] = [
  { value: 'default', label: '默认', hint: '使用模型或后端默认推理设置' },
  { value: 'low', label: '低', hint: '更快响应，适合快速验证' },
  { value: 'medium', label: '中', hint: '平衡速度和推理质量' },
  { value: 'high', label: '高', hint: '更充分推理，适合重要分析' },
  { value: 'xhigh', label: '极高', hint: '使用渠道支持的 xhigh 推理强度，适合深度研究' }
];

export const analystOptions: { value: string; label: string; description: string }[] = [
  { value: 'market', label: '市场分析师', description: '行情、技术指标与价格结构' },
  { value: 'social', label: '社媒分析师', description: '社媒情绪与市场关注度' },
  { value: 'news', label: '新闻分析师', description: '新闻事件与宏观催化' },
  { value: 'fundamentals', label: '基本面分析师', description: '财务、估值与业务质量' }
];

export const defaultAnalysts = analystOptions.map(option => option.value);

export const defaultParams: AnalysisParams = {
  ticker: 'SPY',
  analysis_date: new Date().toISOString().slice(0, 10),
  analysts: [...defaultAnalysts],
  research_depth: 5,
  llm_provider: 'openai',
  quick_model: 'gpt-5.5',
  deep_model: 'gpt-5.5',
  output_language: '中文',
  google_thinking_level: 'xhigh',
  openai_reasoning_effort: 'xhigh',
  anthropic_effort: 'xhigh',
  memory_ids: []
};

export type ThemeMode = 'light' | 'dark';

const THEME_STORAGE_KEY = 'ta_theme_mode';

export function resolveThemeMode(stored: string | null | undefined, prefersDark: boolean): ThemeMode {
  if (stored === 'light' || stored === 'dark') return stored;
  return prefersDark ? 'dark' : 'light';
}

function getInitialThemeMode(): ThemeMode {
  if (typeof window === 'undefined') return 'light';
  return resolveThemeMode(
    localStorage.getItem(THEME_STORAGE_KEY),
    window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
  );
}

export function ThemeToggle({ themeMode, onToggle }: { themeMode: ThemeMode; onToggle: () => void }) {
  const dark = themeMode === 'dark';
  return (
    <button
      type="button"
      aria-pressed={dark}
      aria-label={dark ? '切换到亮色主题' : '切换到深色主题'}
      onClick={onToggle}
      className="inline-flex items-center gap-2 whitespace-nowrap rounded-full border border-subtle bg-surface/95 px-3 py-2 text-xs font-semibold text-primary shadow-panel transition hover:-translate-y-0.5 hover:border-accent hover:shadow-glow"
    >
      {dark ? <Moon size={15} className="text-accent" /> : <Sun size={15} className="text-accent" />}
      <span>当前：{dark ? '深色主题' : '亮色主题'}</span>
      <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] text-accent">
        {dark ? '切换到亮色主题' : '切换到深色主题'}
      </span>
    </button>
  );
}

const isProductionWeb = import.meta.env.VITE_TRADINGAGENTS_WEB_ENV === 'production';
const initialEmail = isProductionWeb ? '' : 'demo@example.com';
const initialPassword = isProductionWeb ? '' : 'demo-password';

export function shouldShowProductionSafetyWarning(webEnv: string | undefined, apiBase: string | undefined): boolean {
  return webEnv !== 'production' || !apiBase || apiBase.includes('localhost') || apiBase.includes('127.0.0.1');
}

export function accountExportFilename(exportedAt: string): string {
  return `tradingagents-export-${exportedAt.slice(0, 10)}.json`;
}

export function complianceExportFilename(workspaceId: number, exportedAt: string): string {
  return `tradingagents-compliance-workspace-${workspaceId}-${exportedAt.slice(0, 10)}.json`;
}

export type ScheduleForm = {
  name: string;
  start_at: string;
  interval: ScheduleInterval;
  params: AnalysisParams;
};

export const defaultScheduleForm: ScheduleForm = {
  name: '每日 SPY',
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

export function formatSelectedAnalysts(selected: string[]): string {
  const normalized = analystOptions.filter(option => selected.includes(option.value));
  if (normalized.length === analystOptions.length) return `全选（${analystOptions.length} 个 Agent）`;
  if (!normalized.length) return '请选择至少 1 个 Agent';
  return normalized.map(option => option.label).join('、');
}

export function toggleAnalystSelection(selected: string[], analyst: string): string[] {
  if (!analystOptions.some(option => option.value === analyst)) return selected;
  if (selected.includes(analyst)) {
    return selected.length === 1 ? selected : selected.filter(item => item !== analyst);
  }
  return analystOptions.filter(option => selected.includes(option.value) || option.value === analyst).map(option => option.value);
}

export function buildEditableParamsFromTask(task: AnalysisTask): AnalysisParams {
  if (!task.parameters) return defaultParams;
  return { ...defaultParams, ...task.parameters, analysts: [...task.parameters.analysts] };
}

export function buildReusableAnalysisParamsFromTask(task: AnalysisTask): {
  params: AnalysisParams;
  tickerInputValue: string;
  selected: AnalysisTask | null;
  events: AgentEvent[];
} {
  const params = buildEditableParamsFromTask(task);
  return {
    params,
    tickerInputValue: params.ticker || task.ticker || defaultParams.ticker,
    selected: null,
    events: []
  };
}

export function applyThinkingDepth(params: AnalysisParams, depth: ThinkingDepth): AnalysisParams {
  const providerDepth = depth === 'default' ? null : depth;
  return {
    ...params,
    google_thinking_level: providerDepth,
    openai_reasoning_effort: providerDepth,
    anthropic_effort: providerDepth
  };
}

export function getThinkingDepth(params: Partial<AnalysisParams> | undefined | null): ThinkingDepth {
  const value = params?.openai_reasoning_effort ?? params?.google_thinking_level ?? params?.anthropic_effort ?? null;
  return value === 'low' || value === 'medium' || value === 'high' || value === 'xhigh' ? value : 'default';
}

export function getThinkingDepthLabel(params: Partial<AnalysisParams> | undefined | null): string {
  const depth = getThinkingDepth(params);
  return thinkingDepthOptions.find(option => option.value === depth)?.label ?? '默认';
}

export function filterAnalysisHistory(
  items: AnalysisTask[],
  filters: { ticker?: string; analysisDate?: string }
): AnalysisTask[] {
  const ticker = filters.ticker?.trim().toUpperCase();
  const analysisDate = filters.analysisDate?.trim();
  return items.filter(item => {
    const itemTicker = (item.ticker ?? item.parameters?.ticker ?? '').toUpperCase();
    const itemTickerName = (item.ticker_name ?? item.parameters?.ticker_name ?? '').toUpperCase();
    const itemDate = item.analysis_date ?? item.parameters?.analysis_date ?? '';
    return (!ticker || itemTicker.includes(ticker) || itemTickerName.includes(ticker)) && (!analysisDate || itemDate === analysisDate);
  });
}

export function buildAnalysisTickerLabel(task: AnalysisTask): string {
  const ticker = (task.ticker ?? task.parameters?.ticker ?? '').trim();
  const name = (task.ticker_name ?? task.parameters?.ticker_name ?? '').trim();
  if (name && ticker) return `${name} · ${ticker}`;
  return ticker || name || '未知股票';
}

export function formatStockSearchSuggestionLabel(suggestion: StockSearchSuggestion): string {
  return [suggestion.name, suggestion.ticker, suggestion.market].filter(Boolean).join(' · ');
}

export function getAshareTickerSearchCode(ticker: string): string | null {
  const match = ticker.trim().toUpperCase().match(/^(\d{6})(?:\.(SS|SZ))?$/);
  return match ? match[1] : null;
}

export function buildTickerInputUpdate(value: string): { inputValue: string; payloadTicker: string } {
  return { inputValue: value, payloadTicker: value.trim().toUpperCase() };
}

export function shouldShowTickerDropdown(state: { open: boolean; query: string; recentCount: number; suggestionCount: number; loading: boolean }): boolean {
  return state.open && (Boolean(state.query.trim()) || state.recentCount > 0 || state.suggestionCount > 0 || state.loading);
}

export function getRecentAnalyzedTickers(items: AnalysisTask[], limit = 12): string[] {
  const tickers: string[] = [];
  const seen = new Set<string>();
  for (const item of items) {
    const ticker = (item.ticker ?? item.parameters?.ticker ?? '').trim().toUpperCase();
    if (!ticker || seen.has(ticker)) continue;
    seen.add(ticker);
    tickers.push(ticker);
    if (tickers.length >= limit) break;
  }
  return tickers;
}

export function getDefaultTickerFromHistory(items: AnalysisTask[], fallback = defaultParams.ticker): string {
  return getRecentAnalyzedTickers(items, 1)[0] ?? fallback;
}

function normalizeTickerSearch(value: string): string {
  return value.toUpperCase().replace(/[^A-Z0-9]/g, '');
}

function fuzzyIncludesTicker(ticker: string, query: string): boolean {
  const normalizedTicker = normalizeTickerSearch(ticker);
  const normalizedQuery = normalizeTickerSearch(query);
  if (!normalizedQuery) return true;
  if (normalizedTicker.includes(normalizedQuery)) return true;
  let queryIndex = 0;
  for (const char of normalizedTicker) {
    if (char === normalizedQuery[queryIndex]) queryIndex += 1;
    if (queryIndex === normalizedQuery.length) return true;
  }
  return false;
}

export function filterRecentTickerSuggestions(tickers: string[], query: string, limit = 8): string[] {
  return tickers.filter(ticker => fuzzyIncludesTicker(ticker, query)).slice(0, limit);
}

export function buildAnalysisParameterSummary(task: AnalysisTask): string {
  const params = task.parameters;
  if (!params) return '参数未保存';
  return [
    `Agent：${params.analysts.join(', ')}`,
    `深度：${params.research_depth}`,
    `思考：${getThinkingDepthLabel(params)}`,
    `模型：${params.quick_model} / ${params.deep_model}`,
    `提供方：${params.llm_provider}`,
    `语言：${params.output_language}`
  ].join(' · ');
}

export function getDefaultReportSectionName(task: AnalysisTask | null): string | null {
  const sections = task?.report_sections ?? [];
  return sections.length ? sections[sections.length - 1].section_name : null;
}

export function getSelectedReportSection(task: AnalysisTask | null, selectedSectionName: string | null | undefined) {
  const sections = task?.report_sections ?? [];
  if (!sections.length) return null;
  return sections.find(section => section.section_name === selectedSectionName) ?? sections[sections.length - 1];
}

export type MarkdownBlock =
  | { type: 'heading'; level: number; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'list'; ordered: boolean; items: string[] }
  | { type: 'code'; text: string }
  | { type: 'quote'; text: string }
  | { type: 'table'; rows: string[][] }
  | { type: 'hr' };

function isMarkdownTableSeparator(line: string): boolean {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function parseMarkdownTableRow(line: string): string[] {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim());
}

export function parseMarkdownBlocks(markdown: string): MarkdownBlock[] {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n');
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed.startsWith('```')) {
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        codeLines.push(lines[index]);
        index += 1;
      }
      blocks.push({ type: 'code', text: codeLines.join('\n') });
      index += index < lines.length ? 1 : 0;
      continue;
    }

    const heading = /^(#{1,6})\s+(.+)$/.exec(trimmed);
    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2].trim() });
      index += 1;
      continue;
    }

    if (/^(-{3,}|\*{3,})$/.test(trimmed)) {
      blocks.push({ type: 'hr' });
      index += 1;
      continue;
    }

    if (trimmed.includes('|') && index + 1 < lines.length && isMarkdownTableSeparator(lines[index + 1])) {
      const rows = [parseMarkdownTableRow(trimmed)];
      index += 2;
      while (index < lines.length && lines[index].trim().includes('|') && lines[index].trim()) {
        rows.push(parseMarkdownTableRow(lines[index]));
        index += 1;
      }
      blocks.push({ type: 'table', rows });
      continue;
    }

    if (/^[-*]\s+/.test(trimmed) || /^\d+\.\s+/.test(trimmed)) {
      const ordered = /^\d+\.\s+/.test(trimmed);
      const items: string[] = [];
      while (index < lines.length) {
        const itemMatch = ordered ? /^\d+\.\s+(.+)$/.exec(lines[index].trim()) : /^[-*]\s+(.+)$/.exec(lines[index].trim());
        if (!itemMatch) break;
        items.push(itemMatch[1].trim());
        index += 1;
      }
      blocks.push({ type: 'list', ordered, items });
      continue;
    }

    if (trimmed.startsWith('>')) {
      const quoteLines: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith('>')) {
        quoteLines.push(lines[index].trim().replace(/^>\s?/, ''));
        index += 1;
      }
      blocks.push({ type: 'quote', text: quoteLines.join('\n') });
      continue;
    }

    const paragraphLines: string[] = [trimmed];
    index += 1;
    while (
      index < lines.length &&
      lines[index].trim() &&
      !lines[index].trim().startsWith('```') &&
      !/^(#{1,6})\s+/.test(lines[index].trim()) &&
      !/^[-*]\s+/.test(lines[index].trim()) &&
      !/^\d+\.\s+/.test(lines[index].trim()) &&
      !lines[index].trim().startsWith('>') &&
      !(lines[index].trim().includes('|') && index + 1 < lines.length && isMarkdownTableSeparator(lines[index + 1]))
    ) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ type: 'paragraph', text: paragraphLines.join('\n') });
  }

  return blocks;
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
      google_thinking_level: schedule.google_thinking_level,
      openai_reasoning_effort: schedule.openai_reasoning_effort,
      anthropic_effort: schedule.anthropic_effort,
      memory_ids: [...(schedule.memory_ids ?? [])]
    }
  };
}

export function buildMemoryOptionLabel(memory: AgentMemory): string {
  return `${formatAgentName(memory.agent_name)} · ${memory.ticker} · ${memory.analysis_date}`;
}

export function buildMemoryPreviewText(content: string, maxLength = 120): string {
  const text = content
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#>*_`|[\]()]/g, ' ')
    .replace(/^\s*[-\d.]+\s+/gm, '')
    .replace(/\s+/g, ' ')
    .replace(/\s+([:：,，.。;；])/g, '$1')
    .trim();
  return text.length > maxLength ? `${text.slice(0, maxLength).trim()}...` : text;
}

export const memoryRailLayoutClass = 'grid grid-flow-col auto-cols-[minmax(300px,360px)] gap-3 overflow-x-auto pb-3';
export const memoryDateGroupLayoutClass = 'space-y-4';

export type MemoryAgentGroup = {
  agentName: string;
  rawAgentName: string;
  memories: AgentMemory[];
};

export type MemoryAnalysisGroup = {
  sourceAnalysisTaskId: number;
  agentGroups: MemoryAgentGroup[];
};

export type MemoryDateGroup = {
  analysisDate: string;
  analysisGroups: MemoryAnalysisGroup[];
  agentGroups: MemoryAgentGroup[];
};

export type MemoryTickerGroup = {
  ticker: string;
  dateGroups: MemoryDateGroup[];
};

export type MemoryFilterTab = 'ticker' | 'date' | 'agent';

export const memoryFilterTabs: { id: MemoryFilterTab; label: string; allLabel: string }[] = [
  { id: 'ticker', label: '股票代码', allLabel: '全部股票' },
  { id: 'date', label: '日期', allLabel: '全部日期' },
  { id: 'agent', label: 'Agent', allLabel: '全部 Agent' }
];

export type MemoryFilterState = {
  ticker?: string;
  analysisDate?: string;
  agentName?: string;
};

export function flattenMemoryDateGroupMemories(dateGroup: MemoryDateGroup): AgentMemory[] {
  return dateGroup.analysisGroups.flatMap(analysisGroup => analysisGroup.agentGroups.flatMap(agentGroup => agentGroup.memories));
}

export function flattenMemoryAnalysisGroupMemories(analysisGroup: MemoryAnalysisGroup): AgentMemory[] {
  return analysisGroup.agentGroups.flatMap(agentGroup => agentGroup.memories);
}

export function getMemoryFilterOptions(memories: AgentMemory[]): {
  tickers: string[];
  dates: string[];
  agents: { rawName: string; label: string }[];
} {
  const tickers = [...new Set(memories.map(memory => memory.ticker.toUpperCase()))].sort((left, right) => left.localeCompare(right));
  const dates = [...new Set(memories.map(memory => memory.analysis_date))].sort((left, right) => right.localeCompare(left));
  const agents = [...new Set(memories.map(memory => memory.agent_name))]
    .sort((left, right) => formatAgentName(left).localeCompare(formatAgentName(right), 'zh-Hans-CN'))
    .map(rawName => ({ rawName, label: formatAgentName(rawName) }));
  return { tickers, dates, agents };
}

export function filterMemoriesForView(memories: AgentMemory[], filters: MemoryFilterState): AgentMemory[] {
  const ticker = filters.ticker?.trim().toUpperCase();
  const analysisDate = filters.analysisDate?.trim();
  const agentName = filters.agentName?.trim();
  return memories.filter(memory => (
    (!ticker || memory.ticker.toUpperCase() === ticker) &&
    (!analysisDate || memory.analysis_date === analysisDate) &&
    (!agentName || memory.agent_name === agentName)
  ));
}

export function groupMemoriesByTickerDateAgent(memories: AgentMemory[]): MemoryTickerGroup[] {
  const tickerMap = new Map<string, Map<string, Map<number, Map<string, AgentMemory[]>>>>();

  for (const memory of memories) {
    const ticker = memory.ticker.toUpperCase();
    if (!tickerMap.has(ticker)) tickerMap.set(ticker, new Map());
    const dateMap = tickerMap.get(ticker)!;
    if (!dateMap.has(memory.analysis_date)) dateMap.set(memory.analysis_date, new Map());
    const analysisMap = dateMap.get(memory.analysis_date)!;
    if (!analysisMap.has(memory.source_analysis_task_id)) analysisMap.set(memory.source_analysis_task_id, new Map());
    const agentMap = analysisMap.get(memory.source_analysis_task_id)!;
    if (!agentMap.has(memory.agent_name)) agentMap.set(memory.agent_name, []);
    agentMap.get(memory.agent_name)!.push(memory);
  }

  return [...tickerMap.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([ticker, dateMap]) => ({
      ticker,
      dateGroups: [...dateMap.entries()]
        .sort(([left], [right]) => right.localeCompare(left))
        .map(([analysisDate, analysisMap]) => {
          const analysisGroups = [...analysisMap.entries()]
            .sort(([left], [right]) => right - left)
            .map(([sourceAnalysisTaskId, agentMap]) => ({
              sourceAnalysisTaskId,
              agentGroups: [...agentMap.entries()]
                .sort(([left], [right]) => formatAgentName(left).localeCompare(formatAgentName(right), 'zh-Hans-CN'))
                .map(([rawAgentName, groupMemories]) => ({
                  rawAgentName,
                  agentName: formatAgentName(rawAgentName),
                  memories: [...groupMemories].sort((left, right) => right.created_at.localeCompare(left.created_at))
                }))
            }));
          return {
            analysisDate,
            analysisGroups,
            agentGroups: analysisGroups.flatMap(analysisGroup => analysisGroup.agentGroups)
          };
        })
    }));
}

export const ACTIVE_ANALYSIS_TASK_KEY = 'ta_active_analysis_task_id';

export function isAnalysisInProgress(status: string | undefined | null): boolean {
  return ['queued', 'running', 'pending'].includes(status ?? '');
}

export function getSecondsSinceLastAnalysisEvent(task: Pick<AnalysisTask, 'last_event_at' | 'events'>, now = new Date()): number | null {
  const lastEventAt = task.last_event_at ?? task.events?.[task.events.length - 1]?.created_at;
  if (!lastEventAt) return null;
  const seconds = Math.floor((now.getTime() - new Date(lastEventAt).getTime()) / 1000);
  return Number.isFinite(seconds) ? Math.max(0, seconds) : null;
}

export function buildStaleAnalysisWarning(task: AnalysisTask, now = new Date()): string | null {
  if (!isAnalysisInProgress(task.status) || !task.stale) return null;
  const seconds = task.seconds_since_last_event ?? getSecondsSinceLastAnalysisEvent(task, now);
  if (seconds === null) return '该分析任务正在运行，但暂时没有实时事件。可以继续等待，或取消后按原参数重试。';
  const minutes = Math.max(1, Math.floor(seconds / 60));
  return `该分析任务已约 ${minutes} 分钟没有新的实时事件，可能已卡住。可以继续等待，或取消后按原参数重试。`;
}

export function deriveAnalysisStatusFromEvent(currentStatus: string, event: AgentEvent): string {
  if (event.event_type === 'task.started') return 'running';
  if (event.event_type === 'task.completed') return 'completed';
  if (event.event_type === 'task.failed') return 'failed';
  if (event.event_type === 'task.cancelled') return 'cancelled';
  return currentStatus;
}

export function getRecoverableAnalysisTaskId(
  items: AnalysisTask[],
  selectedTaskId: number | null | undefined,
  storedTaskId: number | null | undefined
): number | null {
  if (selectedTaskId) return null;
  const activeItems = items.filter(item => isAnalysisInProgress(item.status));
  if (!activeItems.length) return null;
  if (storedTaskId && activeItems.some(item => item.id === storedTaskId)) return storedTaskId;
  return activeItems.reduce((latest, item) => (item.id > latest.id ? item : latest), activeItems[0]).id;
}

const ANALYST_AGENT_NAMES: Record<string, string> = {
  market: 'Market Analyst',
  social: 'Social Analyst',
  news: 'News Analyst',
  fundamentals: 'Fundamentals Analyst'
};
const TRANSPORT_EVENT_AGENTS = new Set(['Graph']);
const FLOW_DETAIL_SECTION_BY_AGENT: Record<string, string> = {
  'Market Analyst': 'market_report',
  'Social Analyst': 'sentiment_report',
  'News Analyst': 'news_report',
  'Fundamentals Analyst': 'fundamentals_report',
  'Research Manager': 'investment_plan',
  Trader: 'trader_investment_plan',
  'Portfolio Manager': 'final_trade_decision'
};

export type AgentProgressStepStatus = 'waiting' | 'active' | 'done' | 'failed';

export type AgentProgressStep = {
  agent: string;
  label: string;
  status: AgentProgressStepStatus;
  lastMessage?: string;
  outputMessage?: string;
  sectionName?: string;
  eventCount: number;
  lastEventType?: string;
};

export type AgentFlowRound = {
  round: number;
  events: AgentEvent[];
  summary: string;
};

export type AgentFlowOutputDetail = {
  title: string;
  meta: string;
  content: string;
  source: 'report_section' | 'final_decision' | 'event';
};

function pushUniqueAgent(agents: string[], agent: string | undefined | null) {
  const normalized = agent?.trim();
  if (normalized && !agents.includes(normalized)) agents.push(normalized);
}

export function buildAgentProgressSteps(events: AgentEvent[], taskStatus: string | undefined | null, analysts: string[] = []): AgentProgressStep[] {
  const agents: string[] = ['System'];
  analysts.map(analyst => ANALYST_AGENT_NAMES[analyst] ?? analyst).forEach(agent => pushUniqueAgent(agents, agent));
  events.forEach(event => {
    if (!TRANSPORT_EVENT_AGENTS.has(event.agent) && !['System', 'Portfolio Manager'].includes(event.agent)) {
      pushUniqueAgent(agents, event.agent);
    }
  });
  ['Research Manager', 'Trader', 'Portfolio Manager'].forEach(agent => pushUniqueAgent(agents, agent));

  const completedAgents = new Set<string>();
  const lastMessageByAgent = new Map<string, string>();
  const outputMessageByAgent = new Map<string, string>();
  const sectionByAgent = new Map<string, string>();
  const eventCountByAgent = new Map<string, number>();
  const lastEventTypeByAgent = new Map<string, string>();
  let failedAgent: string | null = null;
  for (const event of events) {
    if (!TRANSPORT_EVENT_AGENTS.has(event.agent)) {
      lastMessageByAgent.set(event.agent, event.message);
      eventCountByAgent.set(event.agent, (eventCountByAgent.get(event.agent) ?? 0) + 1);
      lastEventTypeByAgent.set(event.agent, event.event_type);
    }
    if (event.event_type === 'task.started') completedAgents.add('System');
    if (event.event_type === 'report.section' || event.event_type.includes('completed')) {
      completedAgents.add(event.agent);
      if (event.event_type === 'report.section' || event.event_type === 'agent.completed') {
        outputMessageByAgent.set(event.agent, event.message);
        const section = event.payload?.section;
        if (typeof section === 'string') sectionByAgent.set(event.agent, section);
      }
    }
    if (event.event_type.includes('failed')) failedAgent = TRANSPORT_EVENT_AGENTS.has(event.agent) ? 'System' : event.agent;
  }

  if (taskStatus === 'completed') {
    agents.forEach(agent => completedAgents.add(agent));
  }
  if (taskStatus === 'failed' && !failedAgent) {
    failedAgent = events.length ? events[events.length - 1].agent : 'System';
  }

  let activeAgent: string | null = null;
  if (isAnalysisInProgress(taskStatus)) {
    activeAgent = agents.find(agent => !completedAgents.has(agent)) ?? null;
  }

  return agents.map(agent => ({
    agent,
    label: formatAgentName(agent),
    status: failedAgent === agent ? 'failed' : completedAgents.has(agent) ? 'done' : activeAgent === agent ? 'active' : 'waiting',
    lastMessage: lastMessageByAgent.get(agent),
    outputMessage: outputMessageByAgent.get(agent),
    sectionName: sectionByAgent.get(agent),
    eventCount: eventCountByAgent.get(agent) ?? 0,
    lastEventType: lastEventTypeByAgent.get(agent)
  }));
}

function isRoundAdvancingOutput(event: AgentEvent): boolean {
  return event.event_type === 'report.section' || event.event_type === 'agent.completed';
}

function isAgentFlowDetailEvent(event: AgentEvent): boolean {
  return event.event_type === 'report.section' || event.event_type === 'agent.completed' || event.event_type === 'debate.message';
}

function getDebateRoundKey(event: AgentEvent): string | null {
  if (event.event_type !== 'debate.message') return null;
  const debate = typeof event.payload?.debate === 'string' ? event.payload.debate : 'debate';
  const round = typeof event.payload?.round === 'number' ? event.payload.round : null;
  return round ? `${debate}:${round}` : null;
}

function formatDebateName(debate: string): string {
  if (debate === 'investment') return '投研辩论';
  if (debate === 'risk') return '风控辩论';
  return '辩论';
}

function formatDebateRoundLabel(event: AgentEvent): string | null {
  if (event.event_type !== 'debate.message') return null;
  const debate = typeof event.payload?.debate === 'string' ? event.payload.debate : 'debate';
  const round = typeof event.payload?.round === 'number' ? event.payload.round : null;
  return round ? `${formatDebateName(debate)}第 ${round} 轮` : formatDebateName(debate);
}

function buildAgentFlowRoundSummary(events: AgentEvent[]): string {
  const debateLabels = Array.from(new Set(events.map(formatDebateRoundLabel).filter(Boolean)));
  const agents = Array.from(new Set(events.map(item => item.agent).filter(Boolean))).map(formatAgentName);
  return [...debateLabels, ...agents].join('、');
}

export function buildAgentFlowRoundGroups(events: AgentEvent[]): AgentFlowRound[] {
  const sorted = [...events].sort((a, b) => a.sequence - b.sequence);
  const rounds: AgentFlowRound[] = [];
  let currentEvents: AgentEvent[] = [];
  let round = 1;
  let outputAgentsThisRound = new Set<string>();
  let currentDebateRoundKey: string | null = null;

  for (const event of sorted) {
    const debateRoundKey = getDebateRoundKey(event);
    const advancesDebateRound = Boolean(currentEvents.length && debateRoundKey && currentDebateRoundKey && debateRoundKey !== currentDebateRoundKey);
    const advancesRound = !currentDebateRoundKey && isRoundAdvancingOutput(event) && outputAgentsThisRound.has(event.agent);
    if (advancesDebateRound && currentEvents.length) {
      rounds.push({
        round,
        events: currentEvents,
        summary: buildAgentFlowRoundSummary(currentEvents)
      });
      round += 1;
      currentEvents = [];
      outputAgentsThisRound = new Set<string>();
      currentDebateRoundKey = null;
    }
    if (advancesRound && currentEvents.length) {
      rounds.push({
        round,
        events: currentEvents,
        summary: buildAgentFlowRoundSummary(currentEvents)
      });
      round += 1;
      currentEvents = [];
      outputAgentsThisRound = new Set<string>();
    }
    currentEvents.push(event);
    if (debateRoundKey) currentDebateRoundKey = debateRoundKey;
    if (isRoundAdvancingOutput(event)) outputAgentsThisRound.add(event.agent);
  }

  if (currentEvents.length) {
    rounds.push({
      round,
      events: currentEvents,
      summary: buildAgentFlowRoundSummary(currentEvents)
    });
  }
  return rounds;
}

export function resolveAgentFlowOutputDetail(task: AnalysisTask | null, event: AgentEvent): AgentFlowOutputDetail {
  const explicitSectionName = typeof event.payload?.section === 'string' ? event.payload.section : null;
  const inferredSectionName = explicitSectionName ?? FLOW_DETAIL_SECTION_BY_AGENT[event.agent] ?? null;
  if (event.agent === 'Portfolio Manager') {
    const finalContent = task?.final_decision?.rationale ?? task?.report_sections?.find(section => section.section_name === 'final_trade_decision')?.content;
    if (finalContent) {
      return {
        title: '最终交易决策',
        meta: `${formatAgentName(event.agent)} · 完整决策理由`,
        content: finalContent,
        source: 'final_decision'
      };
    }
  }

  const reportSection = inferredSectionName ? task?.report_sections?.find(section => section.section_name === inferredSectionName) : null;
  if (reportSection?.content) {
    return {
      title: formatSectionName(reportSection.section_name),
      meta: `${formatAgentName(event.agent)} · 完整 Markdown 报告`,
      content: reportSection.content,
      source: 'report_section'
    };
  }

  return {
    title: `${formatAgentName(event.agent)} · ${formatEventTypeLabel(event.event_type)}`,
    meta: explicitSectionName ? formatSectionName(explicitSectionName) : formatEventTypeLabel(event.event_type),
    content: event.message,
    source: 'event'
  };
}

export function toggleMemoryId(current: number[] = [], memoryId: number): number[] {
  return current.includes(memoryId) ? current.filter(id => id !== memoryId) : [...current, memoryId];
}

export function buildInterventionLabel(session: InterventionSession): string {
  return `#${session.id} · 分析 ${session.source_analysis_task_id} · ${formatAgentName(session.target_agent_name)} · ${formatStatusLabel(session.status)}`;
}

export function formatWorkspaceRoleLabel(role: WorkspaceRole): string {
  return roleLabels[role] ?? role;
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

const inputClass = 'w-full rounded-card border border-subtle bg-surface/80 px-3 py-2 text-sm text-primary shadow-panel outline-none transition placeholder:text-subtle focus:border-accent focus:ring-2 focus:ring-accent/25';

const roleLabels: Record<WorkspaceRole, string> = {
  owner: '所有者',
  admin: '管理员',
  member: '成员',
  viewer: '观察者'
};

const statusLabels: Record<string, string> = {
  ok: '正常',
  open: '进行中',
  active: '生效中',
  paused: '已暂停',
  closed: '已关闭',
  completed: '已完成',
  failed: '失败',
  running: '运行中',
  waiting: '待处理',
  done: '已完成',
  pending: '等待中',
  queued: '排队中',
  cancelled: '已取消',
  暂无: '暂无'
};

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

const intervalLabels: Record<string, string> = { daily: '每日', weekly: '每周', monthly: '每月' };

const resourceTypeLabels: Record<string, string> = {
  analyses: '分析',
  schedules: '计划',
  memories: '记忆',
  interventions: '介入会话',
  audit_logs: '审计日志',
  usage_ledger: '用量账本'
};

export function formatStatusLabel(status: string | undefined | null): string {
  if (!status) return '未知';
  return statusLabels[status] ?? status;
}

export function formatAgentName(agentName: string): string {
  return agentLabels[agentName] ?? agentName;
}

function formatIntervalLabel(interval: string | undefined | null): string {
  if (!interval) return '未知';
  return intervalLabels[interval] ?? interval;
}

function formatResourceTypeLabel(resourceType: string | undefined | null): string {
  if (!resourceType) return '未知';
  return resourceTypeLabels[resourceType] ?? resourceType;
}

function formatDecisionLabel(decision: string | undefined | null): string {
  if (!decision) return '等待结论';
  const normalized = decision.toUpperCase();
  if (normalized === 'BUY') return '买入';
  if (normalized === 'SELL') return '卖出';
  if (normalized === 'HOLD') return '持有';
  if (normalized === 'PENDING') return '等待结论';
  return decision;
}

function formatEventTypeLabel(eventType: string): string {
  if (eventType === 'debate.message') return '辩论发言';
  return eventType
    .replace('analysis.', '分析.')
    .replace('schedule.', '计划.')
    .replace('intervention.', '介入.')
    .replace('cost.', '成本.')
    .replace('auth.', '认证.');
}

function formatSectionName(sectionName: string): string {
  return sectionName
    .replace('market_report', '市场报告')
    .replace('news_report', '新闻报告')
    .replace('fundamentals_report', '基本面报告')
    .replace('social_report', '社媒报告')
    .replace('investment_plan', '投资计划')
    .replace('final_trade_decision', '最终交易决策');
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <div className="block space-y-1.5 text-sm"><span className="text-label">{label}</span>{children}{hint && <span className="block text-xs text-subtle">{hint}</span>}</div>;
}

function AnalystMultiSelect({ selected, onChange }: { selected: string[]; onChange: (analysts: string[]) => void }) {
  return (
    <details className="group relative">
      <summary className="surface-interactive flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-sm text-primary outline-none group-open:border-accent group-open:ring-2 group-open:ring-accent/25">
        <span className="truncate">{formatSelectedAnalysts(selected)}</span>
        <span className="text-xs text-subtle group-open:rotate-180">⌄</span>
      </summary>
      <div className="surface-panel absolute z-30 mt-2 w-full min-w-72 p-3">
        <div className="mb-2 flex items-center justify-between gap-2 border-b border-subtle pb-2">
          <span className="text-label">多选分析师 Agent</span>
          <button type="button" className="chip-accent hover:bg-accent/20" onClick={() => onChange([...defaultAnalysts])}>全选</button>
        </div>
        <div className="space-y-2">
          {analystOptions.map(option => {
            const checked = selected.includes(option.value);
            const locked = checked && selected.length === 1;
            return (
              <label key={option.value} className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition ${checked ? 'border-accent bg-accent-soft/80' : 'border-subtle bg-surface/60 hover:border-accent/35 hover:bg-surface-strong/75'}`}>
                <input
                  type="checkbox"
                  className="mt-1 accent-cyan-600"
                  checked={checked}
                  disabled={locked}
                  onChange={() => onChange(toggleAnalystSelection(selected, option.value))}
                />
                <span>
                  <span className="block font-semibold text-primary">{option.label}</span>
                  <span className="block text-xs leading-5 text-muted">{option.description}</span>
                </span>
              </label>
            );
          })}
        </div>
        <p className="mt-2 text-xs text-subtle">至少保留 1 个 Agent；默认全选。</p>
      </div>
    </details>
  );
}

function MiniStat({ label, value }: { label: string; value: string | number }) {
  return <div className="surface-card p-4"><p className="text-label">{label}</p><p className="text-data mt-1 text-base font-bold">{value}</p></div>;
}

function MetricCard({ label, value, detail }: { label: string; value: number | string; detail: string }) {
  return <div className="surface-panel p-5"><p className="text-label">{label}</p><p className="text-data mt-2 text-3xl font-black">{value}</p><p className="mt-1 text-xs text-muted">{detail}</p></div>;
}

function Notice({ tone, children }: { tone: 'amber' | 'red'; children: ReactNode }) {
  const classes = tone === 'amber' ? 'border-caution/35 bg-caution-soft/85 text-caution' : 'border-negative/35 bg-negative-soft/85 text-negative';
  return <div className={`rounded-2xl border p-4 text-sm ${classes}`}>{children}</div>;
}

function StatusBadge({ status }: { status: string | undefined | null }) {
  const normalized = status ?? 'unknown';
  const positive = ['ok', 'active', 'completed', 'open', 'running'].includes(normalized);
  const paused = ['paused', 'pending', 'queued'].includes(normalized);
  const color = positive ? 'status-positive' : paused ? 'status-caution' : 'status-negative';
  return <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${color}`}>{formatStatusLabel(normalized)}</span>;
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return <div className="surface-card border-dashed p-8 text-center"><p className="font-semibold text-primary">{title}</p><p className="mt-2 text-sm text-subtle">{description}</p></div>;
}

function InfoBlock({ title, children }: { title: string; children: ReactNode }) {
  return <div className="surface-card p-4"><h4 className="mb-3 font-semibold text-primary">{title}</h4>{children}</div>;
}

export function ModalCloseButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label="关闭弹窗"
      className="inline-flex items-center justify-center gap-2 rounded-pill bg-accent px-4 py-2 text-sm font-bold text-accent-foreground shadow-glow transition hover:bg-accent-strong focus:outline-none focus:ring-4 focus:ring-accent/25"
      onClick={onClick}
    >
      <span aria-hidden="true">×</span>
      <span>关闭</span>
    </button>
  );
}

function MemoryPicker({ title, memories, selectedIds, onToggle }: { title: string; memories: AgentMemory[]; selectedIds: number[]; onToggle: (memoryId: number) => void }) {
  return <div className="surface-card p-3 text-sm"><p className="mb-2 text-label">{title}</p>{memories.length ? memories.map(memory => <label key={memory.id} className="flex items-center gap-2 py-1 text-muted"><input type="checkbox" checked={selectedIds.includes(memory.id)} onChange={() => onToggle(memory.id)} /> <span>{buildMemoryOptionLabel(memory)}</span></label>) : <p className="text-xs text-subtle">暂无可选记忆</p>}</div>;
}

function OpenDesignBrand() {
  return (
    <span className="od-brand">
      <img className="od-brand-icon" src="/logo.png" alt="" aria-hidden="true" />
      <span>TradingAgents</span>
    </span>
  );
}

function LandingAnalysisPreview({
  mode,
  ticker,
  analysisDate,
  memoryCount,
  title = 'New analysis',
  briefLabel = 'Analysis brief',
  statusText = 'Ready to stream',
  decisionLabel = 'HOLD',
  steps,
  onLaunch,
  disabled,
  actionLabel = '启动分析'
}: {
  mode: string;
  ticker: string;
  analysisDate: string;
  memoryCount: number;
  title?: string;
  briefLabel?: string;
  statusText?: string;
  decisionLabel?: string;
  steps?: string[];
  onLaunch?: () => void;
  disabled?: boolean;
  actionLabel?: string;
}) {
  const previewSteps = steps ?? ['抓取行情、新闻与基本面上下文', '四类分析师生成分工报告', '研究经理整合牛熊论点', '输出最终交易决策与记忆'];
  return (
    <div className="od-collage" aria-label="TradingAgents 分析生成器预览">
      <div className="floating-ticket hidden border border-strong bg-surface p-3 font-mono text-xs leading-5 text-muted shadow-panel lg:block" aria-hidden="true">
        <b className="mb-2 block text-base text-primary">TA-01</b>
        ticker input<br />agent debate<br />live memory
      </div>
      <div className="od-canvas-card">
        <header className="flex min-h-12 items-center justify-between border-b border-strong px-4 font-mono text-[11px] uppercase tracking-[0.13em]">
          <span>{title}</span>
          <span className="text-accent">{mode}</span>
        </header>
        <div className="grid gap-4 p-5">
          <div className="text-label text-accent">{briefLabel}</div>
          <div className="grid gap-2 sm:grid-cols-2" aria-label="分析参数概览">
            <div className="rounded-card border border-subtle bg-surface-strong p-3">
              <span className="text-label">Ticker</span>
              <strong className="mt-1 block text-lg text-primary">{ticker || 'SPY'}</strong>
            </div>
            <div className="rounded-card border border-subtle bg-surface-strong p-3">
              <span className="text-label">Date</span>
              <strong className="mt-1 block text-lg text-primary">{analysisDate}</strong>
            </div>
            <div className="rounded-card border border-subtle bg-surface-strong p-3 sm:col-span-2">
              <span className="text-label">Analyst agents</span>
              <div className="mt-2 flex flex-wrap gap-2">
                {['Market', 'News', 'Social', 'Fundamentals'].map((agent, index) => (
                  <span key={agent} className={`rounded-pill border px-3 py-1 text-xs ${index === 0 ? 'border-accent text-accent' : 'border-subtle text-muted'}`}>{agent}</span>
                ))}
              </div>
            </div>
            <div className="rounded-card border border-subtle bg-surface-strong p-3">
              <span className="text-label">Memory</span>
              <strong className="mt-1 block text-lg text-primary">{memoryCount} notes</strong>
            </div>
            <div className="rounded-card border border-subtle bg-surface-strong p-3">
              <span className="text-label">Reasoning</span>
              <strong className="mt-1 block text-lg text-primary">High</strong>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="inline-flex items-center gap-2 font-mono text-xs text-muted"><i className="h-2.5 w-2.5 rounded-full bg-positive shadow-[0_0_0_4px_hsl(var(--positive)_/_0.16)]" aria-hidden="true" /> {statusText}</span>
            {onLaunch ? (
              <Button type="button" onClick={onLaunch} disabled={disabled}>
                <PlayCircle size={16} />{actionLabel}
              </Button>
            ) : null}
          </div>
        </div>
        <div className="grid border-t border-strong lg:grid-cols-[1.1fr_0.9fr]" aria-label="实时分析预览状态">
          <div className="border-strong bg-canvas p-5 lg:border-r">
            <div className="grid min-h-52 grid-rows-[34px_1fr] border border-strong bg-surface">
              <div className="flex items-center justify-between border-b border-strong px-3 font-mono text-[10px] text-muted">
                <span className="flex gap-1.5"><i className="h-2 w-2 rounded-full border border-strong" /><i className="h-2 w-2 rounded-full border border-strong" /><i className="h-2 w-2 rounded-full border border-strong" /></span>
                <span>agent stream</span>
              </div>
              <div className="grid gap-3 p-3 sm:grid-cols-[1fr_0.76fr]">
                <div className="grid content-start gap-2">
                  {['Market Analyst', 'News Analyst', 'Research Manager', 'Portfolio Manager'].map((agent, index) => (
                    <div key={agent} className="grid min-h-7 grid-cols-[24px_1fr_auto] items-center gap-2 border border-subtle bg-surface px-2 py-1 text-xs">
                      <i className={`h-[18px] w-[18px] rounded-full border border-strong ${index < 2 ? 'bg-positive' : index === 2 ? 'bg-caution' : 'bg-accent'}`} />
                      <span>{agent}</span>
                      <b className="font-mono text-[11px] text-muted">{index < 2 ? 'done' : index === 2 ? 'debate' : 'final'}</b>
                    </div>
                  ))}
                </div>
                <div className="relative grid min-h-40 content-end gap-2 border border-strong bg-accent-soft p-3">
                  <span className="absolute right-3 top-3 border border-strong bg-surface px-2 py-1 font-mono text-[10px]">{decisionLabel}</span>
                  <span className="h-2.5 w-4/5 bg-primary" />
                  <span className="h-2.5 w-3/5 bg-primary" />
                  <span className="h-2.5 w-2/3 bg-accent" />
                </div>
              </div>
            </div>
          </div>
          <div className="grid">
            {previewSteps.map((step, index) => (
              <div key={step} className="grid grid-cols-[auto_1fr] items-center gap-3 border-b border-strong px-4 py-3 text-sm text-primary last:border-b-0">
                <span className="grid h-7 w-7 place-items-center rounded-full border border-strong bg-surface font-mono text-[11px]">{String(index + 1).padStart(2, '0')}</span>
                <span>{step}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="hidden rotate-[5deg] border border-strong bg-surface-strong p-4 font-serif text-2xl leading-none shadow-panel lg:absolute lg:bottom-20 lg:right-0 lg:block" aria-hidden="true">decision,<br />not dashboard noise</div>
    </div>
  );
}

function InlineMarkdown({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean);
  return (
    <>
      {parts.map((part, index) => {
        if (part.startsWith('`') && part.endsWith('`')) {
          return <code key={index} className="rounded bg-panel-muted px-1 py-0.5 text-[0.9em] text-primary">{part.slice(1, -1)}</code>;
        }
        if (part.startsWith('**') && part.endsWith('**')) {
          return <strong key={index} className="font-bold text-primary">{part.slice(2, -2)}</strong>;
        }
        return <span key={index}>{part}</span>;
      })}
    </>
  );
}

export function MarkdownDocument({ content, className = '' }: { content: string; className?: string }) {
  const blocks = parseMarkdownBlocks(content);
  return (
    <div className={`space-y-4 text-sm leading-7 text-muted ${className}`}>
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          const HeadingTag = `h${Math.min(block.level + 2, 6)}` as 'h3' | 'h4' | 'h5' | 'h6';
          return <HeadingTag key={index} className="mt-6 font-black text-primary first:mt-0"><InlineMarkdown text={block.text} /></HeadingTag>;
        }
        if (block.type === 'paragraph') {
          return <p key={index} className="whitespace-pre-wrap"><InlineMarkdown text={block.text} /></p>;
        }
        if (block.type === 'list') {
          const ListTag = block.ordered ? 'ol' : 'ul';
          return <ListTag key={index} className={`space-y-1 pl-5 ${block.ordered ? 'list-decimal' : 'list-disc'}`}>{block.items.map((item, itemIndex) => <li key={itemIndex}><InlineMarkdown text={item} /></li>)}</ListTag>;
        }
        if (block.type === 'code') {
          return <pre key={index} className="overflow-auto rounded-card bg-background p-4 text-xs leading-6 text-primary"><code>{block.text}</code></pre>;
        }
        if (block.type === 'quote') {
          return <blockquote key={index} className="border-l-4 border-accent bg-accent-soft/70 px-4 py-3 text-muted"><InlineMarkdown text={block.text} /></blockquote>;
        }
        if (block.type === 'table') {
          const [header, ...rows] = block.rows;
          return (
            <div key={index} className="surface-card overflow-auto">
              <table className="min-w-full divide-y divide-subtle text-left text-sm">
                <thead className="bg-surface-strong/80"><tr>{header.map((cell, cellIndex) => <th key={cellIndex} className="px-3 py-2 font-semibold text-primary"><InlineMarkdown text={cell} /></th>)}</tr></thead>
                <tbody className="divide-y divide-subtle">{rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex} className="px-3 py-2"><InlineMarkdown text={cell} /></td>)}</tr>)}</tbody>
              </table>
            </div>
          );
        }
        return <hr key={index} className="border-subtle" />;
      })}
    </div>
  );
}

export function MemoryDetailModal({ memory, onClose }: { memory: AgentMemory; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/75 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="智能体记忆详情">
      <div className="surface-panel-strong max-h-[88vh] w-full max-w-4xl overflow-hidden">
        <div className="flex flex-col gap-4 border-b border-subtle bg-surface-strong/90 p-5 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-label text-accent">智能体记忆详情</p>
            <h3 className="mt-1 text-xl font-black text-primary">{memory.title}</h3>
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted">
              <span className="chip-accent">股票：{memory.ticker}</span>
              <span className="chip-accent">日期：{memory.analysis_date}</span>
              <span className="chip-accent">Agent：{formatAgentName(memory.agent_name)}</span>
              <span className="chip-accent">来源分析：#{memory.source_analysis_task_id}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={memory.archived ? 'paused' : 'active'} />
            <ModalCloseButton onClick={onClose} />
          </div>
        </div>
        <div className="max-h-[62vh] overflow-auto p-6">
          <div className="mb-5 grid gap-3 md:grid-cols-3">
            <MiniStat label="股票代码" value={memory.ticker} />
            <MiniStat label="分析日期" value={memory.analysis_date} />
            <MiniStat label="记忆来源" value={memory.tags?.section ? formatSectionName(String(memory.tags.section)) : `分析 #${memory.source_analysis_task_id}`} />
          </div>
          <MarkdownDocument content={memory.content} />
        </div>
      </div>
    </div>
  );
}

function flowEventTone(event: AgentEvent): string {
  if (event.event_type.includes('failed')) return 'border-negative/35 bg-negative-soft text-negative';
  if (event.event_type === 'debate.message') return 'border-caution/35 bg-caution-soft text-caution';
  if (event.event_type === 'tool.call') return 'border-accent/35 bg-surface-strong text-accent';
  if (event.event_type === 'report.section' || event.event_type.includes('completed')) return 'border-positive/35 bg-positive-soft text-positive';
  if (event.event_type.includes('message')) return 'border-accent/35 bg-accent-soft text-accent';
  return 'border-subtle bg-surface text-muted';
}

export function getEventsForTask(task: Pick<AnalysisTask, 'id'>, events: AgentEvent[]): AgentEvent[] {
  const taskScopedEvents = events.filter(event => event.task_id === task.id);
  if (taskScopedEvents.length) return taskScopedEvents;
  if (events.some(event => event.task_id !== undefined && event.task_id !== task.id)) return [];
  return events;
}

export function AgentProgressFlow({ task, events }: { task: AnalysisTask; events: AgentEvent[] }) {
  const scopedEvents = getEventsForTask(task, events);
  const steps = buildAgentProgressSteps(scopedEvents, task.status, task.parameters?.analysts);
  const rounds = buildAgentFlowRoundGroups(scopedEvents);
  const [selectedOutput, setSelectedOutput] = useState<AgentFlowOutputDetail | null>(null);
  const [selectedRoundNumber, setSelectedRoundNumber] = useState<number>(1);
  const [followLatestRound, setFollowLatestRound] = useState(true);
  const roundEventsRef = useRef<HTMLDivElement | null>(null);
  const latestRound = rounds.length ? rounds[rounds.length - 1] : null;
  const latestRoundNumber = latestRound?.round ?? 1;
  const selectedRound: AgentFlowRound | null = rounds.find(round => round.round === selectedRoundNumber) ?? latestRound;
  const activeStep = steps.find(step => step.status === 'active');
  const completedCount = steps.filter(step => step.status === 'done').length;
  const statusClass: Record<AgentProgressStepStatus, string> = {
    waiting: 'border-subtle bg-surface text-subtle',
    active: 'border-accent bg-accent-soft text-accent shadow-glow ring-2 ring-accent/20',
    done: 'border-positive/35 bg-positive-soft text-positive shadow-panel',
    failed: 'border-negative/35 bg-negative-soft text-negative'
  };
  const dotLabel: Record<AgentProgressStepStatus, string> = {
    waiting: '待',
    active: '中',
    done: '✓',
    failed: '!'
  };
  const progressStatusLabel: Record<AgentProgressStepStatus, string> = {
    waiting: '待处理',
    active: '分析中',
    done: '已完成',
    failed: '失败'
  };

  useEffect(() => {
    setSelectedOutput(null);
    setFollowLatestRound(true);
    setSelectedRoundNumber(1);
  }, [task.id]);

  useEffect(() => {
    if (!rounds.length) return;
    setSelectedRoundNumber(current => {
      if (followLatestRound) return latestRoundNumber;
      return Math.min(current, latestRoundNumber);
    });
  }, [followLatestRound, latestRoundNumber, rounds.length]);

  useEffect(() => {
    if (!roundEventsRef.current) return;
    roundEventsRef.current.scrollTop = roundEventsRef.current.scrollHeight;
  }, [selectedRoundNumber, selectedRound?.events.length]);

  return (
    <div className="surface-panel-strong space-y-4 bg-radial-focus p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-label text-accent">实时流程图</p>
          <h3 className="font-black text-primary">Agent 分析状态与实时产出</h3>
          <p className="mt-1 text-xs text-muted">当前：{activeStep?.label ?? (task.status === 'completed' ? '全部完成' : '等待事件')} · 事件 {scopedEvents.length} 条 · 完成 {completedCount}/{steps.length}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={task.status} />
          <span className="chip-accent">{rounds.length || 1} 轮轨迹</span>
          {!followLatestRound && rounds.length ? (
            <Button className="bg-surface-strong text-primary hover:bg-surface-elevated" onClick={() => { setFollowLatestRound(true); setSelectedRoundNumber(latestRoundNumber); }}>跟随最新</Button>
          ) : null}
        </div>
      </div>
      <div className="overflow-x-auto pb-2">
        <div className="flex min-w-max items-stretch gap-2">
          {steps.map((step, index) => (
            <div key={`${step.agent}-${index}`} className="flex items-center gap-2">
              <div className={`w-56 rounded-2xl border p-3 transition-all duration-300 ${statusClass[step.status]}`}>
                <div className="flex items-center gap-2">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-elevated text-sm font-black text-primary shadow-panel">{dotLabel[step.status]}</span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-bold">{step.label}</p>
                    <p className="truncate text-[11px] opacity-75">{progressStatusLabel[step.status]} · {step.eventCount} 条事件</p>
                  </div>
                </div>
                {step.lastMessage && (
                  <div className="mt-3 rounded-card bg-surface-elevated/80 p-2 text-xs leading-5 text-muted">
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <p className="font-semibold text-muted">{step.outputMessage ? '阶段产出' : '实时输出'}</p>
                      {(() => {
                        const detailEvent = [...scopedEvents].reverse().find(event => event.agent === step.agent && isAgentFlowDetailEvent(event));
                        return detailEvent ? (
                        <button
                          type="button"
                          className="rounded-pill bg-surface px-2 py-0.5 text-[10px] font-semibold text-accent ring-1 ring-accent/20 hover:bg-surface-strong"
                          onClick={() => setSelectedOutput(resolveAgentFlowOutputDetail(task, detailEvent))}
                        >
                          查看详情
                        </button>
                        ) : null;
                      })()}
                    </div>
                    <MarkdownDocument content={step.outputMessage ?? step.lastMessage} className="line-clamp-4 text-xs leading-5" />
                  </div>
                )}
                {step.sectionName && <span className="chip-accent mt-2">{formatSectionName(step.sectionName)}</span>}
              </div>
              {index < steps.length - 1 && (
                <div className={`h-1 w-8 shrink-0 rounded-full transition-colors duration-300 ${step.status === 'done' ? 'bg-positive' : step.status === 'active' ? 'bg-accent animate-pulse' : 'bg-muted'}`} />
              )}
            </div>
          ))}
        </div>
      </div>
      <div className="surface-card p-3">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div>
            <p className="text-label text-positive">讨论与产出轨迹</p>
            <p className="text-sm font-bold text-primary">按轮次展开 Agent 思考、工具调用与报告产出</p>
          </div>
        </div>
        {rounds.length && selectedRound ? (
          <div className="grid gap-3 lg:grid-cols-[220px_minmax(0,1fr)]">
            <aside className="surface-card p-3">
              <p className="mb-2 text-label">轮次导航</p>
              <div className="flex gap-2 overflow-x-auto pb-1 lg:max-h-[420px] lg:flex-col lg:overflow-y-auto lg:pb-0">
                {rounds.map(round => {
                  const active = selectedRound.round === round.round;
                  return (
                    <button
                      key={round.round}
                      type="button"
                      onClick={() => { setFollowLatestRound(false); setSelectedRoundNumber(round.round); }}
                      className={`shrink-0 rounded-2xl border px-3 py-2 text-left text-xs transition ${active ? 'border-accent bg-accent-soft text-accent shadow-panel' : 'border-subtle bg-surface text-muted hover:border-accent/35 hover:bg-surface-strong'}`}
                    >
                      <span className="block font-bold">第 {round.round} 轮</span>
                      <span className="mt-1 block truncate">{round.events.length} 条 · {round.summary}</span>
                    </button>
                  );
                })}
              </div>
            </aside>
            <section className="surface-card p-3">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="chip-accent">第 {selectedRound.round} 轮</span>
                  <p className="mt-2 text-xs text-subtle">{selectedRound.summary}</p>
                </div>
                <span className="chip-accent">{selectedRound.events.length} 条事件</span>
              </div>
              <div ref={roundEventsRef} className="max-h-[420px] space-y-2 overflow-auto pr-1">
                {selectedRound.events.map(event => {
                  const isDetailedOutput = isAgentFlowDetailEvent(event);
                  return (
                    <article key={event.sequence} className={`rounded-2xl border p-3 ${flowEventTone(event)}`}>
                      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                        <span className="chip-accent font-bold">#{event.sequence}</span>
                        <span className="font-semibold">{formatAgentName(event.agent)}</span>
                        <span className="opacity-70">{formatEventTypeLabel(event.event_type)}</span>
                        {formatDebateRoundLabel(event) && <span className="chip-accent">{formatDebateRoundLabel(event)}</span>}
                        {typeof event.payload?.section === 'string' && <span className="chip-accent">{formatSectionName(event.payload.section)}</span>}
                        {isDetailedOutput && (
                          <button
                            type="button"
                            className="ml-auto rounded-pill bg-surface px-2.5 py-1 text-[11px] font-semibold text-accent ring-1 ring-accent/20 hover:bg-surface-strong"
                            onClick={() => setSelectedOutput(resolveAgentFlowOutputDetail(task, event))}
                          >
                            查看详情
                          </button>
                        )}
                      </div>
                      <MarkdownDocument content={event.message} className="line-clamp-5 text-xs leading-5" />
                    </article>
                  );
                })}
              </div>
            </section>
          </div>
        ) : (
          <p className="rounded-2xl border border-dashed border-slate-200 bg-white p-4 text-sm text-slate-400">等待实时事件。分析开始后，Agent 的思考、讨论、工具调用和阶段报告会在这里动态出现。</p>
        )}
      </div>
      {selectedOutput && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="阶段产出详情">
          <div className="surface-panel-strong max-h-[88vh] w-full max-w-4xl overflow-hidden">
            <div className="flex flex-col gap-3 border-b border-slate-200 bg-slate-50/80 p-5 md:flex-row md:items-start md:justify-between">
              <div>
                <p className="text-xs font-semibold text-cyan-700">阶段产出详情</p>
                <h3 className="mt-1 text-xl font-black text-slate-950">{selectedOutput.title}</h3>
                <p className="mt-2 text-xs text-slate-500">{selectedOutput.meta}</p>
              </div>
              <ModalCloseButton onClick={() => setSelectedOutput(null)} />
            </div>
            <div className="max-h-[64vh] overflow-auto p-6">
              <MarkdownDocument content={selectedOutput.content} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function InterventionMarkdownTimeline({ intervention }: { intervention: InterventionSession }) {
  const messages = intervention.messages ?? [];
  const events = intervention.events ?? [];
  const outputs = intervention.outputs ?? [];
  const hasContent = messages.length || events.length || outputs.length;

  if (!hasContent) {
    return <p className="text-sm text-slate-400">暂无会话内容，添加指令或运行延续分析后会显示。</p>;
  }

  return (
    <div className="space-y-3">
      {messages.map(message => (
        <article key={message.id} className="rounded-2xl border border-emerald-100 bg-white/85 p-3">
          <p className="mb-2 text-xs font-semibold text-emerald-700">{message.author}</p>
          <MarkdownDocument content={message.content} />
        </article>
      ))}
      {events.map(event => (
        <article key={`e-${event.id}`} className="rounded-2xl border border-cyan-100 bg-white/85 p-3">
          <p className="mb-2 text-xs font-semibold text-cyan-700">{formatEventTypeLabel(event.event_type)}</p>
          <MarkdownDocument content={event.message} />
        </article>
      ))}
      {outputs.map(output => (
        <article key={`o-${output.id}`} className="rounded-2xl border border-slate-200 bg-white p-4">
          <p className="mb-2 text-xs font-semibold text-slate-500">{formatAgentName(output.target_agent_name)} 延续输出</p>
          <MarkdownDocument content={output.content} />
        </article>
      ))}
    </div>
  );
}

function App() {
  const [themeMode, setThemeMode] = useState<ThemeMode>(getInitialThemeMode);
  const [token, setToken] = useState(localStorage.getItem('ta_token'));
  const [email, setEmail] = useState(initialEmail);
  const [password, setPassword] = useState(initialPassword);
  const [params, setParams] = useState(defaultParams);
  const [tickerInputValue, setTickerInputValue] = useState(defaultParams.ticker);
  const [history, setHistory] = useState<AnalysisTask[]>([]);
  const [selected, setSelected] = useState<AnalysisTask | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [memories, setMemories] = useState<AgentMemory[]>([]);
  const [selectedMemory, setSelectedMemory] = useState<AgentMemory | null>(null);
  const [memoryQuery, setMemoryQuery] = useState('');
  const [memoryFilterTab, setMemoryFilterTab] = useState<MemoryFilterTab>('ticker');
  const [memoryTickerFilter, setMemoryTickerFilter] = useState('');
  const [memoryDateFilter, setMemoryDateFilter] = useState('');
  const [memoryAgentFilter, setMemoryAgentFilter] = useState('');
  const [historyTickerFilter, setHistoryTickerFilter] = useState('');
  const [historyDateFilter, setHistoryDateFilter] = useState('');
  const [interventions, setInterventions] = useState<InterventionSession[]>([]);
  const [selectedIntervention, setSelectedIntervention] = useState<InterventionSession | null>(null);
  const [interventionAgent, setInterventionAgent] = useState('Market Analyst');
  const [guidance, setGuidance] = useState('');
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<number | null>(null);
  const selectedWorkspace = workspaces.find(workspace => workspace.id === selectedWorkspaceId);
  const [workspaceName, setWorkspaceName] = useState('研究工作区');
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
  const [legalHolds, setLegalHolds] = useState<LegalHold[]>([]);
  const [legalHoldResourceId, setLegalHoldResourceId] = useState('');
  const [legalHoldReason, setLegalHoldReason] = useState('调查保全');
  const [provisionEmail, setProvisionEmail] = useState('');
  const [provisionRole, setProvisionRole] = useState<Exclude<WorkspaceRole, 'owner'>>('viewer');
  const [provisioningEvents, setProvisioningEvents] = useState<ProvisioningEvent[]>([]);
  const [idpHealth, setIdpHealth] = useState<IdpHealth | null>(null);
  const [runtimeHealth, setRuntimeHealth] = useState<RuntimeHealth | null>(null);
  const [scheduleForm, setScheduleForm] = useState(defaultScheduleForm);
  const [editingScheduleId, setEditingScheduleId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activePage, setActivePage] = useState<WorkspacePageId>('analysis');
  const [selectedReportSectionName, setSelectedReportSectionName] = useState<string | null>(null);
  const [streamingTaskId, setStreamingTaskId] = useState<number | null>(null);
  const [tickerDropdownOpen, setTickerDropdownOpen] = useState(false);
  const [stockSearchSuggestions, setStockSearchSuggestions] = useState<StockSearchSuggestion[]>([]);
  const [stockSearchLoading, setStockSearchLoading] = useState(false);
  const selectedTaskIdRef = useRef<number | null>(null);
  const tickerTouchedRef = useRef(false);
  const stockNameCacheRef = useRef<Record<string, string>>({});
  const suppressAutoResumeRef = useRef(false);
  const pendingWorkspaceScrollRef = useRef(false);

  const authenticated = Boolean(token);

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode;
    document.documentElement.style.colorScheme = themeMode;
    localStorage.setItem(THEME_STORAGE_KEY, themeMode);
  }, [themeMode]);

  function toggleThemeMode() {
    setThemeMode(current => (current === 'dark' ? 'light' : 'dark'));
  }
  const activePageMeta = getWorkspacePageMeta(activePage) ?? workspacePages[0];
  const filteredHistory = useMemo(
    () => filterAnalysisHistory(history, { ticker: historyTickerFilter, analysisDate: historyDateFilter }),
    [history, historyTickerFilter, historyDateFilter]
  );
  const recentAnalyzedTickers = useMemo(() => getRecentAnalyzedTickers(history), [history]);
  const tickerSuggestions = useMemo(
    () => filterRecentTickerSuggestions(recentAnalyzedTickers, params.ticker),
    [recentAnalyzedTickers, params.ticker]
  );
  const stockSearchQuery = tickerInputValue.trim();
  const memoryFilterOptions = useMemo(() => getMemoryFilterOptions(memories), [memories]);
  const visibleMemories = useMemo(
    () => filterMemoriesForView(memories, { ticker: memoryTickerFilter, analysisDate: memoryDateFilter, agentName: memoryAgentFilter }),
    [memories, memoryTickerFilter, memoryDateFilter, memoryAgentFilter]
  );
  const groupedMemories = useMemo(() => groupMemoriesByTickerDateAgent(visibleMemories), [visibleMemories]);
  const selectedReportSection = useMemo(
    () => getSelectedReportSection(selected, selectedReportSectionName),
    [selected, selectedReportSectionName]
  );
  const showProductionSafetyWarning = shouldShowProductionSafetyWarning(import.meta.env.VITE_TRADINGAGENTS_WEB_ENV, import.meta.env.VITE_TRADINGAGENTS_API);
  const staleAnalysisWarning = useMemo(() => (selected ? buildStaleAnalysisWarning(selected) : null), [selected]);
  const activeMemoryFilterMeta = memoryFilterTabs.find(tab => tab.id === memoryFilterTab) ?? memoryFilterTabs[0];
  const activeMemoryFilterValue = memoryFilterTab === 'ticker' ? memoryTickerFilter : memoryFilterTab === 'date' ? memoryDateFilter : memoryAgentFilter;
  const activeMemoryFilterChoices = memoryFilterTab === 'ticker'
    ? memoryFilterOptions.tickers.map(value => ({ value, label: value }))
    : memoryFilterTab === 'date'
      ? memoryFilterOptions.dates.map(value => ({ value, label: value }))
      : memoryFilterOptions.agents.map(agent => ({ value: agent.rawName, label: agent.label }));
  const activeMemoryFilterLabels = [
    memoryTickerFilter ? `股票：${memoryTickerFilter}` : null,
    memoryDateFilter ? `日期：${memoryDateFilter}` : null,
    memoryAgentFilter ? `Agent：${formatAgentName(memoryAgentFilter)}` : null
  ].filter(Boolean);

  useEffect(() => {
    void api.oidcStatus().then(setIdentityStatus).catch(() => setIdentityStatus(null));
  }, []);

  useEffect(() => {
    function handleAuthExpired() {
      clearAuthenticatedSession('登录已过期，请重新登录。');
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
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
    if (!token || !stockSearchQuery) {
      setStockSearchSuggestions([]);
      setStockSearchLoading(false);
      return;
    }
    let active = true;
    setStockSearchLoading(true);
    const timer = window.setTimeout(() => {
      api.searchStocks(token, stockSearchQuery)
        .then(result => {
          if (active) setStockSearchSuggestions(result.items);
        })
        .catch(() => {
          if (active) setStockSearchSuggestions([]);
        })
        .finally(() => {
          if (active) setStockSearchLoading(false);
        });
    }, 180);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [stockSearchQuery, token]);

  useEffect(() => {
    if (!token || !history.length) return;
    const tickers = Array.from(new Set(history
      .filter(item => !(item.ticker_name ?? item.parameters?.ticker_name))
      .map(item => (item.ticker ?? item.parameters?.ticker ?? '').trim().toUpperCase())
      .filter(ticker => ticker && getAshareTickerSearchCode(ticker) && stockNameCacheRef.current[ticker] === undefined)
    )).slice(0, 8);
    if (!tickers.length) return;
    let active = true;
    Promise.all(tickers.map(async ticker => {
      try {
        const code = getAshareTickerSearchCode(ticker);
        if (!code) return [ticker, ''] as const;
        const result = await api.searchStocks(token, code);
        const match = result.items.find(item => item.ticker.toUpperCase() === ticker) ?? result.items[0];
        return [ticker, match?.name ?? ''] as const;
      } catch {
        return [ticker, ''] as const;
      }
    })).then(entries => {
      if (!active) return;
      const names = Object.fromEntries(entries);
      for (const [ticker, name] of entries) stockNameCacheRef.current[ticker] = name;
      if (!Object.values(names).some(Boolean)) return;
      const applyName = (task: AnalysisTask): AnalysisTask => {
        const ticker = (task.ticker ?? task.parameters?.ticker ?? '').trim().toUpperCase();
        const name = names[ticker];
        if (!name || task.ticker_name || task.parameters?.ticker_name) return task;
        return { ...task, ticker_name: name, parameters: task.parameters ? { ...task.parameters, ticker_name: name } : task.parameters };
      };
      setHistory(current => current.map(applyName));
      setSelected(current => current ? applyName(current) : current);
    });
    return () => {
      active = false;
    };
  }, [history, token]);

  useEffect(() => {
    if (token && selectedWorkspaceId) {
      void refreshHistory(token);
      void refreshSchedules(token);
      void refreshMemories(token);
      void refreshInterventions(token);
      void refreshAuditConsole();
      void refreshEnterpriseCompliance();
    }
  }, [selectedWorkspaceId]);

  useEffect(() => {
    setSelectedReportSectionName(getDefaultReportSectionName(selected));
  }, [selected?.id, selected?.report_sections]);

  useEffect(() => {
    selectedTaskIdRef.current = selected?.id ?? null;
  }, [selected?.id]);

  useEffect(() => {
    const latestTicker = getDefaultTickerFromHistory(history, '');
    if (!latestTicker || tickerTouchedRef.current) return;
    setParams(current => (current.ticker === latestTicker ? current : { ...current, ticker: latestTicker }));
    setTickerInputValue(latestTicker);
  }, [history]);

  useEffect(() => {
    if (!token || selected) return;
    if (suppressAutoResumeRef.current) {
      suppressAutoResumeRef.current = false;
      return;
    }
    const stored = Number(localStorage.getItem(ACTIVE_ANALYSIS_TASK_KEY));
    const storedTaskId = Number.isFinite(stored) ? stored : null;
    const recoverableTaskId = getRecoverableAnalysisTaskId(history, null, storedTaskId);
    if (recoverableTaskId) void resumeAnalysisTask(recoverableTaskId);
  }, [token, history, selected?.id]);

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

  async function viewMemory(memoryId: number) {
    if (!token) return;
    setSelectedMemory(await api.getMemory(token, memoryId));
  }

  function selectActiveMemoryFilter(value: string) {
    if (memoryFilterTab === 'ticker') setMemoryTickerFilter(value);
    if (memoryFilterTab === 'date') setMemoryDateFilter(value);
    if (memoryFilterTab === 'agent') setMemoryAgentFilter(value);
  }

  function clearActiveMemoryFilter() {
    selectActiveMemoryFilter('');
  }

  function clearAllMemoryFilters() {
    setMemoryTickerFilter('');
    setMemoryDateFilter('');
    setMemoryAgentFilter('');
  }

  function updateTickerInput(value: string) {
    tickerTouchedRef.current = true;
    const next = buildTickerInputUpdate(value);
    setTickerInputValue(next.inputValue);
    setParams(current => ({ ...current, ticker: next.payloadTicker, ticker_name: null }));
    setTickerDropdownOpen(true);
  }

  function chooseTickerSuggestion(ticker: string) {
    if (!ticker) return;
    tickerTouchedRef.current = true;
    setTickerInputValue(ticker);
    setParams(current => ({ ...current, ticker, ticker_name: null }));
    setTickerDropdownOpen(false);
  }

  function chooseStockSearchSuggestion(suggestion: StockSearchSuggestion) {
    tickerTouchedRef.current = true;
    setTickerInputValue(suggestion.ticker);
    setParams(current => ({ ...current, ticker: suggestion.ticker, ticker_name: suggestion.name }));
    setTickerDropdownOpen(false);
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
    else setError('当前未配置企业 SSO 登录。');
  }

  function rememberActiveAnalysisTask(task: AnalysisTask) {
    if (isAnalysisInProgress(task.status)) {
      localStorage.setItem(ACTIVE_ANALYSIS_TASK_KEY, String(task.id));
      return;
    }
    if (localStorage.getItem(ACTIVE_ANALYSIS_TASK_KEY) === String(task.id)) {
      localStorage.removeItem(ACTIVE_ANALYSIS_TASK_KEY);
    }
  }

  function clearAnalysisOutputForNewRun() {
    suppressAutoResumeRef.current = true;
    selectedTaskIdRef.current = null;
    localStorage.removeItem(ACTIVE_ANALYSIS_TASK_KEY);
    setSelected(null);
    setEvents([]);
    setSelectedReportSectionName(null);
  }

  async function streamAndFinalizeTask(taskId: number) {
    if (!token || streamingTaskId === taskId) return;
    setStreamingTaskId(taskId);
    try {
      await streamTaskEvents(token, taskId, event => {
        if (selectedTaskIdRef.current !== taskId) return;
        setEvents(current => [...current.filter(item => item.sequence !== event.sequence), event].sort((a, b) => a.sequence - b.sequence));
        setSelected(current => current && current.id === taskId ? {
          ...current,
          status: deriveAnalysisStatusFromEvent(current.status, event),
          last_event_at: event.created_at,
          seconds_since_last_event: 0,
          stale: false
        } : current);
      });
      const detail = await api.getAnalysis(token, taskId);
      rememberActiveAnalysisTask(detail);
      if (selectedTaskIdRef.current === taskId) {
        setSelected(detail);
        setEvents(detail.events ?? []);
      }
      await refreshHistory(token);
      await refreshMemories(token);
    } finally {
      setStreamingTaskId(current => (current === taskId ? null : current));
    }
  }

  async function resumeAnalysisTask(taskId: number) {
    const detail = await loadTask(taskId);
    if (detail && isAnalysisInProgress(detail.status)) {
      await streamAndFinalizeTask(taskId);
    }
  }

  async function launch() {
    if (!token) return;
    setError(null);
    clearAnalysisOutputForNewRun();
    try {
      const task = await api.createAnalysis(token, { ...params, workspace_id: selectedWorkspaceId });
      rememberActiveAnalysisTask(task);
      selectedTaskIdRef.current = task.id;
      setSelected(task);
      setEvents([]);
      await streamAndFinalizeTask(task.id);
    } catch (err) {
      setError(String(err));
    }
  }

  async function loadTask(id: number): Promise<AnalysisTask | null> {
    if (!token) return null;
    const detail = await api.getAnalysis(token, id);
    rememberActiveAnalysisTask(detail);
    selectedTaskIdRef.current = detail.id;
    setSelected(detail);
    setEvents(detail.events ?? []);
    return detail;
  }

  async function loadTaskParameters(id: number) {
    if (!token) return;
    const detail = await api.getAnalysis(token, id);
    const draft = buildReusableAnalysisParamsFromTask(detail);
    clearAnalysisOutputForNewRun();
    tickerTouchedRef.current = true;
    setTickerInputValue(draft.tickerInputValue);
    setParams(draft.params);
  }

  async function rerunSelected(overrides: Partial<AnalysisParams> = {}) {
    if (!token || !selected) return;
    const sourceTaskId = selected.id;
    clearAnalysisOutputForNewRun();
    const task = await api.rerun(token, sourceTaskId, overrides);
    rememberActiveAnalysisTask(task);
    await resumeAnalysisTask(task.id);
    await refreshHistory(token);
  }

  async function cancelSelectedAnalysis() {
    if (!token || !selected) return;
    setError(null);
    try {
      const task = await api.cancelAnalysis(token, selected.id);
      rememberActiveAnalysisTask(task);
      setSelected(task);
      setEvents(task.events ?? []);
      await refreshHistory(token);
    } catch (err) {
      setError(String(err));
    }
  }

  async function pauseSelectedAnalysis() {
    if (!token || !selected) return;
    setError(null);
    try {
      const task = await api.pauseAnalysis(token, selected.id);
      rememberActiveAnalysisTask(task);
      setSelected(task);
      setEvents(task.events ?? []);
      await refreshHistory(token);
    } catch (err) {
      setError(String(err));
    }
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
    if (execution.analysis_task_id) await resumeAnalysisTask(execution.analysis_task_id);
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

  async function refreshEnterpriseCompliance() {
    if (!token || !selectedWorkspaceId) return;
    const [holds, events] = await Promise.all([
      api.listLegalHolds(token, selectedWorkspaceId),
      api.listProvisioningEvents(token, selectedWorkspaceId)
    ]);
    setLegalHolds(holds.items);
    setProvisioningEvents(events.items);
  }

  async function previewRetention() {
    if (!token || !selectedWorkspaceId) return;
    const result = await api.retentionPreview(token, buildRetentionPolicy(selectedWorkspaceId, retentionResourceType, retentionCutoff, false));
    setRetentionResult(result);
    await refreshAuditConsole();
    await refreshEnterpriseCompliance();
  }

  async function applyRetention() {
    if (!token || !selectedWorkspaceId) return;
    const explicit = retentionResourceType === 'audit_logs' || retentionResourceType === 'usage_ledger';
    const result = await api.retentionApply(token, buildRetentionPolicy(selectedWorkspaceId, retentionResourceType, retentionCutoff, explicit));
    setRetentionResult(result);
    await refreshAuditConsole();
    await refreshEnterpriseCompliance();
  }

  async function createLegalHold() {
    if (!token || !selectedWorkspaceId || !legalHoldReason.trim()) return;
    await api.createLegalHold(token, selectedWorkspaceId, retentionResourceType, legalHoldResourceId.trim() || null, legalHoldReason.trim());
    setLegalHoldResourceId('');
    await refreshEnterpriseCompliance();
  }

  async function releaseLegalHold(hold: LegalHold) {
    if (!token || !selectedWorkspaceId) return;
    await api.releaseLegalHold(token, selectedWorkspaceId, hold.id, '从管理控制台释放');
    await refreshEnterpriseCompliance();
  }

  async function provisionWorkspaceUser() {
    if (!token || !selectedWorkspaceId || !provisionEmail.trim()) return;
    await api.provisionUser(token, selectedWorkspaceId, provisionEmail.trim(), provisionRole);
    setProvisionEmail('');
    await refreshWorkspaces(token);
    await refreshEnterpriseCompliance();
  }

  async function deactivateProvisionedUser(userId: number) {
    if (!token || !selectedWorkspaceId) return;
    await api.updateProvisionedUser(token, selectedWorkspaceId, userId, { active: false });
    await refreshWorkspaces(token);
    await refreshEnterpriseCompliance();
  }

  async function checkIdpHealth() {
    if (!token || !selectedWorkspaceId) return;
    setIdpHealth(await api.idpHealth(token, selectedWorkspaceId));
    await refreshAuditConsole();
  }

  async function exportCompliance() {
    if (!token || !selectedWorkspaceId) return;
    const data = await api.complianceExport(token, selectedWorkspaceId);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = complianceExportFilename(selectedWorkspaceId, data.exported_at);
    link.click();
    URL.revokeObjectURL(url);
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

  function clearAuthenticatedSession(message?: string) {
    localStorage.removeItem('ta_token');
    setToken(null);
    setSelected(null);
    setEvents([]);
    setHistory([]);
    setSchedules([]);
    setMemories([]);
    setInterventions([]);
    setSelectedIntervention(null);
    setWorkspaces([]);
    setSelectedWorkspaceId(null);
    setRuntimeHealth(null);
    setError(message ?? null);
  }

  function logout() {
    if (token) void api.logout(token).catch(() => undefined);
    clearAuthenticatedSession();
  }

  function scrollToLoginAccess() {
    const loginSection = document.getElementById('login-access');
    if (!loginSection) return;
    window.scrollTo({ top: Math.max(loginSection.offsetTop - 76, 0), behavior: 'smooth' });
  }

  function scrollToWorkspacePage() {
    const workspacePage = document.getElementById('workspace-active-page');
    if (!workspacePage) return;
    const pageTop = workspacePage.getBoundingClientRect().top + window.scrollY;
    window.scrollTo({ top: Math.max(pageTop - 96, 0), behavior: 'smooth' });
  }

  function selectWorkspacePage(pageId: WorkspacePageId) {
    pendingWorkspaceScrollRef.current = true;
    setActivePage(pageId);
    if (pageId === activePage) {
      window.requestAnimationFrame(() => {
        scrollToWorkspacePage();
        pendingWorkspaceScrollRef.current = false;
      });
    }
  }

  useEffect(() => {
    if (!authenticated || !pendingWorkspaceScrollRef.current) return;
    const frame = window.requestAnimationFrame(() => {
      scrollToWorkspacePage();
      pendingWorkspaceScrollRef.current = false;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [activePage, authenticated]);

  const latestAnalysis = history[0] ?? selected;
  const latestAnalysisTicker = latestAnalysis ? buildAnalysisTickerLabel(latestAnalysis) : '暂无历史分析';
  const latestAnalysisDate = latestAnalysis?.analysis_date ?? latestAnalysis?.parameters?.analysis_date ?? '暂无';
  const latestAnalysisStatus = latestAnalysis ? formatStatusLabel(latestAnalysis.status) : '暂无历史结果';
  const latestAnalysisDecision = latestAnalysis ? formatDecisionLabel(latestAnalysis.final_decision?.decision ?? latestAnalysis.decision) : '暂无结论';
  const latestAnalysisSteps = latestAnalysis
    ? ['最近一次历史任务', '已保存的 Agent 输出', '最终交易结论快照', '进入历史页查看完整报告']
    : ['暂无历史分析', '下方股票分析页可发起任务', '完成后自动沉淀到历史记录', '这里会展示最近一次旧结果'];

  if (!authenticated) {
    return (
      <main className="theme-shell min-h-screen text-primary">
        <header className="od-topbar">
          <OpenDesignBrand />
          <nav className="od-nav" aria-label="页面导航">
            <a href="#login-workbench">工作台</a>
            <a href="#login-flow">Agent Flow</a>
            <a href="#login-access">登录</a>
          </nav>
          <div className="justify-self-end">
            <ThemeToggle themeMode={themeMode} onToggle={toggleThemeMode} />
          </div>
        </header>
        <section id="login-workbench" className="px-5 py-12 lg:px-12 lg:py-16">
          <div className="od-hero-grid mx-auto max-w-[1240px]">
            <div>
              <div className="od-issue-line">Open Design Landing / financial agent platform</div>
              <h1 className="od-display max-w-4xl text-[clamp(3.25rem,8.2vw,7.25rem)] font-semibold leading-[0.94]">把市场噪声交给一组会辩论的 Agent。</h1>
              <p className="mt-7 max-w-2xl text-lg leading-8 text-primary md:text-2xl">
                TradingAgents 将股票研究、实时 Agent 输出、智能体记忆、定时任务、人工介入和合规治理组织成一个中文金融工作台。
              </p>
              <div className="od-hero-actions">
                <a className="od-link-button is-solid" href="#login-access">进入工作台</a>
                <a className="od-link-button" href="#login-flow">查看 Agent 流程</a>
              </div>
              <div className="mt-8 grid max-w-xl gap-3 sm:grid-cols-3">
                <MiniStat label="运行模式" value={runtimeHealth?.runtime_mode ?? 'local'} />
                <MiniStat label="数据存储" value={runtimeHealth?.storage_backend ?? 'SQLite'} />
                <MiniStat label="协调后端" value={runtimeHealth?.coordination_backend ?? 'memory'} />
              </div>
            </div>
            <LandingAnalysisPreview
              mode="SPY / live run"
              ticker="SPY"
              analysisDate={defaultParams.analysis_date}
              memoryCount={7}
              onLaunch={scrollToLoginAccess}
            />
          </div>
        </section>
        <div id="login-flow" className="od-marquee" aria-hidden="true">
          <span>Analysis · Agent Debate · Memory · Schedule · HITL · Governance · Compliance · Analysis · Agent Debate · Memory · Schedule · HITL · Governance · Compliance · </span>
        </div>
        <section id="login-access" className="px-5 py-12 lg:px-12 lg:py-16">
          <div className="mx-auto grid max-w-[1240px] gap-8 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="od-section-heading lg:block">
              <div className="od-section-number">Access</div>
              <h2 className="od-display mt-5 text-5xl font-semibold leading-none md:text-7xl">进入研究工作台。</h2>
              <p className="mt-6 max-w-lg text-base leading-7 text-muted md:text-lg">登录后会进入真实工作区：发起分析、追踪 Agent 流、复用记忆，并访问治理与合规控制台。</p>
            </div>
            <Card className="p-8">
              <CardTitle className="od-display text-3xl font-semibold">登录研究工作台</CardTitle>
              <p className="mb-6 text-sm text-muted">请输入管理员或工作区成员账号。公网环境已关闭开放注册。</p>
              <form className="space-y-4" onSubmit={handleLogin}>
                <Field label="邮箱账号">
                  <input className={inputClass} placeholder="admin@example.com" value={email} onChange={e => setEmail(e.target.value)} />
                </Field>
                <Field label="登录密码">
                  <input className={inputClass} type="password" placeholder="请输入密码" value={password} onChange={e => setPassword(e.target.value)} />
                </Field>
                <Button className="w-full py-3 text-base">登录平台</Button>
                {identityStatus?.oidc_enabled && <Button type="button" className="w-full bg-primary text-primary-foreground hover:bg-primary/85" onClick={startOidcLogin}>使用企业 SSO 登录</Button>}
                {error && <p className="rounded-card border border-negative bg-negative-soft p-3 text-sm text-negative">{error}</p>}
              </form>
            </Card>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="theme-shell min-h-screen text-primary">
      <header className="od-topbar od-workspace-topbar">
        <OpenDesignBrand />
        <nav className="od-nav" aria-label="工作区导航">
          {workspacePages.map(page => (
            <button
              key={page.id}
              type="button"
              onClick={() => selectWorkspacePage(page.id)}
              aria-current={activePage === page.id ? 'page' : undefined}
            >
              {page.title}
            </button>
          ))}
        </nav>
        <div className="od-top-actions">
          <ThemeToggle themeMode={themeMode} onToggle={toggleThemeMode} />
          <Button onClick={exportAccount}>导出账号</Button>
          <Button onClick={logout} className="bg-surface text-primary hover:bg-muted"><LogOut className="mr-2 inline" size={16}/>退出</Button>
        </div>
      </header>

      <section className="px-5 py-10 lg:px-12 lg:py-14">
        <div className="od-hero-grid mx-auto max-w-[1240px]">
          <div>
            <div className="od-issue-line">Open Design Landing / live workstation</div>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <span className="rounded-pill border border-accent bg-accent-soft px-3 py-1 text-xs font-semibold text-accent">中文金融工作台</span>
              <StatusBadge status={runtimeHealth?.status ?? 'ok'} />
              <span className="rounded-pill border border-subtle bg-surface px-3 py-1 text-xs text-muted">{runtimeHealth?.storage_backend ?? 'sqlite'} / {runtimeHealth?.coordination_backend ?? 'memory'}</span>
            </div>
            <h1 className="od-display max-w-5xl text-[clamp(3rem,7.4vw,6.75rem)] font-semibold leading-[0.94]">把市场噪声交给一组会辩论的 Agent。</h1>
            <p className="mt-7 max-w-2xl text-lg leading-8 text-primary md:text-2xl">发起股票研究、追踪每个 Agent 的实时输出，沉淀记忆并支持人工介入与再分析。</p>
            <div className="mt-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard label="历史分析" value={history.length} detail="当前工作区记录" />
              <MetricCard label="智能体记忆" value={memories.length} detail="可附加到新分析" />
              <MetricCard label="定时任务" value={schedules.length} detail="自动研究计划" />
              <MetricCard label="介入会话" value={interventions.length} detail="人工延续分析" />
            </div>
          </div>
          <LandingAnalysisPreview
            title="Latest analysis"
            briefLabel="Recent result"
            mode={latestAnalysis ? `${latestAnalysisTicker} / ${latestAnalysisStatus}` : 'history / empty'}
            ticker={latestAnalysisTicker}
            analysisDate={latestAnalysisDate}
            memoryCount={memories.length}
            statusText={latestAnalysis ? `最近结果：${latestAnalysisStatus}` : '暂无旧分析结果'}
            decisionLabel={latestAnalysisDecision}
            steps={latestAnalysisSteps}
          />
        </div>
      </section>

      <div className="od-marquee" aria-hidden="true">
        <span>Analysis · Agent Debate · Memory · Schedule · HITL · Governance · Compliance · Analysis · Agent Debate · Memory · Schedule · HITL · Governance · Compliance · </span>
      </div>

      <div className="mx-auto max-w-[1500px] space-y-6 px-5 py-8 lg:px-8">

        {showProductionSafetyWarning && <Notice tone="amber">生产安全提醒：公网正式使用前请配置 production 环境、精确 CORS、强密钥、HTTPS、备份、审计复核与限流策略。</Notice>}
        {shouldShowClusterRuntimeWarning(runtimeHealth) && <Notice tone="amber">集群运行警告：production-cluster 模式需要同时启用 Postgres 存储与 Redis 协调。</Notice>}
        {error && <Notice tone="red">{error}</Notice>}

        <section className="rounded-card border border-strong bg-surface p-3 shadow-panel">
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-7">
            {workspacePages.map(page => {
              const active = activePage === page.id;
              return (
                <button
                  key={page.id}
                  type="button"
                  onClick={() => selectWorkspacePage(page.id)}
                  className={`rounded-card border p-4 text-left transition ${active ? 'border-strong bg-canvas shadow-panel' : 'border-transparent bg-surface hover:border-subtle hover:bg-muted'}`}
                  aria-current={active ? 'page' : undefined}
                >
                  <span className={`rounded-pill border px-2 py-0.5 text-[11px] font-semibold ${active ? 'border-accent text-accent' : 'border-subtle text-muted'}`}>{page.badge}</span>
                  <p className="mt-2 font-bold text-primary">{page.title}</p>
                  <p className="mt-1 text-xs leading-5 text-muted">{page.description}</p>
                </button>
              );
            })}
          </div>
        </section>

        <section id="workspace-active-page" className="rounded-card border border-strong bg-surface/90 p-5 shadow-float backdrop-blur-xl">
          <div className="od-section-heading od-workspace-section-heading">
            <div>
              <p className="od-section-number">{activePageMeta.badge}</p>
            </div>
            <div>
              <h2 className="od-workspace-section-title">{activePageMeta.title}</h2>
              <p className="od-section-copy od-workspace-section-copy">{activePageMeta.description}</p>
              {selectedWorkspace && <span className="mt-4 inline-flex rounded-pill border border-subtle bg-surface px-3 py-1 text-xs text-muted">工作区：{selectedWorkspace.name} · {formatWorkspaceRoleLabel(selectedWorkspace.role)}</span>}
            </div>
          </div>

          {activePage === 'analysis' && (
            <div className="space-y-6">
              <div className="grid gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">
                <Card className="border-cyan-100 bg-white/90">
	                <CardTitle><PlayCircle className="mr-2 inline text-cyan-600"/>发起股票分析</CardTitle>
	                <div className="space-y-4">
	                  <div className="grid grid-cols-2 gap-3">
	                    <Field label="股票代码" hint="输入 A 股名称或代码会模糊匹配；选择后自动填入标准股票代码">
	                      <div className="relative space-y-2">
	                        <input
	                          className={inputClass}
	                          placeholder="例如 宁德时代、骏亚科技、600330"
	                          value={tickerInputValue}
	                          aria-haspopup="listbox"
	                          aria-expanded={tickerDropdownOpen}
	                          onFocus={() => setTickerDropdownOpen(true)}
	                          onClick={() => setTickerDropdownOpen(true)}
	                          onBlur={() => window.setTimeout(() => setTickerDropdownOpen(false), 120)}
	                          onChange={e => updateTickerInput(e.target.value)}
	                        />
	                        {shouldShowTickerDropdown({
	                          open: tickerDropdownOpen,
	                          query: stockSearchQuery,
	                          recentCount: recentAnalyzedTickers.length,
	                          suggestionCount: stockSearchSuggestions.length,
	                          loading: stockSearchLoading
	                        }) ? (
	                          <div
	                            className="absolute z-40 mt-1 w-full overflow-hidden rounded-2xl border border-cyan-100 bg-white shadow-2xl shadow-slate-200/90"
	                            role="listbox"
	                            aria-label="股票搜索与最近分析下拉选择"
	                            onMouseDown={event => event.preventDefault()}
	                          >
	                            <div className="flex items-center justify-between gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2">
	                              <span className="text-xs font-semibold text-slate-500">{params.ticker.trim() ? 'A 股搜索结果' : '最近分析股票'}</span>
	                              <span className="text-xs text-slate-400">{stockSearchLoading ? '搜索中…' : `${stockSearchSuggestions.length} 个匹配`}</span>
	                            </div>
	                            {stockSearchSuggestions.length ? (
	                              <div className="max-h-56 overflow-auto p-2">
	                                {stockSearchSuggestions.map(suggestion => (
	                                  <button
	                                    key={suggestion.ticker}
	                                    type="button"
	                                    role="option"
	                                    aria-selected={params.ticker.toUpperCase() === suggestion.ticker}
	                                    className={`mb-1 flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-sm font-semibold transition last:mb-0 ${params.ticker.toUpperCase() === suggestion.ticker ? 'bg-cyan-50 text-cyan-700' : 'text-slate-700 hover:bg-cyan-50 hover:text-cyan-700'}`}
	                                    onClick={() => chooseStockSearchSuggestion(suggestion)}
	                                  >
	                                    <span className="min-w-0">
	                                      <span className="block truncate">{formatStockSearchSuggestionLabel(suggestion)}</span>
	                                      {suggestion.pinyin && <span className="block text-[11px] font-normal text-slate-400">{suggestion.pinyin}</span>}
	                                    </span>
	                                    <span className="shrink-0 text-xs font-normal text-slate-400">A 股</span>
	                                  </button>
	                                ))}
	                              </div>
	                            ) : tickerSuggestions.length ? (
	                              <div className="max-h-56 overflow-auto p-2">
	                                {tickerSuggestions.map(ticker => (
	                                  <button
	                                    key={ticker}
	                                    type="button"
	                                    role="option"
	                                    aria-selected={params.ticker.toUpperCase() === ticker}
	                                    className={`mb-1 flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm font-semibold transition last:mb-0 ${params.ticker.toUpperCase() === ticker ? 'bg-cyan-50 text-cyan-700' : 'text-slate-700 hover:bg-cyan-50 hover:text-cyan-700'}`}
	                                    onClick={() => chooseTickerSuggestion(ticker)}
	                                  >
	                                    <span>{ticker}</span>
	                                    <span className="text-xs font-normal text-slate-400">最近分析</span>
	                                  </button>
	                                ))}
	                              </div>
	                            ) : (
	                              <p className="p-3 text-xs text-slate-400">{stockSearchLoading ? '正在查询 A 股代码…' : '没有匹配的 A 股或最近股票，仍可直接输入标准股票代码。'}</p>
	                            )}
	                          </div>
	                        ) : null}
	                      </div>
	                    </Field>
	                    <Field label="分析日期"><input className={inputClass} type="date" value={params.analysis_date} onChange={e => setParams({...params, analysis_date: e.target.value})} /></Field>
	                  </div>
                  <Field label="分析师 Agent" hint="下拉多选，默认全选；至少保留 1 个 Agent">
                    <AnalystMultiSelect selected={params.analysts} onChange={analysts => setParams({...params, analysts})} />
                  </Field>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="研究深度"><input className={inputClass} type="number" min="1" max="10" value={params.research_depth} onChange={e => setParams({...params, research_depth: Number(e.target.value)})} /></Field>
                    <Field label="LLM 提供方"><input className={inputClass} value={params.llm_provider} onChange={e => setParams({...params, llm_provider: e.target.value})} /></Field>
                  </div>
                  <Field label="思考深度" hint={thinkingDepthOptions.find(option => option.value === getThinkingDepth(params))?.hint}>
                    <select className={inputClass} value={getThinkingDepth(params)} onChange={e => setParams(applyThinkingDepth(params, e.target.value as ThinkingDepth))}>
                      {thinkingDepthOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </Field>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="快速模型"><input className={inputClass} value={params.quick_model} onChange={e => setParams({...params, quick_model: e.target.value})} /></Field>
                    <Field label="深度模型"><input className={inputClass} value={params.deep_model} onChange={e => setParams({...params, deep_model: e.target.value})} /></Field>
                  </div>
                  <Field label="输出语言"><input className={inputClass} value={params.output_language} onChange={e => setParams({...params, output_language: e.target.value})} /></Field>
                  <MemoryPicker title="附加记忆" memories={memories.slice(0, 6)} selectedIds={params.memory_ids ?? []} onToggle={memoryId => setParams({...params, memory_ids: toggleMemoryId(params.memory_ids, memoryId)})} />
                  <Button className="w-full py-3 text-base shadow-lg shadow-emerald-100/80" disabled={!canCreateWorkspaceResource(selectedWorkspace?.role)} onClick={launch}>启动分析</Button>
                </div>
                </Card>

                <Card className="min-h-[620px] border-cyan-100 bg-white/90">
                <CardTitle><Activity className="mr-2 inline text-cyan-600"/>实时进度与最终结论</CardTitle>
                {selected ? (
                  <div className="space-y-5">
                    <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50/90 p-4">
                      <div>
                        <p className="text-xs text-slate-400">分析任务</p>
                        <p className="text-xl font-black text-slate-950">#{selected.id} · {selected.parameters?.ticker ?? selected.ticker}</p>
                      </div>
                      <StatusBadge status={selected.status} />
                      <span className="rounded-full bg-cyan-400/10 px-3 py-1 text-sm text-cyan-700">{selected.analysis_date ?? selected.parameters?.analysis_date}</span>
                    </div>
                    <AgentProgressFlow task={selected} events={events} />
                    {staleAnalysisWarning && (
                      <Notice tone="amber">
                        <span>{staleAnalysisWarning}</span>
                        <span className="mt-3 flex flex-wrap gap-2">
                          <Button className="bg-amber-500 text-white hover:bg-amber-400" onClick={cancelSelectedAnalysis}>取消当前分析</Button>
                          <Button className="bg-white text-amber-700 ring-1 ring-amber-200 hover:bg-amber-50" onClick={() => rerunSelected({})}>按原参数重试</Button>
                        </span>
                      </Notice>
                    )}
                    <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                      <p className="text-xs text-emerald-700">最终决策</p>
                      <h3 className="mt-1 text-2xl font-black text-slate-950">{formatDecisionLabel(selected.final_decision?.decision ?? selected.decision ?? 'pending')}</h3>
                      <MarkdownDocument content={selected.final_decision?.rationale ?? '分析完成后会在这里展示决策理由。'} className="mt-2" />
                    </div>
                    {selected.attached_memories?.length ? <InfoBlock title="本次附加记忆">{selected.attached_memories.map(memory => <p key={memory.id} className="text-sm text-slate-600">{buildMemoryOptionLabel(memory)}</p>)}</InfoBlock> : null}
                    <InfoBlock title="人工介入">
                      <div className="flex flex-wrap gap-2">
                        <select className={inputClass} value={interventionAgent} onChange={e => setInterventionAgent(e.target.value)}><option>Market Analyst</option><option>News Analyst</option><option>Research Manager</option><option>Trader</option><option>Portfolio Manager</option></select>
                        <Button disabled={!canCreateWorkspaceResource(selectedWorkspace?.role)} onClick={createIntervention}>开启介入会话</Button>
                        <Button className="bg-slate-100 text-slate-900 hover:bg-slate-200" onClick={() => setActivePage('interventions')}>查看介入页</Button>
                      </div>
                      {selected.intervention_sessions?.map(session => <button key={session.id} className="mt-2 block text-left text-sm text-cyan-700 hover:text-cyan-700" onClick={() => { void loadIntervention(session.id); setActivePage('interventions'); }}>{buildInterventionLabel(session)}</button>)}
                    </InfoBlock>
                    <div className="flex flex-wrap gap-2">
                      <Button className="bg-slate-100 text-slate-900 hover:bg-slate-200" onClick={() => {
                        if (!selected) return;
                        setTickerInputValue(selected.parameters?.ticker ?? selected.ticker ?? defaultParams.ticker);
                        setParams(buildEditableParamsFromTask(selected));
                      }}>载入参数</Button>
                      <Button onClick={() => rerunSelected({})}><RotateCcw className="mr-2 inline" size={16}/>按原参数再分析</Button>
                      {isAnalysisInProgress(selected.status) && <Button className="bg-cyan-600 text-white hover:bg-cyan-500" onClick={pauseSelectedAnalysis}>暂停分析</Button>}
                      {isAnalysisInProgress(selected.status) && <Button className="bg-amber-500 text-white hover:bg-amber-400" onClick={cancelSelectedAnalysis}>取消分析</Button>}
                      <Button className="bg-red-500 text-white hover:bg-red-400" onClick={deleteSelectedAnalysis}>删除分析</Button>
                    </div>
                  </div>
                ) : <EmptyState title="尚未选择分析" description="启动一次股票分析，或从历史记录中选择已有任务。" />}
                </Card>
              </div>
              {selected ? (
                <Card className="border-cyan-100 bg-white/95">
                  <CardTitle><Database className="mr-2 inline text-cyan-600"/>分析报告文档</CardTitle>
                  {selected.report_sections?.length ? (
                    <div className="space-y-4">
                      <div className="flex flex-wrap gap-2">
                        {selected.report_sections.map(section => {
                          const active = selectedReportSection?.section_name === section.section_name;
                          return (
                            <button
                              key={section.section_name}
                              type="button"
                              onClick={() => setSelectedReportSectionName(section.section_name)}
                              className={`rounded-full border px-4 py-2 text-sm font-medium transition ${active ? 'border-cyan-300 bg-cyan-50 text-cyan-700' : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-cyan-200 hover:bg-cyan-50'}`}
                            >
                              {formatSectionName(section.section_name)}
                            </button>
                          );
                        })}
                      </div>
                      {selectedReportSection && (
                        <article className="rounded-3xl border border-slate-200 bg-slate-50/90 p-5">
                          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                            <h3 className="text-xl font-black text-slate-950">{formatSectionName(selectedReportSection.section_name)}</h3>
                            <span className="rounded-full bg-cyan-100 px-3 py-1 text-xs font-semibold text-cyan-700">默认优先展示最后生成文档</span>
                          </div>
                          <MarkdownDocument content={selectedReportSection.content} />
                        </article>
                      )}
                    </div>
                  ) : <EmptyState title="暂无报告文档" description="分析产生报告后，会在这里按文档逐个展示。" />}
                </Card>
              ) : null}
            </div>
          )}

          {activePage === 'history' && (
            <Card>
              <CardTitle><History className="mr-2 inline text-cyan-600"/>分析历史</CardTitle>
              <div className="mb-4 grid gap-3 md:grid-cols-[1fr_220px_auto]">
                <input className={inputClass} placeholder="按股票名称或代码筛选，例如 骏亚科技、AAPL 或 600330" value={historyTickerFilter} onChange={e => setHistoryTickerFilter(e.target.value.toUpperCase())} />
                <input className={inputClass} type="date" value={historyDateFilter} onChange={e => setHistoryDateFilter(e.target.value)} />
                <Button className="bg-slate-100 text-slate-900 hover:bg-slate-200" onClick={() => { setHistoryTickerFilter(''); setHistoryDateFilter(''); }}>清空筛选</Button>
              </div>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{filteredHistory.map(item => <button key={item.id} onClick={() => { void loadTask(item.id); setActivePage('analysis'); }} className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 text-left transition hover:-translate-y-0.5 hover:border-cyan-300 hover:bg-cyan-50"><div className="flex items-center justify-between gap-3"><strong className="text-slate-950">#{item.id} {buildAnalysisTickerLabel(item)}</strong><StatusBadge status={item.status} /></div><p className="mt-2 text-sm text-slate-400">{item.analysis_date ?? item.parameters?.analysis_date} · {formatDecisionLabel(item.decision ?? '暂无结论')}</p><p className="mt-3 rounded-xl bg-white/80 p-3 text-xs leading-5 text-slate-500">{buildAnalysisParameterSummary(item)}</p><span className="mt-3 inline-block rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-800" onClick={event => { event.stopPropagation(); void loadTaskParameters(item.id); setActivePage('analysis'); }}>载入/编辑参数</span></button>)}</div>
              {!filteredHistory.length && <EmptyState title="暂无匹配历史" description="调整股票代码或日期筛选，或先完成一次股票分析。" />}
            </Card>
          )}

          {activePage === 'memories' && (
            <Card>
              <CardTitle><Database className="mr-2 inline text-cyan-600"/>智能体记忆库</CardTitle>
              <div className="mb-4 flex gap-2"><input className={inputClass} placeholder="搜索记忆内容、股票或 Agent" value={memoryQuery} onChange={e => setMemoryQuery(e.target.value)} /><Button onClick={() => refreshMemories()}><Search className="mr-2 inline" size={16}/>搜索</Button></div>
              <div className="mb-5 rounded-3xl border border-slate-200 bg-white/80 p-4">
                <div className="flex flex-wrap gap-2">
                  {memoryFilterTabs.map(tab => {
                    const active = memoryFilterTab === tab.id;
                    return (
                      <button
                        key={tab.id}
                        type="button"
                        onClick={() => setMemoryFilterTab(tab.id)}
                        className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${active ? 'border-cyan-300 bg-cyan-50 text-cyan-700' : 'border-slate-200 bg-slate-50 text-slate-500 hover:border-cyan-200 hover:bg-cyan-50'}`}
                      >
                        {tab.label}
                      </button>
                    );
                  })}
                </div>
                <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
                  <button
                    type="button"
                    onClick={clearActiveMemoryFilter}
                    className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-semibold transition ${!activeMemoryFilterValue ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-slate-50 text-slate-500 hover:bg-slate-100'}`}
                  >
                    {activeMemoryFilterMeta.allLabel}
                  </button>
                  {activeMemoryFilterChoices.map(choice => (
                    <button
                      key={choice.value}
                      type="button"
                      onClick={() => selectActiveMemoryFilter(choice.value)}
                      className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-semibold transition ${activeMemoryFilterValue === choice.value ? 'border-cyan-300 bg-cyan-50 text-cyan-700' : 'border-slate-200 bg-white text-slate-500 hover:border-cyan-200 hover:bg-cyan-50'}`}
                    >
                      {choice.label}
                    </button>
                  ))}
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span>当前显示 {visibleMemories.length} / {memories.length} 条记忆</span>
                  {activeMemoryFilterLabels.map(label => <span key={label} className="rounded-full bg-cyan-50 px-2.5 py-1 font-semibold text-cyan-700">{label}</span>)}
                  {activeMemoryFilterLabels.length ? <button type="button" className="rounded-full bg-slate-100 px-2.5 py-1 font-semibold text-slate-600 hover:bg-slate-200" onClick={clearAllMemoryFilters}>清空全部筛选</button> : null}
                </div>
              </div>
              <div className="space-y-5">
                {groupedMemories.map(tickerGroup => (
                  <section key={tickerGroup.ticker} className="rounded-3xl border border-slate-200 bg-slate-50/70 p-5">
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-600">股票记忆</p>
                        <h3 className="text-2xl font-black text-slate-950">{tickerGroup.ticker}</h3>
                      </div>
                      <span className="rounded-full bg-white px-3 py-1 text-xs text-slate-500">{tickerGroup.dateGroups.reduce((count, dateGroup) => count + dateGroup.agentGroups.reduce((inner, agentGroup) => inner + agentGroup.memories.length, 0), 0)} 条记忆</span>
                    </div>
                    <div className={memoryDateGroupLayoutClass}>
                      {tickerGroup.dateGroups.map(dateGroup => (
                        <section key={dateGroup.analysisDate} className="rounded-3xl border border-white bg-white/85 p-4 shadow-sm">
                          <div className="mb-3 flex items-center justify-between gap-2">
                            <p className="text-sm font-bold text-cyan-700">{dateGroup.analysisDate}</p>
                            <span className="text-xs text-slate-400">{dateGroup.agentGroups.reduce((count, group) => count + group.memories.length, 0)} 条</span>
                          </div>
                          <div className="space-y-4">
                            {dateGroup.analysisGroups.map(analysisGroup => (
                              <section key={analysisGroup.sourceAnalysisTaskId} className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
                                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span className="rounded-full bg-slate-950 px-3 py-1 text-xs font-semibold text-white">分析 #{analysisGroup.sourceAnalysisTaskId}</span>
                                    <span className="text-xs text-slate-400">该次分析 {flattenMemoryAnalysisGroupMemories(analysisGroup).length} 条 Agent 记忆</span>
                                  </div>
                                  <span className="text-xs text-slate-400">同日同股多次分析已按任务编号区分</span>
                                </div>
                                <div className={memoryRailLayoutClass}>
                                  {flattenMemoryAnalysisGroupMemories(analysisGroup).map(memory => (
                                    <article key={memory.id} className={`flex min-h-44 flex-col justify-between rounded-2xl border p-4 transition hover:-translate-y-0.5 hover:shadow-lg ${selectedMemory?.id === memory.id ? 'border-cyan-300 bg-cyan-50 shadow-cyan-100' : 'border-slate-200 bg-white shadow-sm'}`}>
                                      <div>
                                        <div className="mb-2 flex flex-wrap gap-1.5">
                                          <span className="rounded-full bg-cyan-50 px-2.5 py-1 text-[11px] font-semibold text-cyan-700">{formatAgentName(memory.agent_name)}</span>
                                          {memory.tags?.section != null && <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-500">{formatSectionName(String(memory.tags.section))}</span>}
                                          {memory.archived && <span className="rounded-full bg-amber-50 px-2.5 py-1 text-[11px] text-amber-700">已归档</span>}
                                        </div>
                                        <button className="line-clamp-2 text-left text-base font-black leading-6 text-slate-950 hover:text-cyan-700" onClick={() => viewMemory(memory.id)}>{memory.title}</button>
                                        <p className="mt-2 line-clamp-3 rounded-xl bg-slate-50/90 p-3 text-sm leading-6 text-slate-500">{buildMemoryPreviewText(memory.content)}</p>
                                      </div>
                                      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
                                        <span className="text-xs text-slate-400">来源分析 #{memory.source_analysis_task_id}</span>
                                        <div className="flex flex-wrap gap-2">
                                          <Button onClick={() => viewMemory(memory.id)}>查看详情</Button>
                                          <Button className="bg-slate-100 text-slate-900 hover:bg-slate-200" onClick={() => { if (token) void api.archiveMemory(token, memory.id).then(() => refreshMemories()); }}>归档</Button>
                                        </div>
                                      </div>
                                    </article>
                                  ))}
                                </div>
                              </section>
                            ))}
                          </div>
                        </section>
                      ))}
                    </div>
                  </section>
                ))}
              </div>
              {!visibleMemories.length && memories.length ? <EmptyState title="暂无匹配记忆" description="切换日期、股票代码或 Agent 筛选条件后再查看。" /> : null}
              {!memories.length && <EmptyState title="暂无智能体记忆" description="完成分析后系统会自动沉淀各 Agent 的记忆。" />}
            </Card>
          )}

          {activePage === 'schedules' && (
            <div className="grid gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">
              <Card>
                <CardTitle><CalendarClock className="mr-2 inline text-cyan-600"/>定时分析任务</CardTitle>
                <div className="space-y-3">
                  <Field label="任务名称"><input className={inputClass} value={scheduleForm.name} onChange={e => setScheduleForm({...scheduleForm, name: e.target.value})} /></Field>
                  <Field label="开始时间"><input className={inputClass} type="datetime-local" value={scheduleForm.start_at} onChange={e => setScheduleForm({...scheduleForm, start_at: e.target.value})} /></Field>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="频率"><select className={inputClass} value={scheduleForm.interval} onChange={e => setScheduleForm({...scheduleForm, interval: e.target.value as ScheduleInterval})}><option value="daily">每日</option><option value="weekly">每周</option><option value="monthly">每月</option></select></Field>
                    <Field label="股票"><input className={inputClass} value={scheduleForm.params.ticker} onChange={e => setScheduleForm({...scheduleForm, params: {...scheduleForm.params, ticker: e.target.value.toUpperCase()}})} /></Field>
                  </div>
                  <Field label="Agent 列表" hint="下拉多选，默认全选；至少保留 1 个 Agent"><AnalystMultiSelect selected={scheduleForm.params.analysts} onChange={analysts => setScheduleForm({...scheduleForm, params: {...scheduleForm.params, analysts}})} /></Field>
                  <Field label="研究深度"><input className={inputClass} type="number" min="1" max="10" value={scheduleForm.params.research_depth} onChange={e => setScheduleForm({...scheduleForm, params: {...scheduleForm.params, research_depth: Number(e.target.value)}})} /></Field>
                  <Field label="思考深度" hint="定时任务触发时沿用该推理深度">
                    <select className={inputClass} value={getThinkingDepth(scheduleForm.params)} onChange={e => setScheduleForm({...scheduleForm, params: applyThinkingDepth(scheduleForm.params, e.target.value as ThinkingDepth)})}>
                      {thinkingDepthOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </Field>
                  <MemoryPicker title="任务记忆" memories={memories.slice(0, 6)} selectedIds={scheduleForm.params.memory_ids ?? []} onToggle={memoryId => setScheduleForm({...scheduleForm, params: {...scheduleForm.params, memory_ids: toggleMemoryId(scheduleForm.params.memory_ids, memoryId)}})} />
                  <Button className="w-full" disabled={!canCreateWorkspaceResource(selectedWorkspace?.role)} onClick={saveSchedule}>{editingScheduleId ? '保存任务' : '创建任务'}</Button>
                </div>
              </Card>
              <Card>
                <CardTitle>任务列表</CardTitle>
                <div className="space-y-3">
                  {schedules.length ? schedules.map(schedule => <article key={schedule.id} className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4"><div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between"><div><h3 className="font-semibold text-slate-950">{schedule.name}</h3><p className="mt-1 text-sm text-slate-400">{schedule.ticker} · {formatIntervalLabel(schedule.interval)} · {formatStatusLabel(schedule.status)} · 下次 {schedule.next_run_at}</p><p className="text-xs text-slate-400">最近执行：{formatStatusLabel(schedule.executions?.[0]?.status ?? '暂无')}</p></div><div className="flex flex-wrap gap-2"><Button onClick={() => editSchedule(schedule)}>编辑</Button><Button onClick={() => triggerSchedule(schedule)}>立即触发</Button><Button className="bg-slate-100 text-slate-900 hover:bg-slate-200" onClick={() => toggleSchedule(schedule)}>{schedule.status === 'active' ? '暂停' : '恢复'}</Button><Button className="bg-red-500 text-white hover:bg-red-400" onClick={() => removeSchedule(schedule)}>删除</Button></div></div></article>) : <EmptyState title="暂无定时任务" description="创建一个每日、每周或每月分析任务。" />}
                </div>
              </Card>
            </div>
          )}

          {activePage === 'interventions' && (
            <Card>
              <CardTitle><Brain className="mr-2 inline text-cyan-600"/>人工介入会话</CardTitle>
              {selectedIntervention ? <div className="space-y-3"><p className="text-sm text-slate-600">{buildInterventionLabel(selectedIntervention)}</p><textarea className={`${inputClass} min-h-28`} value={guidance} onChange={e => setGuidance(e.target.value)} placeholder="输入给指定 Agent 的补充观点、风险偏好或反驳意见" /><div className="flex flex-wrap gap-2"><Button onClick={addGuidance}>添加指令</Button><Button onClick={() => setInterventionStatus('pause')}>暂停</Button><Button onClick={() => setInterventionStatus('resume')}>恢复</Button><Button onClick={runContinuation}>运行延续分析</Button><Button onClick={() => setInterventionStatus('close')}>关闭</Button><Button className="bg-red-500 text-white hover:bg-red-400" onClick={deleteSelectedIntervention}>删除会话</Button></div><div className="max-h-72 overflow-auto rounded-2xl border border-slate-200 bg-slate-50/90 p-4"><InterventionMarkdownTimeline intervention={selectedIntervention} /></div></div> : <EmptyState title="暂无选中会话" description="可从某次分析结果中选择 Agent 并开启人工介入。" />}
              <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">{interventions.map(session => <button key={session.id} className="rounded-2xl border border-slate-200 bg-slate-50/80 p-3 text-left text-sm hover:border-cyan-300 hover:bg-cyan-50" onClick={() => loadIntervention(session.id)}>{buildInterventionLabel(session)}</button>)}</div>
            </Card>
          )}

          {activePage === 'governance' && (
            <Card>
              <CardTitle><Users className="mr-2 inline text-cyan-600"/>工作区治理</CardTitle>
              <div className="grid gap-6 xl:grid-cols-2">
                <div className="space-y-4">
                  <Field label="当前工作区"><select className={inputClass} value={selectedWorkspaceId ?? ''} onChange={e => setSelectedWorkspaceId(Number(e.target.value))}>{workspaces.map(workspace => <option key={workspace.id} value={workspace.id}>{workspace.name} · {formatWorkspaceRoleLabel(workspace.role)}</option>)}</select></Field>
                  <div className="grid grid-cols-[1fr_auto] gap-2"><input className={inputClass} value={workspaceName} onChange={e => setWorkspaceName(e.target.value)} /><Button onClick={createWorkspace}>新建</Button></div>
                  <InfoBlock title={`成员管理${selectedWorkspace ? ` · ${selectedWorkspace.name}` : ''}`}>
                    <div className="grid gap-2"><input className={inputClass} placeholder="member@example.com" value={memberEmail} onChange={e => setMemberEmail(e.target.value)} /><select className={inputClass} value={memberRole} onChange={e => setMemberRole(e.target.value as WorkspaceRole)}><option value="viewer">观察者</option><option value="member">成员</option><option value="admin">管理员</option><option value="owner">所有者</option></select><Button disabled={!canManageWorkspaceMembers(selectedWorkspace?.role)} onClick={addWorkspaceMember}>添加/更新成员</Button></div>
                  </InfoBlock>
                </div>
                <div className="space-y-4">
                  <div className="space-y-2">{selectedWorkspace?.members?.map(member => <div key={member.user_id} className="rounded-xl border border-slate-200 bg-slate-50/90 p-3 text-xs text-slate-600"><div className="flex flex-wrap items-center gap-2"><span className="font-medium text-slate-950">{member.email}</span><select className="rounded-lg border border-slate-200 bg-white p-1" value={member.role} disabled={!canManageWorkspaceMembers(selectedWorkspace?.role)} onChange={e => updateWorkspaceMemberRole(member.user_id, e.target.value as WorkspaceRole)}><option value="viewer">观察者</option><option value="member">成员</option><option value="admin">管理员</option><option value="owner">所有者</option></select><Button disabled={!canManageWorkspaceMembers(selectedWorkspace?.role)} onClick={() => removeWorkspaceMember(member.user_id)}>移除</Button>{member.role !== 'owner' && <Button disabled={!canManageWorkspaceMembers(selectedWorkspace?.role)} onClick={() => deactivateProvisionedUser(member.user_id)}>停用</Button>}</div></div>)}</div>
                  <InfoBlock title="用户预配">
                    <div className="grid gap-2"><input className={inputClass} placeholder="provision@example.com" value={provisionEmail} onChange={e => setProvisionEmail(e.target.value)} /><select className={inputClass} value={provisionRole} onChange={e => setProvisionRole(e.target.value as Exclude<WorkspaceRole, 'owner'>)}><option value="viewer">观察者</option><option value="member">成员</option><option value="admin">管理员</option></select><Button disabled={!canManageWorkspaceMembers(selectedWorkspace?.role)} onClick={provisionWorkspaceUser}>预配用户</Button></div>
                    <div className="mt-3 max-h-24 overflow-auto rounded-xl bg-slate-50/90 p-2 text-xs text-slate-400">{provisioningEvents.slice(0, 4).map(event => <p key={event.id}>{event.action} · {event.target_email} · {formatStatusLabel(event.status)}</p>)}</div>
                  </InfoBlock>
                </div>
              </div>
            </Card>
          )}

          {activePage === 'compliance' && (
            <Card>
              <CardTitle><ShieldCheck className="mr-2 inline text-cyan-600"/>审计与合规</CardTitle>
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2"><input className={inputClass} placeholder="审计用户 ID" value={auditUserId} onChange={e => setAuditUserId(e.target.value)} /><input className={inputClass} placeholder="事件类型" value={auditEventType} onChange={e => setAuditEventType(e.target.value)} /><input className={inputClass} placeholder="开始 ISO 时间" value={auditStartAt} onChange={e => setAuditStartAt(e.target.value)} /><input className={inputClass} placeholder="结束 ISO 时间" value={auditEndAt} onChange={e => setAuditEndAt(e.target.value)} /></div>
                <div className="flex flex-wrap gap-2"><Button onClick={refreshAuditConsole}>刷新报告</Button><Button onClick={refreshIdentityConsole}>身份映射</Button><Button onClick={previewRetention}>预览保留</Button><Button onClick={applyRetention}>执行保留</Button><Button onClick={refreshEnterpriseCompliance}>法律保全</Button><Button onClick={checkIdpHealth}>IdP 检查</Button><Button onClick={exportCompliance}>合规导出</Button></div>
                <div className="grid grid-cols-2 gap-2"><select className={inputClass} value={retentionResourceType} onChange={e => setRetentionResourceType(e.target.value as RetentionResourceType)}><option value="analyses">分析</option><option value="schedules">计划</option><option value="memories">记忆</option><option value="interventions">介入</option><option value="audit_logs">审计日志</option><option value="usage_ledger">用量账本</option></select><input className={inputClass} value={retentionCutoff} onChange={e => setRetentionCutoff(e.target.value)} /><input className={inputClass} placeholder="保全资源 ID，留空为全部" value={legalHoldResourceId} onChange={e => setLegalHoldResourceId(e.target.value)} /><input className={inputClass} placeholder="保全原因" value={legalHoldReason} onChange={e => setLegalHoldReason(e.target.value)} /></div>
                <Button onClick={createLegalHold}>创建法律保全</Button>
                <div className="max-h-28 overflow-auto rounded-2xl border border-slate-200 bg-slate-50/90 p-3 text-xs text-slate-600">{legalHolds.slice(0, 5).map(hold => <p key={hold.id}>{hold.active ? '生效中' : '已释放'} · {formatResourceTypeLabel(hold.resource_type)} · {hold.resource_id ?? '全部'} · <button className="text-cyan-700" onClick={() => releaseLegalHold(hold)}>释放</button></p>)}</div>
                <p className="text-xs text-slate-400">SSO：{identityStatus?.oidc_enabled ? `已启用 ${identityStatus.issuer_url}` : '未启用'} · 已映射身份：{identityUsers.length}</p>
                {retentionResult && <p className="text-xs text-slate-400">保留策略 {formatResourceTypeLabel(retentionResult.resource_type)}：匹配 {retentionResult.matched_count ?? retentionResult.affected_count ?? 0} · 保全 {retentionResult.held_count ?? 0} · 可处理/已处理 {retentionResult.eligible_count ?? retentionResult.affected_count ?? 0}</p>}
                {idpHealth && <p className="text-xs text-slate-400">IdP：{idpHealth.ok ? '正常' : '需要处理'} · {idpHealth.checks.map(check => `${check.name}:${check.ok ? '正常' : '失败'}`).join(', ')}</p>}
                <OperatorUsageReport auditEvents={auditEvents} runtimeHealth={runtimeHealth} showClusterRuntimeWarning={shouldShowClusterRuntimeWarning(runtimeHealth)} />
              </div>
            </Card>
          )}
        </section>
        {selectedMemory && <MemoryDetailModal memory={selectedMemory} onClose={() => setSelectedMemory(null)} />}

      </div>
    </main>
  );
}

export default App;
