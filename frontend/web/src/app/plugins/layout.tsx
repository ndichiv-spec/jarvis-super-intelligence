import { DashboardShell } from "@/components/layout/dashboard-shell";

export default function PluginsLayout({ children }: { children: React.ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>;
}
