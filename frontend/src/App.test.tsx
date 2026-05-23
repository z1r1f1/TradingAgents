import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  accountExportFilename,
  analystOptions,
  applyThinkingDepth,
  buildAgentProgressSteps,
  buildAgentFlowRoundGroups,
  buildEditableParamsFromTask,
  buildAuditQuery,
  buildOidcAuthorizeUrl,
  buildAnalysisParameterSummary,
  buildAnalysisTickerLabel,
  buildTickerInputUpdate,
  buildMemoryPreviewText,
  buildReusableAnalysisParamsFromTask,
  buildStaleAnalysisWarning,
  deriveAnalysisStatusFromEvent,
  resolveAgentFlowOutputDetail,
  buildRetentionPolicy,
  canCreateWorkspaceResource,
  canManageWorkspaceMembers,
  filterMemoriesForView,
  filterAnalysisHistory,
  filterRecentTickerSuggestions,
  formatStockSearchSuggestionLabel,
  flattenMemoryDateGroupMemories,
  getRecentAnalyzedTickers,
  getDefaultTickerFromHistory,
  getAshareTickerSearchCode,
  getDefaultReportSectionName,
  getMemoryFilterOptions,
  getRecoverableAnalysisTaskId,
  getSecondsSinceLastAnalysisEvent,
  getSelectedReportSection,
  getThinkingDepth,
  getThinkingDepthLabel,
  getEventsForTask,
  groupMemoriesByTickerDateAgent,
  flattenMemoryAnalysisGroupMemories,
  isAnalysisInProgress,
  parseMarkdownBlocks,
  formatWorkspaceRoleLabel,
  getWorkspacePageMeta,
  memoryDateGroupLayoutClass,
  memoryRailLayoutClass,
  MarkdownDocument,
  MemoryDetailModal,
  ModalCloseButton,
  AgentProgressFlow,
  defaultParams,
  formatSelectedAnalysts,
  parseAnalystsInput,
  shouldShowClusterRuntimeWarning,
  shouldShowProductionSafetyWarning,
  shouldShowTickerDropdown,
  resolveThemeMode,
  ThemeToggle,
  toggleAnalystSelection,
  workspacePages
} from './App';
import type { AnalysisParams, AnalysisTask, StockSearchSuggestion } from './api';

const defaultParamsForTest: AnalysisParams = {
  ticker: 'SPY',
  analysis_date: '2026-05-01',
  analysts: ['market'],
  research_depth: 1,
  llm_provider: 'openai',
  quick_model: 'gpt-5.5',
  deep_model: 'gpt-5.5',
  output_language: '中文'
};

