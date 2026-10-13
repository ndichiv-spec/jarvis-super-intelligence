'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { onAuthError, clearAuthToken } from '@/lib/api-client';
import { useAuthStore } from '@/stores/authStore';
import { usePlatformStore } from '@/stores/platform-store';
import { DashboardShell } from './dashboard-shell';

export function AuthenticatedShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  useEffect(() => {
    onAuthError(() => {
      clearAuthToken();
      useAuthStore.setState({
        token: null,
        refreshToken: null,
        user: null,
        isAuthenticated: false,
      });
      router.replace('/login');
    });

    const { setUser } = usePlatformStore.getState();
    const authUser = useAuthStore.getState().user;
    setUser({
      id: authUser?.id ?? null,
      email: authUser?.email ?? null,
      full_name: authUser?.full_name ?? null,
      roles: Array.isArray(authUser?.roles)
        ? authUser.roles.map((role) => typeof role === 'string' ? role : role.name)
        : [],
      isAuthenticated: Boolean(authUser),
    });
  }, [router]);

  return <DashboardShell>{children}</DashboardShell>;
}
