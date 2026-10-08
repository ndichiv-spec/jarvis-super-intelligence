import { ConnectionBanner } from "@/components/connection-banner";
import { DashboardShell } from "@/components/layout/dashboard-shell";

export default function LocationsLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <ConnectionBanner />
      <DashboardShell>{children}</DashboardShell>
    </>
  );
}
