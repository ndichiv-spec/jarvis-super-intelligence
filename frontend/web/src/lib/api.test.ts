import { afterEach, describe, expect, it, vi } from 'vitest';
import { jarvisAPI } from './api';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('JARVIS API error handling', () => {
  it('bounds session verification and avoids retrying a slow auth check', async () => {
    const timeoutSpy = vi.spyOn(AbortSignal, 'timeout');
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ authenticated: true, user: { id: 'user-1' } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await jarvisAPI.getMe();

    expect(timeoutSpy).toHaveBeenCalledWith(5_000);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('extracts structured API messages and does not retry client errors', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        error: { code: 'AUTHENTICATION_ERROR', message: 'Authentication required.' },
      }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(jarvisAPI.getImageProviderStatus()).rejects.toThrow(
      'Authentication required.',
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('reads the real agent inventory and scheduler contract', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        agents: [{
          id: 'jarvis-core',
          name: 'Jarvis Core',
          role: 'coordinator',
          status: 'active',
          capabilities: ['chat'],
        }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        running: false,
        status: 'NOT_CONFIGURED',
        next_run: null,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        enabled: false,
        status: 'NOT_CONFIGURED',
        services: [],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }));

    vi.stubGlobal('fetch', fetchMock);

    const agents = await jarvisAPI.getAgents();
    expect(agents.agents[0]).toMatchObject({ id: 'jarvis-core', status: 'active' });

    const scheduler = await jarvisAPI.getSchedulerStatus();
    expect(scheduler.status).toBe('NOT_CONFIGURED');
    expect(scheduler.running).toBe(false);

    const tailoring = await jarvisAPI.getServiceTailoringStatus();
    expect(tailoring.status).toBe('NOT_CONFIGURED');
    expect(tailoring.enabled).toBe(false);
  });

  it('uses the real RBAC status enum and audit log schema', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        users: [{
          id: 'u-1',
          email: 'ops@example.com',
          username: 'ops',
          full_name: 'Ops Admin',
          roles: ['admin'],
          status: 'pending_authorization',
          created_at: '2024-01-01T00:00:00.000Z',
        }],
        total: 1,
        page: 1,
        per_page: 20,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        logs: [{
          id: 'a-1',
          actor_id: 'u-1',
          action: 'user_updated',
          resource_type: 'rbac',
          resource_id: 'u-1',
          timestamp: '2024-01-02T00:00:00.000Z',
        }],
        total: 1,
        page: 1,
        per_page: 20,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }));

    vi.stubGlobal('fetch', fetchMock);

    const users = await jarvisAPI.rbac.getUsers();
    expect(users.users[0].status).toBe('pending_authorization');

    const audit = await jarvisAPI.rbac.getAuditLogs();
    expect(audit.logs[0]).toMatchObject({ actor_id: 'u-1', timestamp: '2024-01-02T00:00:00.000Z' });
  });
});
