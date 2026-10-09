import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '@/lib/api-client';
import chatApi from '@/features/chat/api';
import { useChatStore } from '@/features/chat/store';
import {
  attachEndpointToSession,
  getDeviceIdentity,
  ensureActiveSession,
  heartbeatEndpoint,
  registerEndpoint,
} from './endpoint-client';
import type { PresentationCapabilities } from './presentation-contract';

vi.mock('@/features/chat/api', () => ({
  default: {
    getSessions: vi.fn(),
    createSession: vi.fn(),
  },
}));

vi.mock('@/features/chat/store', () => ({
  useChatStore: { getState: vi.fn() },
}));

describe('endpoint startup continuity', () => {
  const state = {
    currentSessionId: null as string | null,
    loadSession: vi.fn<(sessionId: string) => Promise<void>>(),
  };
  state.loadSession.mockImplementation(async (sessionId) => {
    state.currentSessionId = sessionId;
  });

  beforeEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
    state.currentSessionId = null;
    vi.mocked(useChatStore.getState).mockReturnValue(state as never);
  });

  it('keeps a stable browser identity without treating it as authorization', () => {
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'device-identity-1') });

    expect(getDeviceIdentity()).toBe('device-identity-1');
    expect(getDeviceIdentity()).toBe('device-identity-1');
  });

  it('restores the most recent owned conversation before going live', async () => {
    vi.mocked(chatApi.getSessions).mockResolvedValue({
      sessions: [{ session_id: 'existing-session' }],
      total: 1,
      offset: 0,
      limit: 1,
      has_more: false,
    });

    await expect(ensureActiveSession()).resolves.toBe('existing-session');
    expect(state.loadSession).toHaveBeenCalledWith('existing-session');
    expect(chatApi.createSession).not.toHaveBeenCalled();
  });

  it('creates a persistent conversation when the owner has none', async () => {
    vi.mocked(chatApi.getSessions).mockResolvedValue({
      sessions: [],
      total: 0,
      offset: 0,
      limit: 1,
      has_more: false,
    });
    vi.mocked(chatApi.createSession).mockResolvedValue({ id: 'new-session' });

    await expect(ensureActiveSession()).resolves.toBe('new-session');
    expect(state.loadSession).toHaveBeenCalledWith('new-session');
  });

  it('stores the server-issued credential and uses it for endpoint lifecycle calls', async () => {
    const endpointId = 'endpoint-1';
    const endpointToken = 'jep_endpoint-1.secret';
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({
      endpoint: {
        endpointId,
        runtimeVersion: '1.0',
        capabilities: {} as PresentationCapabilities,
        state: 'registered',
        connectivity: 'registered',
        securityState: 'authenticated',
        activeSessions: [],
        lastSeen: new Date().toISOString(),
      },
      endpointToken,
      runtimeCapabilities: {},
    } as never);

    await registerEndpoint(
      'device-1',
      { runtimeVersion: '1.0' } as PresentationCapabilities,
      'session-1',
    );
    await heartbeatEndpoint(endpointId);
    await attachEndpointToSession(endpointId, 'session-1');

    expect(sessionStorage.getItem(`jarvis-endpoint-token:${endpointId}`)).toBe(endpointToken);
    expect(post).toHaveBeenNthCalledWith(
      2,
      expect.any(String),
      {},
      { headers: { Authorization: `Bearer ${endpointToken}` }, retries: 0 },
    );
    expect(post).toHaveBeenNthCalledWith(
      3,
      expect.any(String),
      {},
      { headers: { Authorization: `Bearer ${endpointToken}` }, retries: 0 },
    );
  });
});
