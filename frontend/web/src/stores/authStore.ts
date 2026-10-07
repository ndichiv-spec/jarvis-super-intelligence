import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { jarvisAPI } from '@/lib/api';
import { setAuthToken } from '@/lib/api-client';

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
  tenant_id: string;
  last_login_at?: string;
  created_at?: string;
  roles?: Array<{
    id: string;
    name: string;
    permissions: string[];
  }>;
}

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: User | null;
  isAuthenticated: boolean;
  login: (token: string | null, refreshToken: string | null, user: User) => void;
  logout: () => Promise<void>;
  updateUser: (updates: Partial<User>) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,

      login: (_token: string | null, _refreshToken: string | null, user: User) => {
        clearClientCredentials();
        set({
          token: null,
          refreshToken: null,
          user,
          isAuthenticated: true,
        });
      },

      logout: async () => {
        try {
          await jarvisAPI.logout();
        } catch (error) {
          console.error('Logout error:', error);
        }
        // Wipe both tokens from the in-memory API client AND persisted storage.
        clearClientCredentials();
        set({
          token: null,
          refreshToken: null,
          user: null,
          isAuthenticated: false,
        });
      },

      updateUser: (updates: Partial<User>) => {
        const { user } = get();
        if (user) {
          set({ user: { ...user, ...updates } });
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
        if (!state?.isAuthenticated) return;
        void jarvisAPI.getMe().then((user) => {
          useAuthStore.setState({ token: null, refreshToken: null, user, isAuthenticated: true });
        }).catch(() => {
          useAuthStore.setState({ token: null, refreshToken: null, user: null, isAuthenticated: false });
        });
      },
    }
  )
);
