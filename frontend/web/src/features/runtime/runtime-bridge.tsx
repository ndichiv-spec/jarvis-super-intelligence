'use client';

import { useEffect } from 'react';
import { API_ENDPOINTS } from '@/config/api';
import { ApiClientError, apiClient } from '@/lib/api-client';
import { useChatStore } from '@/features/chat/store';
import {
  attachEndpointToSession,
  ensureActiveSession,
  getDeviceIdentity,
  heartbeatEndpoint,
  registerEndpoint,
} from './endpoint-client';
import { useSystemStore } from '@/features/system/store';
import { useAuthStore } from '@/stores/authStore';
import { usePlatformStore } from '@/stores/platform-store';
import { startRuntimeEventAdapter } from './runtime-event-adapter';
import { useJarvisRuntime } from './store';
import type {
  PresentationCapabilities,
  PresentationContractMetadata,
} from './presentation-contract';

const PRESENTATION_CAPABILITIES: PresentationCapabilities = {
  clientId: 'jarvis-web',
  runtimeVersion: '1.0',
  platform: 'web',
  surfaces: ['web'],
  renderers: ['text.renderer', 'status.renderer', 'map.renderer'],
  environments: ['conversation', 'geospatial'],
  primitives: ['text', 'status', 'map', 'marker', 'control'],
  media: [],
  spatial: [],
  input: ['text', 'zoom', 'pan', 'recenter'],
  output: ['text'],
  performanceProfile: 'balanced',
  accessibility: {
    reducedMotion: typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  },
};

