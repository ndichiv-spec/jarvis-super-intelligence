"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { onAuthError, clearAuthToken } from "@/lib/api-client";
import { useAuthStore } from "@/stores/authStore";
import { usePlatformStore } from "@/stores/platform-store";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { ConnectionBanner } from "@/components/connection-banner";

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

    // Initialize the unified platform store:
    // sync user identity, fetch backend/system/metrics state, and
    // subscribe to real-time WebSocket events.
    const { refreshAll, subscribeToEvents, setUser } = usePlatformStore.getState();
    const authUser = useAuthStore.getState().user;
    if (authUser) {
      setUser({
        id: authUser.id,
        email: authUser.email,
        full_name: authUser.full_name ?? null,
        roles: Array.isArray(authUser.roles) ? authUser.roles.map((r) => typeof r === 'string' ? r : r.name) : [],
        isAuthenticated: true,
      });
    }
    refreshAll();
    const unsub = subscribeToEvents();

    return () => unsub();
  }, [router]);

  return (
    <>
      <ConnectionBanner />
      <DashboardShell>
        {children}
      </DashboardShell>
    </>
  );
}
