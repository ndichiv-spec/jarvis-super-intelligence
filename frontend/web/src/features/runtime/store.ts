import { create } from 'zustand';
import type { WsEvent } from '@/lib/websocket-client';
import type { EnvironmentId } from './environment-registry';
import type { SystemCapability } from '@/features/system/types';
import type { ProviderStatus } from '@/lib/types/platform';
import { mapCapabilities, mapIntegrations, type RuntimeCapability, type RuntimeIntegration } from './capability-graph';
import type {
  PresentationEnvelope,
  PresentationEvent,
  RendererNegotiation,
  RuntimeEvent,
  RuntimeSnapshot,
  RuntimeState,
} from './presentation-contract';

export interface RuntimeActivity {
  id: string;
  type: string;
  occurredAt: string;
  summary: string;
  detail?: string;
  source: 'websocket' | 'chat';
}

export interface EnvironmentTransition {
  from: EnvironmentId;
  to: EnvironmentId;
  occurredAt: string;
}

export interface RuntimeTask {
  id: string;
  title: string;
  status: string;
  updatedAt: string;
}

export interface RuntimeSelection {
  environment: EnvironmentId;
  kind: string;
  id?: string;
  label: string;
}

export type PermissionState = 'unknown' | 'requested' | 'granted' | 'denied';
export type VoicePresenceState = 'idle' | 'listening' | 'processing' | 'speaking' | 'error' | 'unavailable';
export type EndpointStatus =
  | 'unregistered'
  | 'registered'
  | 'connecting'
  | 'connected'
  | 'disconnected'
  | 'unauthorized'
  | 'unhealthy';

const ENVIRONMENT_FOR_PRESENTATION: Record<string, EnvironmentId> = {
  conversation: 'conversation',
  geospatial: 'world',
  navigation: 'world',
  research: 'knowledge',
  communications: 'communications',
  visual: 'visual',
  media: 'visual',
  device: 'devices',
  voice: 'voice',
  knowledge: 'knowledge',
  tasks: 'tasks',
  automation: 'tasks',
  learning: 'learning',
  system: 'operations',
  observability: 'operations',
  creative: 'visual',
};

interface JarvisRuntimeState {
  currentEnvironment: EnvironmentId;
  previousEnvironment: EnvironmentId | null;
  environmentHistory: EnvironmentTransition[];
  currentSessionId: string | null;
  currentTask: RuntimeTask | null;
  selectedObject: RuntimeSelection | null;
  permissions: Record<string, PermissionState>;
  voiceState: VoicePresenceState;
  activities: RuntimeActivity[];
  capabilities: RuntimeCapability[];
  integrations: RuntimeIntegration[];
  capabilityRegistryReported: boolean;
  capabilityRegistryUpdatedAt: string | null;
  rendererNegotiation: RendererNegotiation | null;
  rendererNegotiationError: string | null;
  currentPresentation: PresentationEnvelope | null;
  presentationEvents: PresentationEvent[];
  runtimeSnapshot: RuntimeSnapshot | null;
  runtimeState: RuntimeState;
  lastRuntimeSequence: number;
  runtimeEventError: string | null;
  endpointId: string | null;
  endpointStatus: EndpointStatus;
  endpointError: string | null;
  transitionEnvironment: (environment: EnvironmentId) => void;
  setSessionId: (sessionId: string | null) => void;
  setCurrentTask: (task: RuntimeTask | null) => void;
  setSelectedObject: (selection: RuntimeSelection | null) => void;
  setPermissionState: (capability: string, permission: PermissionState) => void;
  setVoiceState: (voiceState: VoicePresenceState) => void;
  syncCapabilityRegistry: (registry: SystemCapability[] | undefined, reportedAt?: string) => void;
  syncIntegrations: (providers: ProviderStatus[]) => void;
  setRendererNegotiation: (result: RendererNegotiation) => void;
  setRendererNegotiationError: (error: string | null) => void;
  applyPresentation: (envelope: PresentationEnvelope, events?: PresentationEvent[]) => boolean;
  applyRuntimeSnapshot: (snapshot: RuntimeSnapshot) => boolean;
  applyRuntimeEvent: (event: RuntimeEvent) => boolean;
  setRuntimeEventError: (error: string | null) => void;
  setEndpointStatus: (status: EndpointStatus, endpointId?: string | null, error?: string | null) => void;
  ingestWebSocketEvent: (event: WsEvent) => void;
  ingestChatActivity: (event: {
    event_id: string;
    event_type: string;
    timestamp: string;
    message: string;
    status: string;
  }) => void;
}

