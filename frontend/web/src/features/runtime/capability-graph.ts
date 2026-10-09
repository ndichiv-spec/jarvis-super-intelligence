import type { SystemCapability } from '@/features/system/types';
import type { ProviderStatus } from '@/lib/types/platform';

export interface RuntimeCapability {
  id: string;
  category: string;
  tool: string;
  permissions: string[];
  provider: string | null;
  providerService: string;
  model: string | null;
  availability: SystemCapability['availability'];
  health: SystemCapability['health'];
  aiBacked: boolean;
}

export interface RuntimeIntegration {
  id: string;
  name: string;
  connected: boolean;
  configured: boolean;
  status: string;
  capabilities: string[];
  modelCount?: number;
}

export function mapCapabilities(registry: SystemCapability[] | undefined): RuntimeCapability[] {
  if (!registry) return [];
  return registry.map((item) => ({
    id: item.capability,
    category: item.category,
    tool: item.tool,
    permissions: item.permissions,
    provider: item.provider,
    providerService: item.provider_service,
    model: item.model,
    availability: item.availability,
    health: item.health,
    aiBacked: item.ai_backed,
  }));
}

export function mapIntegrations(providers: ProviderStatus[]): RuntimeIntegration[] {
  return providers.map((provider) => ({
    id: provider.provider,
    name: provider.display_name,
    connected: provider.connected,
    configured: provider.configured,
    status: provider.status,
    capabilities: provider.capabilities,
    ...(provider.model_count !== undefined ? { modelCount: provider.model_count } : {}),
  }));
}
