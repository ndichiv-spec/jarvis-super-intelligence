import { FeatureNotConfiguredPage } from '@/components/feature-not-configured-page';

export default function OperationalDashboardPage() {
  return (
    <FeatureNotConfiguredPage
      title="Operational overview"
      summary="The overview stays quiet until health, model, memory, and agent services return verified operational data."
      links={[
        { label: 'Monitoring', href: '/dashboard/monitoring', description: 'Open service health and monitoring data.' },
        { label: 'System', href: '/dashboard/system', description: 'Review system metrics that are actually reported.' },
        { label: 'Runtime status', href: '/dashboard/runtime-status', description: 'Inspect current runtime status.' },
      ]}
    />
  );
}