describe('TradingAgents web frontend', () => {
  it('splits authenticated workspace functions into dedicated Chinese pages', () => {
    expect(workspacePages.map(page => page.id)).toEqual([
      'analysis',
      'history',
      'memories',
      'schedules',
      'interventions',
      'governance',
      'compliance'
    ]);
    expect(getWorkspacePageMeta('analysis')?.title).toBe('股票分析');
    expect(getWorkspacePageMeta('compliance')?.title).toBe('合规与身份');
  });

  it('exposes explicit light and dark theme controls instead of mixing themes implicitly', () => {
    expect(resolveThemeMode('dark', false)).toBe('dark');
    expect(resolveThemeMode('light', true)).toBe('light');
    expect(resolveThemeMode(null, true)).toBe('dark');
    expect(resolveThemeMode('unexpected', false)).toBe('light');

    const lightHtml = renderToStaticMarkup(<ThemeToggle themeMode="light" onToggle={() => undefined} />);
    const darkHtml = renderToStaticMarkup(<ThemeToggle themeMode="dark" onToggle={() => undefined} />);

    expect(lightHtml).toContain('当前：亮色主题');
    expect(lightHtml).toContain('切换到深色主题');
    expect(lightHtml).toContain('aria-pressed="false"');
    expect(darkHtml).toContain('当前：深色主题');
    expect(darkHtml).toContain('切换到亮色主题');
    expect(darkHtml).toContain('aria-pressed="true"');
  });

  it('loads historical task parameters into the editable analysis form', () => {
    const task: AnalysisTask = {
      id: 42,
      status: 'completed',
      parameters: {
        ticker: 'MSFT',
        analysis_date: '2026-05-01',
        analysts: ['fundamentals'],
        research_depth: 1,
        llm_provider: 'openai',
        quick_model: 'gpt-5.4-mini',
        deep_model: 'gpt-5.5',
        output_language: 'English'
      }
    };

    const params = buildEditableParamsFromTask(task);

    expect(params.ticker).toBe('MSFT');
    expect(params.analysts).toEqual(['fundamentals']);
    expect(params.research_depth).toBe(1);
  });

  it('loads reusable analysis parameters without carrying over previous output data', () => {
    const task: AnalysisTask = {
      id: 42,
      status: 'completed',
      ticker: 'MSFT',
      analysis_date: '2026-05-01',
      events: [
        { sequence: 1, agent: 'Market Analyst', event_type: 'report.section', message: 'old report', created_at: '2026-05-01T00:00:00Z' }
      ],
      report_sections: [{ section_name: 'market', content: 'old report' }],
      parameters: {
        ticker: 'MSFT',
        analysis_date: '2026-05-01',
        analysts: ['fundamentals'],
        research_depth: 1,
        llm_provider: 'openai',
        quick_model: 'gpt-5.4-mini',
        deep_model: 'gpt-5.5',
        output_language: 'English'
      }
    };

    const draft = buildReusableAnalysisParamsFromTask(task);

    expect(draft.params.ticker).toBe('MSFT');
    expect(draft.tickerInputValue).toBe('MSFT');
    expect(draft.selected).toBeNull();
    expect(draft.events).toEqual([]);
  });

  it('maps the visible thinking depth selector to provider-specific payload fields', () => {
    const params = applyThinkingDepth(
      {
        ticker: 'MSFT',
        analysis_date: '2026-05-01',
        analysts: ['fundamentals'],
        research_depth: 1,
        llm_provider: 'openai',
        quick_model: 'gpt-5.5',
        deep_model: 'gpt-5.5',
        output_language: '中文'
      },
      'xhigh'
    );

    expect(params.openai_reasoning_effort).toBe('xhigh');
    expect(params.google_thinking_level).toBe('xhigh');
    expect(params.anthropic_effort).toBe('xhigh');
    expect(getThinkingDepth(params)).toBe('xhigh');
    expect(getThinkingDepthLabel(params)).toContain('极高');
    expect(buildAnalysisParameterSummary({ id: 9, status: 'queued', parameters: params })).toContain('思考：极高');
  });

  it('filters history by ticker and analysis date while showing saved parameters', () => {
    const items: AnalysisTask[] = [
      {
        id: 1,
        status: 'completed',
        ticker: 'AAPL',
        analysis_date: '2026-05-01',
        parameters: {
          ticker: 'AAPL',
          analysis_date: '2026-05-01',
          analysts: ['market'],
          research_depth: 1,
          llm_provider: 'openai',
          quick_model: 'gpt-5.5',
          deep_model: 'gpt-5.5',
          output_language: '中文'
        }
      },
      { id: 2, status: 'completed', ticker: 'MSFT', analysis_date: '2026-05-02' }
    ];

    expect(filterAnalysisHistory(items, { ticker: 'aa', analysisDate: '2026-05-01' }).map(item => item.id)).toEqual([1]);
    expect(buildAnalysisParameterSummary(items[0])).toContain('Agent：market');
    expect(buildAnalysisParameterSummary(items[0])).toContain('模型：gpt-5.5 / gpt-5.5');
  });

  it('suggests recently analyzed tickers with fuzzy matching', () => {
    const items: AnalysisTask[] = [
      { id: 7, status: 'completed', ticker: '000925.SZ' },
      { id: 6, status: 'completed', parameters: { ...defaultParamsForTest, ticker: 'AAPL' } },
      { id: 5, status: 'completed', ticker: '600330.SS' },
      { id: 4, status: 'completed', ticker: 'AAPL' },
      { id: 3, status: 'completed', parameters: { ...defaultParamsForTest, ticker: 'MSFT' } }
    ];

    expect(getRecentAnalyzedTickers(items)).toEqual(['000925.SZ', 'AAPL', '600330.SS', 'MSFT']);
    expect(filterRecentTickerSuggestions(['000925.SZ', 'AAPL', '600330.SS', 'MSFT'], 'apl')).toEqual(['AAPL']);
    expect(filterRecentTickerSuggestions(['000925.SZ', 'AAPL', '600330.SS', 'MSFT'], '033')).toEqual(['600330.SS']);
    expect(filterRecentTickerSuggestions(['000925.SZ', 'AAPL', '600330.SS', 'MSFT'], 'sz')).toEqual(['000925.SZ']);
    expect(getDefaultTickerFromHistory(items, 'SPY')).toBe('000925.SZ');
    expect(getDefaultTickerFromHistory([], 'SPY')).toBe('SPY');
  });

  it('extracts A-share search codes from normalized tickers', () => {
    expect(getAshareTickerSearchCode('603386.SS')).toBe('603386');
    expect(getAshareTickerSearchCode('000767.sz')).toBe('000767');
    expect(getAshareTickerSearchCode('AAPL')).toBeNull();
  });

  it('keeps raw stock-name input for fuzzy search while normalizing manual ticker payloads', () => {
    expect(buildTickerInputUpdate('jun')).toEqual({ inputValue: 'jun', payloadTicker: 'JUN' });
    expect(buildTickerInputUpdate('骏亚')).toEqual({ inputValue: '骏亚', payloadTicker: '骏亚' });
    expect(buildTickerInputUpdate('600330.ss')).toEqual({ inputValue: '600330.ss', payloadTicker: '600330.SS' });
  });

  it('keeps the ticker dropdown open for typed stock-name queries even before results arrive', () => {
    expect(shouldShowTickerDropdown({ open: true, query: '骏亚', recentCount: 0, suggestionCount: 0, loading: false })).toBe(true);
    expect(shouldShowTickerDropdown({ open: true, query: '', recentCount: 0, suggestionCount: 0, loading: false })).toBe(false);
  });

  it('formats A-share stock suggestions and history labels with stock names', () => {
    const suggestion: StockSearchSuggestion = {
      code: '603386',
      name: '骏亚科技',
      ticker: '603386.SS',
      market: '沪A',
      pinyin: 'JYKJ'
    };

    expect(formatStockSearchSuggestionLabel(suggestion)).toBe('骏亚科技 · 603386.SS · 沪A');
    expect(buildAnalysisTickerLabel({ id: 8, status: 'completed', ticker: '603386.SS', ticker_name: '骏亚科技' })).toBe('骏亚科技 · 603386.SS');
    expect(buildAnalysisTickerLabel({ id: 9, status: 'completed', parameters: { ...defaultParamsForTest, ticker: '000767.SZ', ticker_name: '晋控电力' } })).toBe('晋控电力 · 000767.SZ');
    expect(buildAnalysisTickerLabel({ id: 10, status: 'completed', ticker: 'AAPL' })).toBe('AAPL');
  });

  it('filters history by saved A-share stock name or ticker', () => {
    const items: AnalysisTask[] = [
      { id: 1, status: 'completed', ticker: '603386.SS', ticker_name: '骏亚科技' },
      { id: 2, status: 'completed', ticker: '000767.SZ', parameters: { ...defaultParamsForTest, ticker: '000767.SZ', ticker_name: '晋控电力' } }
    ];

    expect(filterAnalysisHistory(items, { ticker: '骏亚', analysisDate: '' }).map(item => item.id)).toEqual([1]);
    expect(filterAnalysisHistory(items, { ticker: '000767', analysisDate: '' }).map(item => item.id)).toEqual([2]);
  });

  it('recovers the currently running analysis after refresh by preferring stored active tasks', () => {
    const items: AnalysisTask[] = [
      { id: 1, status: 'completed', ticker: 'AAPL' },
      { id: 2, status: 'running', ticker: 'MSFT' },
      { id: 3, status: 'queued', ticker: 'TSLA' }
    ];

    expect(isAnalysisInProgress('running')).toBe(true);
    expect(getRecoverableAnalysisTaskId(items, null, 2)).toBe(2);
    expect(getRecoverableAnalysisTaskId(items, null, 99)).toBe(3);
    expect(getRecoverableAnalysisTaskId(items, 2, 3)).toBeNull();
  });

  it('derives flow-chart style agent progress states from realtime events', () => {
    const steps = buildAgentProgressSteps(
      [
        { sequence: 1, agent: 'System', event_type: 'task.started', message: 'start', created_at: '2026-05-01T00:00:00Z' },
        { sequence: 2, agent: 'Market Analyst', event_type: 'agent.completed', message: 'done', created_at: '2026-05-01T00:00:01Z' },
        { sequence: 3, agent: 'News Analyst', event_type: 'agent.started', message: 'started', created_at: '2026-05-01T00:00:02Z' }
      ],
      'running',
      ['market', 'news']
    );

    expect(steps.map(step => [step.agent, step.status])).toEqual([
      ['System', 'done'],
      ['Market Analyst', 'done'],
      ['News Analyst', 'active'],
      ['Research Manager', 'waiting'],
      ['Trader', 'waiting'],
      ['Portfolio Manager', 'waiting']
    ]);
    expect(steps[1].eventCount).toBe(1);
    expect(steps[1].outputMessage).toBe('done');
    expect(steps[2].lastMessage).toBe('started');
  });

  it('groups repeated agent outputs into visual analysis rounds', () => {
    const rounds = buildAgentFlowRoundGroups([
      { sequence: 1, agent: 'System', event_type: 'task.started', message: 'start', created_at: '2026-05-01T00:00:00Z' },
      { sequence: 2, agent: 'Market Analyst', event_type: 'report.section', message: 'first market view', created_at: '2026-05-01T00:00:01Z' },
      { sequence: 3, agent: 'News Analyst', event_type: 'agent.message', message: 'news discussion', created_at: '2026-05-01T00:00:02Z' },
      { sequence: 4, agent: 'Market Analyst', event_type: 'report.section', message: 'second market view', created_at: '2026-05-01T00:00:03Z' },
      { sequence: 5, agent: 'Trader', event_type: 'agent.completed', message: 'trade plan', created_at: '2026-05-01T00:00:04Z' }
    ]);

    expect(rounds.map(round => round.round)).toEqual([1, 2]);
    expect(rounds[0].events.map(event => event.sequence)).toEqual([1, 2, 3]);
    expect(rounds[1].events.map(event => event.sequence)).toEqual([4, 5]);
    expect(rounds[1].summary).toContain('市场分析师');
  });

  it('keeps explicit debate rounds visible instead of collapsing them into report output rounds', () => {
    const rounds = buildAgentFlowRoundGroups([
      { sequence: 1, agent: 'System', event_type: 'task.started', message: 'start', created_at: '2026-05-01T00:00:00Z' },
      { sequence: 2, agent: 'Bull Researcher', event_type: 'debate.message', message: 'bull round 1', payload: { debate: 'investment', round: 1 }, created_at: '2026-05-01T00:00:01Z' },
      { sequence: 3, agent: 'Bear Researcher', event_type: 'debate.message', message: 'bear round 1', payload: { debate: 'investment', round: 1 }, created_at: '2026-05-01T00:00:02Z' },
      { sequence: 4, agent: 'Bull Researcher', event_type: 'debate.message', message: 'bull round 2', payload: { debate: 'investment', round: 2 }, created_at: '2026-05-01T00:00:03Z' },
      { sequence: 5, agent: 'Bear Researcher', event_type: 'debate.message', message: 'bear round 2', payload: { debate: 'investment', round: 2 }, created_at: '2026-05-01T00:00:04Z' },
      { sequence: 6, agent: 'Bull Researcher', event_type: 'debate.message', message: 'bull round 3', payload: { debate: 'investment', round: 3 }, created_at: '2026-05-01T00:00:05Z' }
    ]);

    expect(rounds.map(round => round.round)).toEqual([1, 2, 3]);
    expect(rounds[0].events.map(event => event.sequence)).toEqual([1, 2, 3]);
    expect(rounds[1].events.map(event => event.sequence)).toEqual([4, 5]);
    expect(rounds[2].events.map(event => event.sequence)).toEqual([6]);
    expect(rounds[0].summary).toContain('投研辩论第 1 轮');
  });

  it('uses semantic workstation tokens for modal surfaces and close controls', () => {
    const buttonHtml = renderToStaticMarkup(<ModalCloseButton onClick={() => undefined} />);
    const modalHtml = renderToStaticMarkup(
      <MemoryDetailModal
        memory={{
          id: 1,
          user_id: 7,
          title: '记忆标题',
          ticker: 'SPY',
          analysis_date: '2026-05-01',
          agent_name: 'Market Analyst',
          source_analysis_task_id: 3,
          content: '## 细节',
          tags: {},
          created_at: '2026-05-01T00:00:00Z',
          archived: false
        }}
        onClose={() => undefined}
      />
    );

    expect(buttonHtml).toContain('关闭');
    expect(buttonHtml).toContain('bg-accent');
    expect(buttonHtml).toContain('text-accent-foreground');
    expect(buttonHtml).toContain('shadow-glow');
    expect(buttonHtml).toContain('aria-label="关闭弹窗"');
    expect(modalHtml).toContain('surface-panel-strong');
    expect(modalHtml).toContain('chip-accent');
  });

  it('renders realtime flow with clickable markdown outputs and compact round track', () => {
    const html = renderToStaticMarkup(
      <AgentProgressFlow
        task={{ id: 9, status: 'running', parameters: { ...defaultParamsForTest, analysts: ['market', 'news'] } }}
        events={[
          { sequence: 1, agent: 'System', event_type: 'task.started', message: 'start', created_at: '2026-05-01T00:00:00Z' },
          { sequence: 2, agent: 'Market Analyst', event_type: 'report.section', message: '## 市场阶段产出', created_at: '2026-05-01T00:00:01Z' },
          { sequence: 3, agent: 'Market Analyst', event_type: 'report.section', message: '## 第二轮市场修订', created_at: '2026-05-01T00:00:02Z' }
        ]}
      />
    );

    expect(html).toContain('阶段产出');
    expect(html).toContain('查看详情');
    expect(html).toContain('讨论与产出轨迹');
    expect(html).toContain('轮次导航');
    expect(html).toContain('max-h-[420px]');
    expect(html).not.toContain('grid gap-2 md:grid-cols-2');
    expect(html).toContain('<h4');
  });

  it('renders detail actions for bull and bear researcher debate messages', () => {
    const html = renderToStaticMarkup(
      <AgentProgressFlow
        task={{ id: 11, status: 'running', parameters: { ...defaultParamsForTest, analysts: ['market'] } }}
        events={[
          { sequence: 1, agent: 'System', event_type: 'task.started', message: 'start', created_at: '2026-05-01T00:00:00Z' },
          { sequence: 2, agent: 'Bull Researcher', event_type: 'debate.message', message: 'Bull Analyst: 多方完整观点', payload: { debate: 'investment', round: 1 }, created_at: '2026-05-01T00:00:01Z' },
          { sequence: 3, agent: 'Bear Researcher', event_type: 'debate.message', message: 'Bear Analyst: 空方完整观点', payload: { debate: 'investment', round: 1 }, created_at: '2026-05-01T00:00:02Z' }
        ]}
      />
    );

    expect(html).toContain('多方研究员');
    expect(html).toContain('空方研究员');
    expect(html).toMatch(/多方研究员[\s\S]*?查看详情/);
    expect(html).toMatch(/空方研究员[\s\S]*?查看详情/);
    expect(html.match(/查看详情/g) ?? []).toHaveLength(4);
  });

  it('does not render previous task discussion events in a new analysis flow', () => {
    const events = [
      { task_id: 1, sequence: 1, agent: 'Bull Researcher', event_type: 'debate.message', message: '旧一轮多方观点', created_at: '2026-05-01T00:00:00Z' },
      { task_id: 1, sequence: 2, agent: 'Bear Researcher', event_type: 'debate.message', message: '旧一轮空方观点', created_at: '2026-05-01T00:00:01Z' }
    ];

    const scopedEvents = getEventsForTask({ id: 2 }, events);
    const html = renderToStaticMarkup(
      <AgentProgressFlow
        task={{ id: 2, status: 'queued', parameters: { ...defaultParamsForTest, ticker: 'AAPL' } }}
        events={events}
      />
    );

    expect(scopedEvents).toEqual([]);
    expect(html).toContain('等待实时事件');
    expect(html).toContain('事件 0 条');
    expect(html).not.toContain('旧一轮多方观点');
    expect(html).not.toContain('旧一轮空方观点');
  });

  it('keeps realtime flow as the single event surface instead of a separate agent output panel', () => {
    const html = renderToStaticMarkup(
      <AgentProgressFlow
        task={{ id: 10, status: 'running', parameters: { ...defaultParamsForTest, analysts: ['market'] } }}
        events={[{ sequence: 1, agent: 'Market Analyst', event_type: 'agent.message', message: '实时消息', created_at: '2026-05-01T00:00:00Z' }]}
      />
    );

    expect(html).not.toContain('Agent 实时输出');
  });

  it('resolves full markdown details for report sections and final decisions', () => {
    const task: AnalysisTask = {
      id: 12,
      status: 'running',
      report_sections: [
        { section_name: 'market_report', content: '## 完整市场报告\n\n**评级**: 持有\n\n- 趋势稳定' },
        { section_name: 'final_trade_decision', content: '## 最终决策\n\n**结论**: HOLD' }
      ],
      final_decision: { decision: 'HOLD', rationale: '## 完整最终决策\n\n**理由**: 风险可控' }
    };

    const sectionDetail = resolveAgentFlowOutputDetail(task, {
      sequence: 2,
      agent: 'Market Analyst',
      event_type: 'report.section',
      message: 'truncated preview',
      payload: { section: 'market_report' },
      created_at: '2026-05-01T00:00:00Z'
    });
    const finalDetail = resolveAgentFlowOutputDetail(task, {
      sequence: 3,
      agent: 'Portfolio Manager',
      event_type: 'agent.completed',
      message: 'truncated final decision',
      created_at: '2026-05-01T00:00:01Z'
    });

    expect(sectionDetail.content).toContain('完整市场报告');
    expect(sectionDetail.content).not.toContain('truncated preview');
    expect(finalDetail.content).toContain('完整最终决策');
    expect(finalDetail.content).not.toContain('truncated final decision');
  });

  it('keeps Graph transport events out of the flow chart and advances to the next analyst', () => {
    const steps = buildAgentProgressSteps(
      [
        { sequence: 1, agent: 'System', event_type: 'task.started', message: 'start', created_at: '2026-05-01T00:00:00Z' },
        { sequence: 2, agent: 'Graph', event_type: 'tool.call', message: 'get_stock_data', created_at: '2026-05-01T00:00:01Z' },
        { sequence: 3, agent: 'Market Analyst', event_type: 'report.section', message: 'market done', created_at: '2026-05-01T00:00:02Z' },
        { sequence: 4, agent: 'Graph', event_type: 'agent.message', message: 'Continue', created_at: '2026-05-01T00:00:03Z' }
      ],
      'running',
      ['market', 'news', 'fundamentals', 'social']
    );

    expect(steps.map(step => step.agent)).not.toContain('Graph');
    expect(steps.map(step => [step.agent, step.status])).toEqual([
      ['System', 'done'],
      ['Market Analyst', 'done'],
      ['News Analyst', 'active'],
      ['Fundamentals Analyst', 'waiting'],
      ['Social Analyst', 'waiting'],
      ['Research Manager', 'waiting'],
      ['Trader', 'waiting'],
      ['Portfolio Manager', 'waiting']
    ]);
  });

  it('derives the visible task status from realtime lifecycle events', () => {
    expect(deriveAnalysisStatusFromEvent('queued', { sequence: 1, agent: 'System', event_type: 'task.started', message: 'start', created_at: '2026-05-01T00:00:00Z' })).toBe('running');
    expect(deriveAnalysisStatusFromEvent('running', { sequence: 2, agent: 'System', event_type: 'task.completed', message: 'done', created_at: '2026-05-01T00:00:01Z' })).toBe('completed');
    expect(deriveAnalysisStatusFromEvent('running', { sequence: 3, agent: 'System', event_type: 'task.failed', message: 'failed', created_at: '2026-05-01T00:00:02Z' })).toBe('failed');
  });

  it('detects stale running analyses for cancellation and retry affordances', () => {
    const task: AnalysisTask = {
      id: 77,
      status: 'running',
      last_event_at: '2026-05-07T01:13:19+00:00',
      stale: true
    };

    expect(getSecondsSinceLastAnalysisEvent(task, new Date('2026-05-07T01:18:19+00:00'))).toBe(300);
    expect(buildStaleAnalysisWarning(task, new Date('2026-05-07T01:18:19+00:00'))).toContain('5 分钟');
  });

  it('defaults the analysis document viewer to the last generated report section', () => {
    const task: AnalysisTask = {
      id: 8,
      status: 'completed',
      report_sections: [
        { section_name: 'market_report', content: 'market document' },
        { section_name: 'final_trade_decision', content: 'final document' }
      ]
    };

    expect(getDefaultReportSectionName(task)).toBe('final_trade_decision');
    expect(getSelectedReportSection(task, null)?.content).toBe('final document');
    expect(getSelectedReportSection(task, 'market_report')?.content).toBe('market document');
  });

  it('parses markdown report documents into renderable blocks', () => {
    const blocks = parseMarkdownBlocks(
      [
        '## 摘要',
        '',
        '- 趋势向上',
        '- 风险偏高',
        '',
        '| 指标 | 数值 |',
        '| --- | --- |',
        '| RSI | 72 |',
        '',
        '```',
        'FINAL TRANSACTION PROPOSAL: HOLD',
        '```'
      ].join('\n')
    );

    expect(blocks.map(block => block.type)).toEqual(['heading', 'list', 'table', 'code']);
    expect(blocks[0]).toMatchObject({ type: 'heading', level: 2, text: '摘要' });
    expect(blocks[1]).toMatchObject({ type: 'list', ordered: false, items: ['趋势向上', '风险偏高'] });
    expect(blocks[2]).toMatchObject({ type: 'table', rows: [['指标', '数值'], ['RSI', '72']] });
  });

  it('keeps markdown content as structured blocks for every document surface', () => {
    const blocks = parseMarkdownBlocks('**评级**: 持有\n\n> 风险提示\n\n1. 等待回踩');

    expect(blocks).toEqual([
      { type: 'paragraph', text: '**评级**: 持有' },
      { type: 'quote', text: '风险提示' },
      { type: 'list', ordered: true, items: ['等待回踩'] }
    ]);
  });

  it('renders markdown documents into semantic HTML instead of plain markdown text', () => {
    const html = renderToStaticMarkup(<MarkdownDocument content={'## 结论\n\n**评级**: 持有\n\n> 风险提示'} />);

    expect(html).toContain('<h4');
    expect(html).toContain('<strong');
    expect(html).toContain('<blockquote');
    expect(html).not.toContain('**评级**');
  });

  it('parses adjusted analyst input before submitting a new run', () => {
    expect(parseAnalystsInput('market, news, market')).toEqual(['market', 'news']);
  });

  it('defaults analyst selection to all agents and supports multi-select dropdown toggles', () => {
    expect(defaultParams.analysts).toEqual(analystOptions.map(option => option.value));
    expect(defaultParams.research_depth).toBe(5);
    expect(getThinkingDepth(defaultParams)).toBe('xhigh');
    expect(formatSelectedAnalysts(defaultParams.analysts)).toContain('全选');
    expect(toggleAnalystSelection(defaultParams.analysts, 'news')).toEqual(['market', 'social', 'fundamentals']);
    expect(toggleAnalystSelection(['market'], 'market')).toEqual(['market']);
    expect(toggleAnalystSelection(['market'], 'news')).toEqual(['market', 'news']);
  });
});

