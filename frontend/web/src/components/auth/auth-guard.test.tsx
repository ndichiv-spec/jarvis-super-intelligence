import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

const { replace, authErrorHandler, onAuthError, clearAuthToken } = vi.hoisted(() => ({
  replace: vi.fn(),
  authErrorHandler: { current: null as (() => void) | null },
  onAuthError: vi.fn((handler: () => void) => {
    authErrorHandler.current = handler;
  }),
  clearAuthToken: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace }),
}));

vi.mock('@/lib/api-client', () => ({
  onAuthError,
  clearAuthToken,
  setAuthToken: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  jarvisAPI: {
    getMe: vi.fn(),
    logout: vi.fn(),
    setToken: vi.fn(),
  },
}));

import { useAuthStore } from '@/stores/authStore';
import { jarvisAPI } from '@/lib/api';
import { AuthGuard } from './auth-guard';

const user = {
  id: 'user-1',
  email: 'person@example.test',
  username: 'person',
  status: 'active',
  tenant_id: 'tenant-1',
};

describe('AuthGuard', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    authErrorHandler.current = null;
    useAuthStore.setState({
      token: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
      authStatus: 'idle',
    });
  });

  it.each(['idle', 'checking'] as const)('withholds protected content while auth is %s', (authStatus) => {
    useAuthStore.setState({ user, isAuthenticated: true, authStatus });

    render(<AuthGuard><p>Protected content</p></AuthGuard>);

    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Checking your session');
    expect(replace).not.toHaveBeenCalled();
  });

  it('redirects an empty persisted session once rehydration finishes', async () => {
    useAuthStore.setState({ user: null, isAuthenticated: false, authStatus: 'idle' });

    render(<AuthGuard><p>Protected content</p></AuthGuard>);

    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/login'));
  });

  it('renders protected content after identity is authenticated', () => {
    useAuthStore.setState({ user, isAuthenticated: true, authStatus: 'authenticated' });

    render(<AuthGuard><p>Protected content</p></AuthGuard>);

    expect(screen.getByText('Protected content')).toBeInTheDocument();
  });

  it('verifies a fresh login instead of clearing it when persistence hydration is delayed', () => {
    useAuthStore.setState({ user, isAuthenticated: true, authStatus: 'authenticated' });
    vi.spyOn(useAuthStore.persist, 'hasHydrated').mockReturnValue(false);
    vi.useFakeTimers();

    render(<AuthGuard><p>Protected content</p></AuthGuard>);

    act(() => {
      vi.advanceTimersByTime(1_000);
    });

    expect(useAuthStore.getState()).toMatchObject({
      user,
      isAuthenticated: true,
      authStatus: 'checking',
    });
    expect(jarvisAPI.getMe).toHaveBeenCalledOnce();
    expect(clearAuthToken).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it('keeps protected content locked and offers retry when session verification is unavailable', () => {
    useAuthStore.setState({ user, isAuthenticated: true, authStatus: 'unavailable' });

    render(<AuthGuard><p>Protected content</p></AuthGuard>);

    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('We can’t verify your session');
    expect(screen.getByRole('alert'))
      .toHaveTextContent('Your workspace stays locked until your sign-in can be verified.');
    expect(replace).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Retry verification' }));
    expect(jarvisAPI.getMe).toHaveBeenCalledOnce();
  });

  it('shows a retrying state but does not expose content while verification is pending', () => {
    useAuthStore.setState({ user, isAuthenticated: true, authStatus: 'checking' });

    render(<AuthGuard><p>Protected content</p></AuthGuard>);

    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Checking your session');
    expect(screen.getByRole('button', { name: 'Verifying…' })).toBeDisabled();
  });

  it.each(['unauthenticated', 'authenticated', 'unavailable'] as const)('redirects %s sessions without a retained identity', (authStatus) => {
    useAuthStore.setState({ user: null, isAuthenticated: false, authStatus });

    render(<AuthGuard><p>Protected content</p></AuthGuard>);

    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
    expect(replace).toHaveBeenCalledWith('/login');
  });

  it('clears persisted auth and redirects when the API reports an auth error', () => {
    useAuthStore.setState({ user, isAuthenticated: true, authStatus: 'authenticated' });

    render(<AuthGuard><p>Protected content</p></AuthGuard>);
    authErrorHandler.current?.();

    const persistedAuth = JSON.parse(localStorage.getItem('jarvis-auth-storage') ?? '{}').state;
    expect(useAuthStore.getState()).toMatchObject({
      user: null,
      isAuthenticated: false,
      authStatus: 'unauthenticated',
    });
    expect(persistedAuth).toMatchObject({ user: null, isAuthenticated: false });
    expect(clearAuthToken).toHaveBeenCalled();
    expect(replace).toHaveBeenCalledWith('/login');
  });
});
