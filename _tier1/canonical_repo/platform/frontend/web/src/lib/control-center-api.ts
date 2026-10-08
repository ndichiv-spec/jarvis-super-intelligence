/**
 * Control Center API wrappers.
 *
 * All calls go through the existing `apiClient` (from `lib/api-client`) so that
 * 401 / token-refresh handling and `AuthError` propagation work consistently.
 * No raw secrets are ever requested or returned by these wrappers.
 */
import { apiClient } from "@/lib/api-client";
import type {
  ControlCenterStatus,
  CredentialRef,
  ExtensionCatalog,
  ExtensionManifest,
  ProviderConnection,
} from "@/lib/types/control-center";

export interface ControlCenterApi {
  /** Merged overview: providers, extensions, connectors. */
  getStatus: () => Promise<ControlCenterStatus>;
  /** Credential references only — no secret values. */
  getCredentials: () => Promise<CredentialRef[]>;
  /** Full provider connection list. */
  getProviders: () => Promise<ProviderConnection[]>;
  /** Test a single provider connection (health probe). */
  testProvider: (providerId: string) => Promise<{ provider: string; status: string; connected: boolean; detail: string; timestamp: number }>;
  /** Disconnect a provider (clears credential override / OAuth link). */
  disconnectProvider: (providerId: string) => Promise<{ provider: string; ok: boolean; action: string; timestamp: number }>;
  /** Connect / rotate a provider credential. */
  connectProvider: (providerId: string) => Promise<{ provider: string; ok: boolean; vault_key: string; detail: string; timestamp: number; auth_url_hint: string | null }>;
  /** Extension marketplace catalog. */
  getExtensions: () => Promise<ExtensionCatalog>;
  /** Install an extension. */
  installExtension: (extId: string) => Promise<Record<string, unknown>>;
  /** Connect an extension (starts OAuth or API-key flow). */
  connectExtension: (extId: string, apiKey?: string) => Promise<Record<string, unknown>>;
  /** Toggle extension enabled state. */
  updateExtension: (extId: string, patch: { enabled?: boolean; connected?: boolean }) => Promise<Record<string, unknown>>;
  /** Launch an extension's web interface. */
  launchExtension: (extId: string) => Promise<Record<string, unknown>>;
}

export const controlCenterApi: ControlCenterApi = {
  getStatus: async () => {
    return apiClient.get<ControlCenterStatus>("/api/v1/control/status");
  },

  getCredentials: async () => {
    return apiClient.get<CredentialRef[]>("/api/v1/control/credentials");
  },

  getProviders: async () => {
    return apiClient.get<ProviderConnection[]>("/api/v1/admin/providers");
  },

  testProvider: async (providerId: string) => {
    return apiClient.post<{ provider: string; status: string; connected: boolean; detail: string; timestamp: number }>(
      `/api/v1/providers/${providerId}/test`
    );
  },

  disconnectProvider: async (providerId: string) => {
    return apiClient.delete<{ provider: string; ok: boolean; action: string; timestamp: number }>(
      `/api/v1/providers/${providerId}`
    );
  },

  connectProvider: async (providerId: string) => {
    return apiClient.post<{ provider: string; ok: boolean; vault_key: string; detail: string; timestamp: number; auth_url_hint: string | null }>(
      `/api/v1/admin/providers/${providerId}/connect`
    );
  },

  getExtensions: async () => {
    return apiClient.get<ExtensionCatalog>("/api/v1/extensions");
  },

  installExtension: async (extId: string) => {
    return apiClient.post("/api/v1/extensions/install", { extension_id: extId });
  },

  connectExtension: async (extId: string, apiKey?: string) => {
    const body: { api_key?: string } = {};
    if (apiKey) body.api_key = apiKey;
    return apiClient.post(`/api/v1/extensions/${extId}/connect`, body);
  },

  updateExtension: async (extId: string, patch: { enabled?: boolean; connected?: boolean }) => {
    return apiClient.patch(`/api/v1/extensions/${extId}`, patch);
  },

  launchExtension: async (extId: string) => {
    return apiClient.post(`/api/v1/extensions/${extId}/launch`);
  },
};