import { buildSchedulePayload, buildScheduleFormFromSchedule } from './App';
import type { Schedule } from './api';

describe('scheduled analysis frontend helpers', () => {
  it('builds a schedule payload from editable form fields', () => {
    const payload = buildSchedulePayload({
      name: 'Morning SPY',
      start_at: '2026-05-01T09:30',
      interval: 'daily',
      params: {
        ticker: 'spy',
        analysis_date: '2026-05-01',
        analysts: ['market'],
        research_depth: 1,
        llm_provider: 'openai',
        quick_model: 'gpt-5.4-mini',
        deep_model: 'gpt-5.5',
        output_language: 'English'
      }
    });

    expect(payload.ticker).toBe('SPY');
    expect(payload.interval).toBe('daily');
    expect(payload.start_at).toBe('2026-05-01T09:30:00');
    expect(payload.analysts).toEqual(['market']);
  });

  it('loads an existing schedule into the editable schedule form', () => {
    const schedule: Schedule = {
      id: 7,
      name: 'Monthly AAPL',
      status: 'active',
      ticker: 'AAPL',
      start_at: '2026-05-01T09:30:00+00:00',
      next_run_at: '2026-06-01T09:30:00+00:00',
      interval: 'monthly',
      analysts: ['news'],
      research_depth: 3,
      llm_provider: 'openai',
      quick_model: 'gpt-5.4-mini',
      deep_model: 'gpt-5.5',
      output_language: 'English'
    };

    const form = buildScheduleFormFromSchedule(schedule);

    expect(form.name).toBe('Monthly AAPL');
    expect(form.interval).toBe('monthly');
    expect(form.params.ticker).toBe('AAPL');
    expect(form.params.analysts).toEqual(['news']);
  });
});

