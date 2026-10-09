import { API_ENDPOINTS } from '@/config/api';
import { apiClient } from '@/lib/api-client';
import chatApi from '@/features/chat/api';
import { useChatStore } from '@/features/chat/store';
import type { PresentationCapabilities, RendererNegotiation } from './presentation-contract';

const DEVICE_IDENTITY_KEY = 'jarvis-endpoint-identity';
const ENDPOINT_TOKEN_KEY_PREFIX = 'jarvis-endpoint-token:';

export interface RegisteredEndpoint {
  endpointId: string;
  runtimeVersion: string | null;
  capabilities: PresentationCapabilities;
  state: 'registered' | 'connecting' | 'connected' | 'disconnected' | 'unauthorized' | 'unhealthy';
  connectivity: RegisteredEndpoint['state'];
  securityState: 'authenticated';
  activeSessions: string[];
  lastSeen: string;
}

export interface EndpointRegistrationResponse {
  endpoint: RegisteredEndpoint;
  endpointToken: string;
  runtimeCapabilities: RendererNegotiation;
}

let activeSessionBootstrap: Promise<string> | null = null;

export function getDeviceIdentity(): string {
  let identity = localStorage.getItem(DEVICE_IDENTITY_KEY);
  if (identity) return identity;
  if (!globalThis.crypto?.randomUUID) {
    throw new Error('This browser cannot create a persistent JARVIS endpoint identity.');
  }
  identity = globalThis.crypto.randomUUID();
  localStorage.setItem(DEVICE_IDENTITY_KEY, identity);
  return identity;
}

export function ensureActiveSession(): Promise<string> {
  const existingSessionId = useChatStore.getState().currentSessionId;
  if (existingSessionId) return Promise.resolve(existingSessionId);
  if (activeSessionBootstrap) return activeSessionBootstrap;

  activeSessionBootstrap = (async () => {
    const { sessions } = await chatApi.getSessions({ limit: 1, include_archived: false });
    const sessionId = sessions[0]?.session_id ?? (await chatApi.createSession()).id;
    await useChatStore.getState().loadSession(sessionId);
    if (useChatStore.getState().currentSessionId !== sessionId) {
      throw new Error('The active JARVIS conversation could not be restored.');
    }
    return sessionId;
  })().finally(() => {
    activeSessionBootstrap = null;
  });

  return activeSessionBootstrap;
}

export function registerEndpoint(
  deviceIdentity: string,
  capabilities: PresentationCapabilities,
  sessionId: string,
): Promise<EndpointRegistrationResponse> {
  return apiClient.post<EndpointRegistrationResponse>(API_ENDPOINTS.endpoints.register, {
    deviceIdentity,
    runtimeVersion: capabilities.runtimeVersion,
    capabilities,
    sessionId,
  }).then((response) => {
    if (!response.endpointToken) {
      throw new Error('The endpoint registration did not issue an endpoint credential.');
    }
    sessionStorage.setItem(
      `${ENDPOINT_TOKEN_KEY_PREFIX}${response.endpoint.endpointId}`,
      response.endpointToken,
    );
    return response;
  });
}

export function heartbeatEndpoint(endpointId: string): Promise<void> {
  const token = getEndpointToken(endpointId);
  return apiClient.post<{ endpoint: RegisteredEndpoint }>(
    API_ENDPOINTS.endpoints.heartbeat(endpointId),
    {},
    { headers: { Authorization: `Bearer ${token}` }, retries: 0 },
  ).then(() => undefined);
}

export function attachEndpointToSession(endpointId: string, sessionId: string): Promise<void> {
  const token = getEndpointToken(endpointId);
  return apiClient.post<{ endpoint: RegisteredEndpoint }>(
    API_ENDPOINTS.endpoints.attachSession(endpointId, sessionId),
    {},
    { headers: { Authorization: `Bearer ${token}` }, retries: 0 },
  ).then(() => undefined);
}

function getEndpointToken(endpointId: string): string {
  const token = sessionStorage.getItem(`${ENDPOINT_TOKEN_KEY_PREFIX}${endpointId}`);
  if (!token) {
    throw new Error('The endpoint must authenticate again before using its connection.');
  }
  return token;
}
