import { describe, expect, it } from 'vitest';
import {
  accountExportFilename,
  buildEditableParamsFromTask,
  buildAuditQuery,
  canCreateWorkspaceResource,
  canManageWorkspaceMembers,
  formatWorkspaceRoleLabel,
  parseAnalystsInput,
  shouldShowProductionSafetyWarning
} from './App';
import type { AnalysisTask } from './api';

describe('TradingAgents web frontend', () => {
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

  it('parses adjusted analyst input before submitting a new run', () => {
    expect(parseAnalystsInput('market, news, market')).toEqual(['market', 'news']);
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
    expect(buildMemoryOptionLabel(memory)).toBe('Market Analyst · SPY · 2026-05-01');
  });

  it('toggles selected memory ids deterministically', () => {
    expect(toggleMemoryId([1, 3], 2)).toEqual([1, 3, 2]);
    expect(toggleMemoryId([1, 3], 3)).toEqual([1]);
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

    expect(buildInterventionLabel(session)).toBe('#5 · Task 9 · Market Analyst · open');
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

describe('workspace governance frontend helpers', () => {
  it('labels workspace roles and enforces role affordances', () => {
    expect(formatWorkspaceRoleLabel('owner')).toBe('Owner');
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
