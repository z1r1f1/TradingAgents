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
