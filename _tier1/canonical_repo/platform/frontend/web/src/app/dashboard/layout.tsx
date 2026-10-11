"use client";

import { AuthenticatedShell } from '@/components/layout/authenticated-shell';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return <AuthenticatedShell>{children}</AuthenticatedShell>;
}
