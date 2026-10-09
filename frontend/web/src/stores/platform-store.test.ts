import { afterEach, describe, expect, it, vi } from 'vitest';
import { usePlatformStore } from './platform-store';

afterEach(() => {
  vi.unstubAllGlobals();
  usePlatformStore.setState({
    system: null,
    providers: [],
    providerSummary: { total: 0, connected: 0, disconnected: 0 },
  });
});

describe('platform system metrics', () => {
  it('does not turn a health-only response into zero-valued metrics', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ status: 'healthy' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    await usePlatformStore.getState().refreshSystem();

    expect(usePlatformStore.getState().system).toBeNull();
  });

  it('retains actual resource values from the backend metrics response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            cpu_percent: 38.5,
            memory: { percent: 61.2, available: 1024 * 1024 * 512 },
            disk: 44,
            processes: 24,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    );

    await usePlatformStore.getState().refreshSystem();

    expect(usePlatformStore.getState().system).toMatchObject({
      cpu_percent: 38.5,
      memory_percent: 61.2,
      memory_available_mb: 512,
      disk_percent: 44,
      processes: 24,
    });
  });

  it('loads real provider capability states through the same-origin API', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        providers: [
          {
            id: 'openai',
            name: 'OpenAI',
            configured: true,
            connected: false,
            status: 'CONFIGURED',
            capabilities: ['chat'],
          },
          {
            id: 'unconfigured',
            name: 'Unconfigured provider',
            configured: false,
            connected: false,
            status: 'NOT_CONFIGURED',
            capabilities: [],
          },
        ],
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await usePlatformStore.getState().refreshProviders();

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/integrations/providers?probe=false',
      { credentials: 'include' },
    );
    expect(usePlatformStore.getState().providers).toEqual([
      {
        provider: 'openai',
        display_name: 'OpenAI',
        connected: false,
        status: 'CONFIGURED',
        capabilities: ['chat'],
        configured: true,
      },
      {
        provider: 'unconfigured',
        display_name: 'Unconfigured provider',
        connected: false,
        status: 'NOT_CONFIGURED',
        capabilities: [],
        configured: false,
      },
    ]);
    expect(usePlatformStore.getState().providerSummary).toEqual({
      total: 2,
      connected: 0,
      disconnected: 2,
    });
  });
});