function valueFromRecord(value: unknown, key: string): string | undefined {
  if (!value || typeof value !== 'object' || !(key in value)) return undefined;
  const field = (value as Record<string, unknown>)[key];
  return typeof field === 'string' ? field : undefined;
}

function readableType(type: string): string {
  return type
    .replace(/[._-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function voiceStateFromEvent(eventType: string): VoicePresenceState | null {
  if (eventType === 'voice.speaking.completed' || eventType === 'voice.session.ended') return 'idle';
  if (eventType === 'voice.speaking.started') return 'speaking';
  if (eventType === 'voice.session.interrupted') return 'error';
  if (eventType.startsWith('voice.state.')) {
    const state = eventType.slice('voice.state.'.length);
    if (state === 'idle') return 'idle';
    if (state === 'listening' || state === 'capturing') return 'listening';
    if (state === 'speaking') return 'speaking';
    if (state === 'offline') return 'unavailable';
    if (state === 'error' || state === 'interrupted') return 'error';
    if (['transcribing', 'understanding', 'thinking', 'acting', 'generating_response', 'synthesizing'].includes(state)) {
      return 'processing';
    }
  }
  return null;
}

function activityFromWebSocket(event: WsEvent): RuntimeActivity {
  const message = typeof event.data === 'string'
    ? event.data
    : valueFromRecord(event.data, 'message')
      ?? valueFromRecord(event.data, 'summary')
      ?? valueFromRecord(event.data, 'description');

  return {
    id: event.id ?? `${event.timestamp}:${event.type}`,
    type: event.type,
    occurredAt: event.timestamp,
    summary: message || readableType(event.type),
    detail: valueFromRecord(event.data, 'status'),
    source: 'websocket',
  };
}

function transitionPatch(
  currentEnvironment: EnvironmentId,
  environmentHistory: EnvironmentTransition[],
  environment: EnvironmentId,
): Partial<Pick<JarvisRuntimeState, 'currentEnvironment' | 'previousEnvironment' | 'environmentHistory'>> {
  if (currentEnvironment === environment) return {};
  const occurredAt = new Date().toISOString();
  return {
    currentEnvironment: environment,
    previousEnvironment: currentEnvironment,
    environmentHistory: [
      ...environmentHistory,
      { from: currentEnvironment, to: environment, occurredAt },
    ].slice(-20),
  };
}

export const useJarvisRuntime = create<JarvisRuntimeState>((set) => ({
  currentEnvironment: 'conversation',
  previousEnvironment: null,
  environmentHistory: [],
  currentSessionId: null,
  currentTask: null,
  selectedObject: null,
  permissions: {},
  voiceState: 'idle',
  activities: [],
  capabilities: [],
  integrations: [],
  capabilityRegistryReported: false,
  capabilityRegistryUpdatedAt: null,
  rendererNegotiation: null,
  rendererNegotiationError: null,
  currentPresentation: null,
  presentationEvents: [],
  runtimeSnapshot: null,
  runtimeState: 'idle',
  lastRuntimeSequence: 0,
  runtimeEventError: null,
  endpointId: null,
  endpointStatus: 'unregistered',
  endpointError: null,
  transitionEnvironment: (environment) => set((state) => {
    return transitionPatch(
      state.currentEnvironment,
      state.environmentHistory,
      environment,
    );
  }),
  setSessionId: (currentSessionId) => set({
    currentSessionId,
    runtimeSnapshot: null,
    runtimeState: 'idle',
    lastRuntimeSequence: 0,
    runtimeEventError: null,
  }),
  setCurrentTask: (currentTask) => set({ currentTask }),
  setSelectedObject: (selectedObject) => set({ selectedObject }),
  setPermissionState: (capability, permission) => set((state) => ({
    permissions: { ...state.permissions, [capability]: permission },
  })),
  setVoiceState: (voiceState) => set({ voiceState }),
  syncCapabilityRegistry: (registry, reportedAt) => set({
    capabilities: mapCapabilities(registry),
    capabilityRegistryReported: registry !== undefined,
    capabilityRegistryUpdatedAt: registry ? reportedAt ?? new Date().toISOString() : null,
  }),
  syncIntegrations: (providers) => set({ integrations: mapIntegrations(providers) }),
  setRendererNegotiation: (rendererNegotiation) => set({
    rendererNegotiation,
    rendererNegotiationError: null,
  }),
  setRendererNegotiationError: (rendererNegotiationError) => set({ rendererNegotiationError }),
  applyPresentation: (envelope, events = []) => {
    if (
      envelope.protocol !== 'jarvis.presentation'
      || !/^\d+\.\d+$/.test(envelope.version)
      || Number(envelope.version.split('.')[0]) !== 1
    ) {
      return false;
    }
    set((state) => {
      if (state.currentPresentation?.intent.id === envelope.intent.id) {
        return state;
      }
      const voiceState = envelope.intent.voice?.state;
      const environment = ENVIRONMENT_FOR_PRESENTATION[envelope.intent.environment.type];
      return {
        currentPresentation: envelope,
        presentationEvents: events,
        ...(environment
          ? transitionPatch(state.currentEnvironment, state.environmentHistory, environment)
          : {}),
        ...(voiceState
          ? {
              voiceState: voiceState === 'silent'
                ? 'idle' as const
                : voiceState === 'processing'
                  ? 'processing' as const
                  : voiceState,
            }
          : {}),
      };
    });
    return true;
  },
  applyRuntimeSnapshot: (runtimeSnapshot) => {
    if (runtimeSnapshot.sessionId !== useJarvisRuntime.getState().currentSessionId) return false;
    set((state) => ({
      runtimeSnapshot,
      runtimeState: runtimeSnapshot.assistantState,
      lastRuntimeSequence: Math.max(state.lastRuntimeSequence, runtimeSnapshot.sequence),
    }));
    return true;
  },
  applyRuntimeEvent: (event) => {
    const current = useJarvisRuntime.getState();
    if (event.sessionId !== current.currentSessionId || event.sequence <= current.lastRuntimeSequence) {
      return false;
    }
    set((state) => {
      const environment = typeof event.data.environment === 'string'
        ? ENVIRONMENT_FOR_PRESENTATION[event.data.environment]
        : undefined;
      return {
        runtimeState: event.state ?? state.runtimeState,
        lastRuntimeSequence: event.sequence,
        ...(environment
          ? transitionPatch(
              state.currentEnvironment,
              state.environmentHistory,
              environment,
            )
          : {}),
        ...(event.type === 'voice_listening_started' ? { voiceState: 'listening' as const } : {}),
        ...(event.type === 'voice_synthesis_started' ? { voiceState: 'speaking' as const } : {}),
        ...(event.type === 'voice_completed' ? { voiceState: 'idle' as const } : {}),
        ...(event.type === 'request_completed' && state.voiceState !== 'speaking'
          ? { voiceState: 'idle' as const }
          : {}),
      };
    });
    return true;
  },
  setRuntimeEventError: (runtimeEventError) => set({ runtimeEventError }),
  setEndpointStatus: (endpointStatus, endpointId, endpointError = null) => set((state) => ({
    endpointStatus,
    endpointId: endpointId === undefined ? state.endpointId : endpointId,
    endpointError,
  })),
  ingestWebSocketEvent: (event) => set((state) => ({
    activities: [activityFromWebSocket(event), ...state.activities].slice(0, 50),
  })),
  ingestChatActivity: (event) => set((state) => ({
    activities: [{
      id: event.event_id,
      type: event.event_type,
      occurredAt: event.timestamp,
      summary: event.message || readableType(event.event_type),
      detail: event.status,
      source: 'chat' as const,
    }, ...state.activities].slice(0, 50),
    ...(voiceStateFromEvent(event.event_type)
      ? { voiceState: voiceStateFromEvent(event.event_type)! }
      : {}),
  })),
}));
