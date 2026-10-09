"use client";

import { useEffect } from "react";
import { useAuthStore } from "@/stores/authStore";
import { usePlatformStore } from "@/stores/platform-store";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { AuthGuard } from "@/components/auth/auth-guard";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <DashboardRuntime>{children}</DashboardRuntime>
    </AuthGuard>
  );
}

function DashboardRuntime({ children }: { children: React.ReactNode }) {
  const authStatus = useAuthStore((state) => state.authStatus);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const user = useAuthStore((state) => state.user);

  useEffect(() => {
    if (
      !isAuthenticated ||
      !user ||
      (authStatus !== "authenticated" && authStatus !== "unavailable")
    ) {
      return;
    }

    // Initialize the unified platform store:
    // sync user identity, fetch backend/system/metrics state, and
    // subscribe to real-time WebSocket events.
    const { setUser } = usePlatformStore.getState();
    setUser({
      id: user.id,
      email: user.email,
      full_name: user.full_name ?? null,
      roles: Array.isArray(user.roles) ? user.roles.map((r) => typeof r === 'string' ? r : r.name) : [],
      isAuthenticated: true,
    });
  }, [authStatus, isAuthenticated, user]);

  return (
    <DashboardShell>{children}</DashboardShell>
  );
}
