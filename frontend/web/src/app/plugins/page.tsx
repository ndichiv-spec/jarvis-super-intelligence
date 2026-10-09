import { FeatureNotConfiguredPage } from '@/components/feature-not-configured-page';

export default function PluginMarketplacePage() {
  return (
    <FeatureNotConfiguredPage
      title="Plugin catalog"
      summary="Browse and manage plugins after a trusted catalog and installation service are configured."
      links={[
        { label: 'Extensions', href: '/dashboard/extensions', description: 'Inspect integrations already registered with the platform.' },
        { label: 'Connections', href: '/dashboard/connections', description: 'Review connections that have a supported backend contract.' },
        { label: 'Capability readiness', href: '/dashboard/capabilities', description: 'See the platform capabilities reported by JARVIS.' },
      ]}
    />
  );
}
