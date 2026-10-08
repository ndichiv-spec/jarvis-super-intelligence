import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { jarvisAPI } from '@/lib/api';
import { setAuthToken } from '@/lib/api-client';

function syncToken(token: string | null, refresh: string | null = null) {
  jarvisAPI.setToken(token || '');
  setAuthToken(token, refresh);
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
  login: (token: string, refreshToken: string | null, user: User) => void;
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

      login: (token: string, refreshToken: string | null, user: User) => {
        // Persist both tokens so the session outlives the 7-day access-token
        // TTL (silent refresh) instead of bouncing back to first login.
        syncToken(token, refreshToken);
        set({
          token,
          refreshToken,
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
        syncToken(null, null);
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
      partialize: (state) => ({
        token: state.token,
        refreshToken: state.refreshToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);

// Initialize the in-memory API client token from persisted storage on
// startup so protected requests are authenticated on first render.
if (typeof window !== 'undefined') {
  const state = useAuthStore.getState();
  if (state.token) {
    syncToken(state.token, state.refreshToken);
  }
}
