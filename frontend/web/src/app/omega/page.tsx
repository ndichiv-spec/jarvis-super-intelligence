import { FeatureNotConfiguredPage } from '@/components/feature-not-configured-page';

export default function OmegaPage() {
  return (
    <FeatureNotConfiguredPage
      title="OMEGA systems"
      summary="A consolidated view for autonomous operations and model orchestration."
      links={[
        { label: 'Agent inventory and tasks', href: '/dashboard/agents', description: 'View registered agents and backed task operations.' },
        { label: 'Monitoring', href: '/dashboard/monitoring', description: 'Review health signals returned by configured services.' },
        { label: 'Runtime status', href: '/dashboard/runtime-status', description: 'Inspect runtime status exposed by the platform.' },
      ]}
    />
  );
}
