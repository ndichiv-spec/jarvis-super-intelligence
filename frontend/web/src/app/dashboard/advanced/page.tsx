import { FeatureNotConfiguredPage } from '@/components/feature-not-configured-page';

export default function AdvancedDashboardPage() {
  return (
    <FeatureNotConfiguredPage
      title="Advanced systems"
      summary="Advanced model, goal, and self-management controls are shown only when their services provide live data and actions."
      links={[
        { label: 'Agent inventory and tasks', href: '/dashboard/agents', description: 'Review agents and task execution backed by the API.' },
        { label: 'Monitoring', href: '/dashboard/monitoring', description: 'Inspect available monitoring signals without simulated values.' },
        { label: 'Capability readiness', href: '/dashboard/capabilities', description: 'See capabilities reported by the platform.' },
      ]}
    />
  );
}
