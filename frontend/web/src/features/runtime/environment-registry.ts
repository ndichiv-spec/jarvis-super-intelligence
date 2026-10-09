export type EnvironmentId =
  | 'conversation'
  | 'world'
  | 'visual'
  | 'voice'
  | 'tasks'
  | 'knowledge'
  | 'operations'
  | 'communications'
  | 'devices'
  | 'learning';

export type CapabilityAvailability =
  | 'available'
  | 'requires_permission'
  | 'requires_connector'
  | 'requires_provider'
  | 'coming_later';

export interface EnvironmentDefinition {
  id: EnvironmentId;
  name: string;
  description: string;
  route: string | null;
  category: 'core' | 'capability' | 'operational' | 'internal';
  availability: CapabilityAvailability;
  capabilities: string[];
  requirement?: string;
}

export const ENVIRONMENTS: readonly EnvironmentDefinition[] = [
  {
    id: 'conversation',
    name: 'Conversation',
    description: 'Talk with JARVIS and continue the current session.',
    route: '/',
    category: 'core',
    availability: 'available',
    capabilities: ['chat', 'session history', 'runtime tool activity'],
  },
  {
    id: 'world',
    name: 'World',
    description: 'Maps, authorized location, place search, and directions.',
    route: '/dashboard/geography',
    category: 'capability',
    availability: 'available',
    capabilities: ['OpenStreetMap view', 'one-shot browser location', 'configured geocoding', 'configured routing'],
  },
  {
    id: 'visual',
    name: 'Visual Studio',
    description: 'Image generation and visual tools available in this installation.',
    route: '/image-generation',
    category: 'capability',
    availability: 'available',
    capabilities: ['image generation interface'],
  },
  {
    id: 'voice',
    name: 'Voice',
    description: 'Voice interface; usable features depend on the configured voice service.',
    route: '/voice',
    category: 'capability',
    availability: 'available',
    capabilities: ['voice interface'],
    requirement: 'Voice provider and permissions may be required.',
  },
  {
    id: 'tasks',
    name: 'Tasks',
    description: 'Inspect backend-reported agent tasks and their real execution state.',
    route: '/dashboard/agents',
    category: 'capability',
    availability: 'available',
    capabilities: ['agent tasks'],
  },
  {
    id: 'knowledge',
    name: 'Knowledge',
    description: 'Search and inspect the connected knowledge environment.',
    route: '/knowledge-hub',
    category: 'capability',
    availability: 'available',
    capabilities: ['knowledge search'],
  },
  {
    id: 'operations',
    name: 'System status',
    description: 'Operational diagnostics and backend-reported platform state.',
    route: '/dashboard/runtime-status',
    category: 'operational',
    availability: 'available',
    capabilities: ['runtime status'],
  },
  {
    id: 'communications',
    name: 'Connectors',
    description: 'Configure and inspect authorized service connections.',
    route: '/dashboard/connections',
    category: 'capability',
    availability: 'available',
    capabilities: ['connector setup', 'OAuth connections', 'email connector configuration'],
    requirement: 'This is connector management; a unified inbox and calls interface is not connected.',
  },
  {
    id: 'devices',
    name: 'Devices',
    description: 'Observe or control devices only through explicitly authorized connectors.',
    route: null,
    category: 'capability',
    availability: 'requires_connector',
    capabilities: ['computer', 'phone', 'tablet'],
    requirement: 'No device-control connector is available in the frontend contract.',
  },
  {
    id: 'learning',
    name: 'Evolution',
    description: 'Live research, study, learning-path, and review APIs.',
    route: '/dashboard/bio-growth',
    category: 'internal',
    availability: 'available',
    capabilities: ['research ingestion', 'study', 'learning paths', 'spaced-repetition review'],
    requirement: 'Training, model evaluation, and deployment lineage are not reported by this environment.',
  },
] as const;

export function getEnvironment(id: EnvironmentId): EnvironmentDefinition {
  const definition = ENVIRONMENTS.find((environment) => environment.id === id);
  if (!definition) throw new Error(`Unknown JARVIS environment: ${id}`);
  return definition;
}

export function environmentForPath(pathname: string): EnvironmentDefinition {
  const match = [...ENVIRONMENTS]
    .filter((environment) => environment.route && environment.route !== '/')
    .sort((left, right) => (right.route?.length ?? 0) - (left.route?.length ?? 0))
    .find((environment) => pathname === environment.route || pathname.startsWith(`${environment.route}/`));

  if (match) return match;
  if (pathname === '/dashboard' || pathname.startsWith('/dashboard/')) return getEnvironment('operations');
  return getEnvironment('conversation');
}

export function availabilityLabel(availability: CapabilityAvailability): string {
  switch (availability) {
    case 'available': return 'Available';
    case 'requires_permission': return 'Permission required';
    case 'requires_connector': return 'Connector required';
    case 'requires_provider': return 'Provider required';
    case 'coming_later': return 'Not connected';
  }
}