import { buildMemoryOptionLabel, toggleMemoryId } from './App';
import type { AgentMemory } from './api';

describe('agent memory frontend helpers', () => {
  const memory: AgentMemory = {
    id: 9,
    user_id: 1,
    source_analysis_task_id: 3,
    ticker: 'SPY',
    analysis_date: '2026-05-01',
    agent_name: 'Market Analyst',
    title: 'SPY Market Analyst memory for 2026-05-01',
    content: 'market context',
    tags: { section: 'market_report' },
    archived: false,
    created_at: '2026-05-01T10:00:00+00:00'
  };

  it('labels selectable memories by agent, ticker, and date', () => {
    expect(buildMemoryOptionLabel(memory)).toBe('市场分析师 · SPY · 2026-05-01');
  });

  it('builds a compact plain-text memory preview for readable cards', () => {
    expect(buildMemoryPreviewText('## 标题\n\n**评级**: 关注\n\n- 等待确认\n- 控制仓位', 14)).toBe('标题 评级: 关注 等待确认...');
  });

  it('toggles selected memory ids deterministically', () => {
    expect(toggleMemoryId([1, 3], 2)).toEqual([1, 3, 2]);
    expect(toggleMemoryId([1, 3], 3)).toEqual([1]);
  });

  it('shows memory details in a modal with rendered markdown content', () => {
    const html = renderToStaticMarkup(
      <MemoryDetailModal
        memory={{ ...memory, content: '## 记忆详情\n\n**评级**: 关注\n\n1. 等待确认' }}
        onClose={() => undefined}
      />
    );

    expect(html).toContain('role="dialog"');
    expect(html).toContain('<strong');
    expect(html).toContain('<ol');
    expect(html).not.toContain('**评级**');
  });

  it('groups memories by ticker, analysis date, and agent with recent dates first', () => {
    const groups = groupMemoriesByTickerDateAgent([
      { ...memory, id: 1, ticker: 'AAPL', analysis_date: '2026-05-01', agent_name: 'Market Analyst' },
      { ...memory, id: 2, ticker: 'AAPL', analysis_date: '2026-05-02', agent_name: 'News Analyst' },
      { ...memory, id: 3, ticker: 'AAPL', analysis_date: '2026-05-02', agent_name: 'Market Analyst' },
      { ...memory, id: 4, ticker: 'MSFT', analysis_date: '2026-05-01', agent_name: 'Trader' }
    ]);

    expect(groups.map(group => group.ticker)).toEqual(['AAPL', 'MSFT']);
    expect(groups[0].dateGroups.map(group => group.analysisDate)).toEqual(['2026-05-02', '2026-05-01']);
    expect(groups[0].dateGroups[0].agentGroups.map(group => group.agentName)).toEqual(['市场分析师', '新闻分析师']);
    expect(groups[0].dateGroups[0].agentGroups[0].memories.map(item => item.id)).toEqual([3]);
    expect(flattenMemoryDateGroupMemories(groups[0].dateGroups[0]).map(item => item.id)).toEqual([3, 2]);
  });

  it('separates multiple analysis runs for the same ticker and analysis date', () => {
    const groups = groupMemoriesByTickerDateAgent([
      { ...memory, id: 1, source_analysis_task_id: 101, ticker: 'AAPL', analysis_date: '2026-05-02', agent_name: 'Market Analyst' },
      { ...memory, id: 2, source_analysis_task_id: 101, ticker: 'AAPL', analysis_date: '2026-05-02', agent_name: 'News Analyst' },
      { ...memory, id: 3, source_analysis_task_id: 102, ticker: 'AAPL', analysis_date: '2026-05-02', agent_name: 'Market Analyst' }
    ]);
    const dateGroup = groups[0].dateGroups[0];

    expect(dateGroup.analysisGroups.map(group => group.sourceAnalysisTaskId)).toEqual([102, 101]);
    expect(dateGroup.analysisGroups[0].agentGroups.map(group => group.agentName)).toEqual(['市场分析师']);
    expect(dateGroup.analysisGroups[1].agentGroups.map(group => group.agentName)).toEqual(['市场分析师', '新闻分析师']);
    expect(flattenMemoryAnalysisGroupMemories(dateGroup.analysisGroups[1]).map(item => item.id)).toEqual([1, 2]);
    expect(flattenMemoryDateGroupMemories(dateGroup).map(item => item.id)).toEqual([3, 1, 2]);
  });

  it('uses horizontal memory rails instead of vertical-only memory stacks', () => {
    expect(memoryRailLayoutClass).toContain('grid-flow-col');
    expect(memoryRailLayoutClass).toContain('overflow-x-auto');
    expect(memoryRailLayoutClass).not.toContain('md:grid-cols-2');
    expect(memoryDateGroupLayoutClass).not.toContain('auto-cols');
    expect(memoryDateGroupLayoutClass).not.toContain('grid-flow-col');
  });

  it('builds tab filter options and filters memories by ticker date and agent', () => {
    const memories: AgentMemory[] = [
      { ...memory, id: 1, ticker: 'AAPL', analysis_date: '2026-05-01', agent_name: 'Market Analyst' },
      { ...memory, id: 2, ticker: 'MSFT', analysis_date: '2026-05-02', agent_name: 'News Analyst' },
      { ...memory, id: 3, ticker: 'AAPL', analysis_date: '2026-05-02', agent_name: 'News Analyst' }
    ];

    expect(getMemoryFilterOptions(memories)).toEqual({
      tickers: ['AAPL', 'MSFT'],
      dates: ['2026-05-02', '2026-05-01'],
      agents: [
        { rawName: 'Market Analyst', label: '市场分析师' },
        { rawName: 'News Analyst', label: '新闻分析师' }
      ]
    });
    expect(filterMemoriesForView(memories, { ticker: 'AAPL', analysisDate: '2026-05-02', agentName: 'News Analyst' }).map(item => item.id)).toEqual([3]);
    expect(filterMemoriesForView(memories, { agentName: 'News Analyst' }).map(item => item.id)).toEqual([2, 3]);
  });
});

