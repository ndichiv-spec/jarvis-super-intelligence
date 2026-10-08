"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { onAuthError, clearAuthToken } from "@/lib/api-client";
import { useAuthStore } from "@/stores/authStore";
import { usePlatformStore } from "@/stores/platform-store";
import { DashboardShell } from "@/components/layout/dashboard-shell";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  useEffect(() => {
    // Any 401 from the API while inside the dashboard -> clear the stale
    // token (both the in-memory zustand store AND the persisted localStorage
    // AND the api-client in-memory token) and redirect to login so the
    // user sees the sign-in form instead of a redirect loop.
    onAuthError(() => {
      clearAuthToken();
      // Synchronously clear the zustand persist store so the login page
      // sees isAuthenticated === false and shows the sign-in form.
      useAuthStore.setState({
        token: null,
        refreshToken: null,
        user: null,
        isAuthenticated: false,
      });
      router.replace("/login");
    });

    // Keep the shell's shared identity in sync. The dashboard shell owns
    // runtime refresh and the single monitoring-event subscription.
    const { setUser } = usePlatformStore.getState();
    const authUser = useAuthStore.getState().user;
    setUser({
      id: authUser?.id ?? null,
      email: authUser?.email ?? null,
      full_name: authUser?.full_name ?? null,
      roles: Array.isArray(authUser?.roles) ? authUser.roles.map((r) => typeof r === 'string' ? r : r.name) : [],
      isAuthenticated: Boolean(authUser),
    });
  }, [router]);

  return (
    <DashboardShell>{children}</DashboardShell>
  );
}
