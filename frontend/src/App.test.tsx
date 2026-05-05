import { describe, expect, it } from 'vitest';
import { buildEditableParamsFromTask, parseAnalystsInput } from './App';
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
