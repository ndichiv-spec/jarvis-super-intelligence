import { FeatureNotConfiguredPage } from '@/components/feature-not-configured-page';

export default function UpgradePage() {
  return (
    <FeatureNotConfiguredPage
      title="Software upgrades"
      summary="Review and apply platform or package updates when an authorized updater is connected."
      links={[
        { label: 'System status', href: '/dashboard/system-status', description: 'Review the system information currently reported by JARVIS.' },
        { label: 'Connections', href: '/dashboard/connections', description: 'Inspect configured services and their reported connectivity.' },
      ]}
    />
  );
}
