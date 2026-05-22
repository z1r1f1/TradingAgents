import { describe, expect, it, vi } from 'vitest';
import { api, AUTH_EXPIRED_EVENT } from './api';

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

  it('searches A-share stocks through the backend proxy', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [{ code: '603386', name: '骏亚科技', ticker: '603386.SS', market: '沪A' }] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await api.searchStocks('token-123', '骏亚');

    expect(result.items[0].ticker).toBe('603386.SS');
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/stock-search?query=%E9%AA%8F%E4%BA%9A',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer token-123' })
      })
    );
  });

  it('emits an auth-expired event when an authenticated request receives 401', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'token expired' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' }
      })
    );
    vi.stubGlobal('fetch', fetchMock);
    const listener = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, listener);

    await expect(api.listAnalyses('expired-token')).rejects.toThrow('token expired');

    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(AUTH_EXPIRED_EVENT, listener);
  });
});
