import { FeatureNotConfiguredPage } from '@/components/feature-not-configured-page';

export default function SupremePage() {
  return (
    <FeatureNotConfiguredPage
      title="Supreme intelligence"
      summary="This experimental surface has been replaced with a direct path to JARVIS capabilities that are currently connected."
      links={[
        { label: 'Conversation workspace', href: '/', description: 'Continue in the primary JARVIS conversation experience.' },
        { label: 'Agent inventory and tasks', href: '/dashboard/agents', description: 'Inspect registered agents and available task operations.' },
        { label: 'Model connections', href: '/dashboard/connections', description: 'Review configured provider and service connections.' },
      ]}
    />
  );
}
