/**
 * Control Center type definitions (spec §38).
 *
 * These types compose with the existing backend response shapes from the
 * identity router (`/api/v1/control/*`, `/api/v1/admin/providers`), the
 * extensions router (`/api/v1/extensions`), and the connectors router
 * (`/api/v1/connectors`).  They never duplicate provider adapter internals.
 */

export type ConnectionStatus =
  | "connected"
  | "not_connected"
  | "expired"
  | "error"
  | "testing";

export type ProviderHealth = "healthy" | "degraded" | "unconfigured" | "unreachable";

export interface ProviderConnection {
  provider: string;
  display_name: string;
  connected: boolean;
  status: ConnectionStatus;
  capabilities: string[];
  model_count: number;
  detail: string;
  last_tested: string | null;
  expires_at: string | null;
  configured: boolean;
  health?: ProviderHealth;
  latency_ms?: number | null;
}

export interface ProviderSummary {
  total: number;
  connected: number;
  disconnected: number;
}

export interface CredentialRef {
  provider: string;
  display_name: string;
  key: string;
  label: string;
  status: "set" | "unset";
  source: "env" | "vault" | "override";
  identity_provider: boolean;
}

export type ExtensionStatus =
  | "ready"
  | "error"
  | "unconfigured"
  | "connected"
  | "disabled"
  | "available";

export type ConnectType = "oauth" | "api_key" | "local" | "none";

export interface ExtensionManifest {
  id: string;
  name: string;
  desc: string;
  category: string;
  icon: string;
  logo: string | null;
  installed: boolean;
  enabled: boolean;
  connected: boolean;
  status: ExtensionStatus;
  config: Record<string, unknown>;
  installed_at?: string | null;
  connected_at?: string | null;
  launch_url: string;
  connect_type: ConnectType;
  key_env: string | null;
  caps: string[];
}

export interface ExtensionCatalog {
  extensions: ExtensionManifest[];
  total: number;
}

export interface ConnectorConfig {
  kind: string;
  name: string;
  enabled: boolean;
  capabilities: string[];
  connected: boolean;
  host: string | null;
  port: number | null;
  username: string | null;
  password_set: boolean;
  encryption: string;
}

export interface ControlCenterStatus {
  providers: ProviderConnection[];
  provider_summary: ProviderSummary;
  extensions: {
    installed_count: number;
    connected_count: number;
  };
  connectors: {
    count: number;
  };
}

export interface TabConfig {
  id: string;
  label: string;
  icon: React.ElementType;
  short?: string;
}
