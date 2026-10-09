import { FeatureNotConfiguredPage } from '@/components/feature-not-configured-page';

export default function Phase3Page() {
  return (
    <FeatureNotConfiguredPage
      title="Advanced systems"
      summary="Training, dataset management, and plugin orchestration require dedicated backend services."
      links={[
        { label: 'Knowledge', href: '/dashboard/knowledge', description: 'Browse knowledge available through the configured API.' },
        { label: 'Extensions', href: '/dashboard/extensions', description: 'Inspect integrations registered with JARVIS.' },
        { label: 'Agents & tasks', href: '/dashboard/agents', description: 'Work with the available agent and task APIs.' },
      ]}
    />
  );
}