import { buildInterventionLabel } from './App';
import type { InterventionSession } from './api';

describe('human intervention frontend helpers', () => {
  it('labels intervention sessions by source task, agent, and status', () => {
    const session: InterventionSession = {
      id: 5,
      user_id: 1,
      source_analysis_task_id: 9,
      target_agent_name: 'Market Analyst',
      status: 'open',
      created_at: '2026-05-01T10:00:00+00:00',
      updated_at: '2026-05-01T10:00:00+00:00'
    };

    expect(buildInterventionLabel(session)).toBe('#5 · 分析 9 · 市场分析师 · 进行中');
  });
});

describe('production hardening frontend helpers', () => {
  it('surfaces warnings for non-production or localhost API settings', () => {
    expect(shouldShowProductionSafetyWarning('development', 'http://localhost:8000')).toBe(true);
    expect(shouldShowProductionSafetyWarning('production', 'http://127.0.0.1:8000')).toBe(true);
    expect(shouldShowProductionSafetyWarning('production', 'https://tradingagents.example.com')).toBe(false);
  });

  it('builds deterministic export filenames from export timestamps', () => {
    expect(accountExportFilename('2026-05-05T11:00:00+00:00')).toBe('tradingagents-export-2026-05-05.json');
  });
});

describe('cluster runtime frontend helpers', () => {
  it('warns only when cluster health is inconsistent', () => {
    expect(shouldShowClusterRuntimeWarning(null)).toBe(false);
    expect(shouldShowClusterRuntimeWarning({ status: 'ok', runtime_mode: 'local' })).toBe(false);
    expect(
      shouldShowClusterRuntimeWarning({
        status: 'ok',
        runtime_mode: 'production-cluster',
        storage_backend: 'sqlite',
        coordination_backend: 'memory',
        postgres_configured: false,
        redis_configured: false
      })
    ).toBe(true);
    expect(
      shouldShowClusterRuntimeWarning({
        status: 'ok',
        runtime_mode: 'production-cluster',
        storage_backend: 'postgres',
        coordination_backend: 'redis',
        postgres_configured: true,
        redis_configured: true
      })
    ).toBe(false);
  });
});

