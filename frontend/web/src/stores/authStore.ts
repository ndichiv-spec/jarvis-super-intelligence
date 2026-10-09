import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { jarvisAPI } from '@/lib/api';
import { clearAuthToken, setAuthToken } from '@/lib/api-client';

function clearClientCredentials() {
  jarvisAPI.setToken('');
  setAuthToken(null, null);
}

export interface User {
  id: string;
  email: string;
  username: string;
  full_name?: string;
  avatar_url?: string;
  status: string;
  tenant_id: string | null;
  last_login_at?: string;
  created_at?: string;
  roles?: Array<string | {
    id?: string;
    name: string;
    permissions?: string[];
  }>;
}

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: User | null;
  isAuthenticated: boolean;
  authStatus: 'idle' | 'checking' | 'authenticated' | 'unauthenticated' | 'unavailable';
  login: (token: string | null, refreshToken: string | null, user: User) => void;
  logout: () => Promise<void>;
  updateUser: (updates: Partial<User>) => void;
  retrySessionCheck: () => Promise<void>;
  handleConnectivityChange: (online: boolean) => void;
}

let sessionCheckGeneration = 0;

export function clearAuthState() {
  sessionCheckGeneration += 1;
  clearClientCredentials();
  clearAuthToken();
  useAuthStore.setState({
    token: null,
    refreshToken: null,
    user: null,
    isAuthenticated: false,
    authStatus: 'unauthenticated',
  });
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
      authStatus: 'idle',

      login: (_token: string | null, _refreshToken: string | null, user: User) => {
        sessionCheckGeneration += 1;
        clearClientCredentials();
        clearAuthToken();
        set({
          token: null,
          refreshToken: null,
          user,
          isAuthenticated: true,
          authStatus: 'authenticated',
        });
      },

      logout: async () => {
        sessionCheckGeneration += 1;
        try {
          await jarvisAPI.logout();
        } catch (error) {
          console.error('Logout error:', error);
        }
        // Wipe both tokens from the in-memory API client AND persisted storage.
        clearClientCredentials();
        clearAuthToken();
        set({
          token: null,
          refreshToken: null,
          user: null,
          isAuthenticated: false,
          authStatus: 'unauthenticated',
        });
      },

      updateUser: (updates: Partial<User>) => {
        const { user } = get();
        if (user) {
          set({ user: { ...user, ...updates } });
        }
      },

      retrySessionCheck: async () => {
        const generation = ++sessionCheckGeneration;
        set({ authStatus: 'checking' });
        try {
          const response = await jarvisAPI.getMe();
          if (generation !== sessionCheckGeneration) return;

          const payload = response && typeof response === 'object'
            ? response as Record<string, unknown>
            : null;
          if (payload?.authenticated === false) {
            clearAuthState();
            return;
          }

          const user = payload?.user && typeof payload.user === 'object'
            ? payload.user
            : payload;
          if (!user || typeof user !== 'object') {
            set({ authStatus: 'unavailable' });
            return;
          }

          set({
            token: null,
            refreshToken: null,
            user: user as User,
            isAuthenticated: true,
            authStatus: 'authenticated',
          });
        } catch (error) {
          if (generation !== sessionCheckGeneration) return;
          const status = error && typeof error === 'object' && 'status' in error
            ? Number((error as { status: unknown }).status)
            : null;
          if (status === 401 || status === 403) {
            clearAuthState();
            return;
          }

          // Keep the persisted identity on transient transport/server failures.
          set({ authStatus: 'unavailable' });
        }
      },

      handleConnectivityChange: (online) => {
        const { authStatus, isAuthenticated, user, retrySessionCheck } = get();
        if (!online && authStatus === 'checking') {
          sessionCheckGeneration += 1;
          set({ authStatus: 'unavailable' });
          return;
        }

        if (online && isAuthenticated && user && authStatus === 'unavailable') {
          void retrySessionCheck();
        }
      },
    }),
    {
      name: 'jarvis-auth-storage',
      version: 2,
      migrate: (persistedState) => {
        const state = persistedState as Partial<AuthState> | undefined;
        return {
          token: null,
          refreshToken: null,
          user: state?.user ?? null,
          isAuthenticated: state?.isAuthenticated ?? false,
        };
      },
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
      onRehydrateStorage: () => (state) => {
        clearClientCredentials();
        if (!state?.isAuthenticated) {
          useAuthStore.setState({ authStatus: 'unauthenticated' });
          return;
        }
        void state.retrySessionCheck();
      },
    }
  )
);
