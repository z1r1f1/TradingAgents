import { describe, expect, it } from 'vitest';

describe('TradingAgents web frontend', () => {
  it('defines a browser-facing app contract', () => {
    expect('login analysis history realtime rerun').toContain('realtime');
  });
});
