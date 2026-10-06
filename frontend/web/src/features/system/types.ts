export interface SystemStatus {
  status: string;
  version: string;
  uptime: number;
  start_time: string;
  active_engines: string[];
  active_connections: number;
  memory_usage: number;
  cpu_usage: number;
}

export interface SystemProcess {
  pid: number;
  name: string;
  cpu_percent: number;
  memory_percent: number;
  status: string;
  created_at: string;
  username?: string;
}

export interface ProviderSettings {
  ollama_base_url: string;
  ollama_model: string;
  openai_api_key: string;
  google_gemini_api_key: string;
  anthropic_api_key: string;
  huggingface_api_key: string;
  stability_api_key: string;
  replicate_api_key: string;
  aws_access_key_id: string;
  aws_secret_access_key: string;
  aws_region: string;
  tavily_api_key: string;
  serper_api_key: string;
  news_api_key: string;
  openweathermap_api_key: string;
}

export interface ProviderFeatureStatus {
  label: string;
  summary: string;
  features: string[];
  configured: boolean;
}

export interface ProviderSettingsResponse {
  success: boolean;
  settings: ProviderSettings;
  providers: Record<string, ProviderFeatureStatus>;
  env_file_exists: boolean;
  env_path: string;
}

export interface FileInfo {
  name: string;
  path: string;
  size: number;
  type: string;
  modified_at: string;
  is_directory: boolean;
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

export interface ModelCatalogEntry {
  model_id: string;
  provider: string;
  category: string;
  max_tokens: number;
  available: boolean;
  provider_available: boolean;
  provider_authorized: boolean;
  provider_status: string;
}

export interface ProviderAvailability {
  [providerName: string]: {
    available?: boolean;
    authorized?: boolean;
    configured?: boolean;
    model?: string;
    models?: string[];
    endpoint?: string;
    status?: string;
    last_checked?: string;
    errors?: string | null;
  };
}

export interface ModelCatalog {
  timestamp: string;
  total_models: number;
  providers: ProviderAvailability;
  catalog: ModelCatalogEntry[];
  active_model: string | null;
  active_provider: string | null;
  provider_keys_configured: string[];
}

export interface ServiceState {
  name: string;
  status: string;
  reachable: boolean;
  endpoint?: string;
  host?: string;
  port?: number;
  path?: string;
  details: string | null;
}

export interface ServiceStatus {
  timestamp: string;
  overall_status: string;
  services: Record<string, ServiceState>;
}