describe('workspace governance frontend helpers', () => {
  it('labels workspace roles and enforces role affordances', () => {
    expect(formatWorkspaceRoleLabel('owner')).toBe('所有者');
    expect(canManageWorkspaceMembers('admin')).toBe(true);
    expect(canManageWorkspaceMembers('member')).toBe(false);
    expect(canCreateWorkspaceResource('member')).toBe(true);
    expect(canCreateWorkspaceResource('viewer')).toBe(false);
  });

  it('builds workspace audit query filters without empty optional values', () => {
    expect(
      buildAuditQuery(3, {
        userId: '7',
        eventType: 'analysis.create',
        startAt: '2026-05-01T00:00:00+00:00',
        endAt: ''
      })
    ).toEqual({
      workspace_id: '3',
      user_id: '7',
      event_type: 'analysis.create',
      start_at: '2026-05-01T00:00:00+00:00'
    });
  });
});

describe('enterprise identity and retention frontend helpers', () => {
  it('builds OIDC authorization URLs without client secrets', () => {
    const url = buildOidcAuthorizeUrl({
      oidc_enabled: true,
      issuer_url: 'https://idp.example.com',
      authorization_endpoint: 'https://idp.example.com/authorize',
      client_id: 'tradingagents',
      redirect_uri: 'https://app.example.com/auth/oidc/callback',
      scope: 'openid email',
      group_claim: 'groups',
      mapped_groups: ['traders']
    });

    expect(url).toContain('response_type=code');
    expect(url).toContain('client_id=tradingagents');
    expect(url).not.toContain('secret');
  });

  it('requires explicit flags only for sensitive retention resource types', () => {
    expect(buildRetentionPolicy(3, 'analyses', '2026-01-01T00:00:00+00:00')).toEqual({
      workspace_id: 3,
      resource_type: 'analyses',
      cutoff_before: '2026-01-01T00:00:00+00:00',
      include_audit_logs: false,
      include_usage_ledger: false
    });
    expect(buildRetentionPolicy(3, 'usage_ledger', '2026-01-01T00:00:00+00:00', true).include_usage_ledger).toBe(true);
  });
});
