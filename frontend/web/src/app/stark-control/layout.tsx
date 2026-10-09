import { DashboardShell } from "@/components/layout/dashboard-shell";

export default function ShellLayout({ children }: { children: React.ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>;
}
