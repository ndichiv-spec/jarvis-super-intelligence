export interface VersionInfo {
  version: string;
  buildNumber: number;
  releaseDate: Date;
  changelog: unknown[];
  critical: boolean;
  breaking: boolean;
  downloadUrl: string;
  checksum: string;
  size: number;
  dependencies: unknown[];
  codename: string;
  milestone: string;
  changes: string[];
}

export interface TierInfo {
  tier: number;
  name: string;
  level: string;
  features: string[];
  price: number;
  limits: Record<string, number>;
}

export interface SystemCapability {
  capability: string;
  category: string;
  tool: string;
  permissions: string[];
  provider: string | null;
  provider_service: string;
  model: string | null;
  availability: 'available' | 'unavailable';
  health: 'ok' | 'degraded' | 'offline';
  ai_backed: boolean;
}

export interface SystemCapabilities {
  version: string;
  engines: string[];
  features: string[];
  tier_level: number;
  active_providers: string[];
  capabilities?: string[];
  registry?: SystemCapability[];
  ai_enabled?: boolean;
  providers?: { ai_enabled: boolean; configured: string[] };
  timestamp?: string;
}

export type AsyncStatus = 'idle' | 'loading' | 'success' | 'error';
