import { describe, expect, it, vi } from 'vitest';
import { api } from './api';

describe('TradingAgents web API', () => {
  it('exposes a pause endpoint for analyses', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 7, status: 'paused', events: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    await api.pauseAnalysis('token-123', 7);

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/analyses/7/pause',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Bearer token-123' })
      })
    );
  });
});