export function RuntimeBridge() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const systemCapabilities = useSystemStore((state) => state.capabilities);
  const loadCapabilities = useSystemStore((state) => state.loadCapabilities);
  const providers = usePlatformStore((state) => state.providers);
  const refreshProviders = usePlatformStore((state) => state.refreshProviders);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const messages = useChatStore((state) => state.messages);
  const isLoading = useChatStore((state) => state.isLoading);
  const isStreaming = useChatStore((state) => state.isStreaming);
  const setSessionId = useJarvisRuntime((state) => state.setSessionId);
  const voiceState = useJarvisRuntime((state) => state.voiceState);
  const setVoiceState = useJarvisRuntime((state) => state.setVoiceState);
  const syncCapabilityRegistry = useJarvisRuntime((state) => state.syncCapabilityRegistry);
  const syncIntegrations = useJarvisRuntime((state) => state.syncIntegrations);
  const setRendererNegotiation = useJarvisRuntime((state) => state.setRendererNegotiation);
  const setRendererNegotiationError = useJarvisRuntime((state) => state.setRendererNegotiationError);
  const applyPresentation = useJarvisRuntime((state) => state.applyPresentation);
  const applyRuntimeSnapshot = useJarvisRuntime((state) => state.applyRuntimeSnapshot);
  const applyRuntimeEvent = useJarvisRuntime((state) => state.applyRuntimeEvent);
  const setRuntimeEventError = useJarvisRuntime((state) => state.setRuntimeEventError);
  const setEndpointStatus = useJarvisRuntime((state) => state.setEndpointStatus);
  const endpointId = useJarvisRuntime((state) => state.endpointId);
  const endpointStatus = useJarvisRuntime((state) => state.endpointStatus);

  useEffect(() => {
    setSessionId(currentSessionId);
  }, [currentSessionId, setSessionId]);

  useEffect(() => {
    syncCapabilityRegistry(systemCapabilities?.registry, systemCapabilities?.timestamp);
  }, [systemCapabilities, syncCapabilityRegistry]);

  useEffect(() => {
    syncIntegrations(providers);
  }, [providers, syncIntegrations]);

  useEffect(() => {
    if (!isAuthenticated) return;
    void loadCapabilities();
    void refreshProviders();
  }, [isAuthenticated, loadCapabilities, refreshProviders]);

  useEffect(() => {
    if (!isAuthenticated || !currentSessionId || !endpointId || endpointStatus !== 'connected') return;
    setRuntimeEventError(null);
    return startRuntimeEventAdapter(currentSessionId, endpointId, {
      onSnapshot: applyRuntimeSnapshot,
      onEvent: applyRuntimeEvent,
      onError: (error) => setRuntimeEventError(error.message),
    });
  }, [
    applyRuntimeEvent,
    applyRuntimeSnapshot,
    currentSessionId,
    endpointId,
    endpointStatus,
    isAuthenticated,
    setRuntimeEventError,
  ]);

  useEffect(() => {
    if (!isAuthenticated) {
      setEndpointStatus('unregistered', null);
      return;
    }
    let active = true;
    let heartbeatTimer: ReturnType<typeof setInterval> | undefined;
    let heartbeatInFlight = false;
    setEndpointStatus('connecting', null);
    void (async () => {
      const contract = await apiClient.get<PresentationContractMetadata>(
        API_ENDPOINTS.presentation.contract,
      );
      const majorVersion = Number(contract.version.split('.')[0]);
      if (contract.protocol !== 'jarvis.presentation' || majorVersion !== 1) {
        throw new Error(`Unsupported JARVIS presentation contract version: ${contract.version}.`);
      }
      const sessionId = await ensureActiveSession();
      const registration = await registerEndpoint(
        getDeviceIdentity(),
        PRESENTATION_CAPABILITIES,
        sessionId,
      );
      if (!active) return;
      setRendererNegotiation(registration.runtimeCapabilities);
      await heartbeatEndpoint(registration.endpoint.endpointId);
      await attachEndpointToSession(registration.endpoint.endpointId, sessionId);
      if (!active) return;
      setEndpointStatus('connected', registration.endpoint.endpointId);
      heartbeatTimer = setInterval(() => {
        if (!active || heartbeatInFlight) return;
        heartbeatInFlight = true;
        void heartbeatEndpoint(registration.endpoint.endpointId)
          .then(() => {
            if (active) setEndpointStatus('connected', registration.endpoint.endpointId);
          })
          .catch((error: unknown) => {
            if (active) {
              const status = error instanceof ApiClientError && (error.status === 401 || error.status === 403)
                ? 'unauthorized'
                : error instanceof ApiClientError
                  ? 'unhealthy'
                  : 'disconnected';
              setEndpointStatus(
                status,
                registration.endpoint.endpointId,
                error instanceof Error ? error.message : 'JARVIS endpoint heartbeat failed.',
              );
            }
          })
          .finally(() => {
            heartbeatInFlight = false;
          });
      }, 30000);
    })().catch((error: unknown) => {
      if (active) {
        const message = error instanceof Error
          ? error.message
          : 'JARVIS endpoint registration failed.';
        const status = error instanceof ApiClientError && (error.status === 401 || error.status === 403)
          ? 'unauthorized'
          : error instanceof ApiClientError
            ? 'unhealthy'
            : 'disconnected';
        setEndpointStatus(status, null, message);
        setRendererNegotiationError(message);
      }
    });
    return () => {
      active = false;
      if (heartbeatTimer) clearInterval(heartbeatTimer);
    };
  }, [
    isAuthenticated,
    setEndpointStatus,
    setRendererNegotiation,
    setRendererNegotiationError,
  ]);

  useEffect(() => {
    if (!isAuthenticated || !endpointId || !currentSessionId || endpointStatus !== 'connected') return;
    void attachEndpointToSession(endpointId, currentSessionId).catch((error: unknown) => {
      setEndpointStatus(
        'disconnected',
        endpointId,
        error instanceof Error ? error.message : 'The endpoint could not attach this conversation.',
      );
    });
  }, [
    currentSessionId,
    endpointId,
    endpointStatus,
    isAuthenticated,
    setEndpointStatus,
  ]);

  useEffect(() => {
    if (voiceState === 'processing' && !isLoading && !isStreaming) setVoiceState('idle');
  }, [isLoading, isStreaming, setVoiceState, voiceState]);

  useEffect(() => {
    for (const message of messages) {
      if (!message.presentation || message.presentation.intent.sessionId !== currentSessionId) continue;
      applyPresentation(message.presentation, message.presentation_events ?? []);
    }
  }, [applyPresentation, currentSessionId, messages]);

  return null;
}
