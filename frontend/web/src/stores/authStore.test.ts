import { beforeEach, describe, expect, it, vi } from 'vitest';
import { waitFor } from '@testing-library/react';

const { getMe, setToken, setAuthToken, clearAuthToken } = vi.hoisted(() => ({
  getMe: vi.fn(),
  setToken: vi.fn(),
  setAuthToken: vi.fn(),
  clearAuthToken: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  jarvisAPI: {
    getMe,
    setToken,
    logout: vi.fn(),
  },
}));

vi.mock('@/lib/api-client', () => ({
  setAuthToken,
  clearAuthToken,
}));

import { jarvisAPI } from '@/lib/api';
import { useAuthStore } from './authStore';

const cachedUser = {
  id: 'user-1',
  email: 'user@example.test',
  username: 'user',
  status: 'active',
  tenant_id: 'tenant-1',
};

function persistAuthenticatedUser() {
  localStorage.setItem('jarvis-auth-storage', JSON.stringify({
    state: { user: cachedUser, isAuthenticated: true },
    version: 2,
  }));
}

describe('cookie-authenticated session rehydration', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    useAuthStore.setState({
      token: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
      authStatus: 'idle',
    });
  });

  it('keeps the persisted session when the server is temporarily unavailable', async () => {
    persistAuthenticatedUser();
    vi.mocked(jarvisAPI.getMe).mockRejectedValueOnce(Object.assign(new Error('Service unavailable'), { status: 503 }));

    await useAuthStore.persist.rehydrate();

    await waitFor(() => expect(useAuthStore.getState().authStatus).toBe('unavailable'));
    expect(useAuthStore.getState().authStatus).toBe('unavailable');
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().user).toEqual(cachedUser);
  });

  it.each([401, 403])('clears the persisted session on confirmed HTTP %s', async (status) => {
    persistAuthenticatedUser();
    vi.mocked(jarvisAPI.getMe).mockRejectedValueOnce(Object.assign(new Error('Session rejected'), { status }));

    await useAuthStore.persist.rehydrate();

    await waitFor(() => expect(useAuthStore.getState().authStatus).toBe('unauthenticated'));
    expect(useAuthStore.getState().authStatus).toBe('unauthenticated');
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().user).toBeNull();
  });

  it('replaces cached identity with the user returned by the session endpoint', async () => {
    const verifiedUser = { ...cachedUser, username: 'verified-user' };
    persistAuthenticatedUser();
    vi.mocked(jarvisAPI.getMe).mockResolvedValueOnce({ authenticated: true, user: verifiedUser });

    await useAuthStore.persist.rehydrate();

    await waitFor(() => expect(useAuthStore.getState().authStatus).toBe('authenticated'));
    expect(useAuthStore.getState().authStatus).toBe('authenticated');
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().user).toEqual(verifiedUser);
  });

  it('does not call the session endpoint when there is no persisted identity', async () => {
    await useAuthStore.persist.rehydrate();

    expect(useAuthStore.getState().authStatus).toBe('unauthenticated');
    expect(jarvisAPI.getMe).not.toHaveBeenCalled();
  });

  it('restores a failed verification when the browser comes back online', async () => {
    useAuthStore.setState({
      user: cachedUser,
      isAuthenticated: true,
      authStatus: 'checking',
    });

    useAuthStore.getState().handleConnectivityChange(false);
    expect(useAuthStore.getState().authStatus).toBe('unavailable');

    vi.mocked(jarvisAPI.getMe).mockResolvedValueOnce({ authenticated: true, user: cachedUser });
    useAuthStore.getState().handleConnectivityChange(true);

    await waitFor(() => expect(useAuthStore.getState().authStatus).toBe('authenticated'));
    expect(jarvisAPI.getMe).toHaveBeenCalledOnce();
  });
});
