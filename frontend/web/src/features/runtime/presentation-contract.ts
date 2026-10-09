export type PresentationMode =
  | 'ambient'
  | 'compact'
  | 'focused'
  | 'immersive'
  | 'spatial'
  | 'fullscreen';

export type PresentationEnvironmentType =
  | 'conversation'
  | 'geospatial'
  | 'navigation'
  | 'research'
  | 'communications'
  | 'visual'
  | 'media'
  | 'device'
  | 'voice'
  | 'knowledge'
  | 'tasks'
  | 'automation'
  | 'learning'
  | 'system'
  | 'observability'
  | 'creative';

export interface DataReference {
  source:
    | 'runtime'
    | 'capability'
    | 'connector'
    | 'provider'
    | 'device'
    | 'user'
    | 'memory'
    | 'web'
    | 'generated';
  resource: string;
  query?: Record<string, unknown>;
  freshness?: { required?: boolean; maxAgeMs?: number };
  authorization?: string;
}

export interface SceneNode {
  id: string;
  type:
    | 'group'
    | 'text'
    | 'image'
    | 'video'
    | 'map'
    | 'globe'
    | 'model3d'
    | 'chart'
    | 'timeline'
    | 'panel'
    | 'avatar'
    | 'device'
    | 'document'
    | 'source'
    | 'control'
    | 'status'
    | 'custom';
  children?: SceneNode[];
  data?: DataReference;
  properties?: Record<string, unknown>;
  visibility?: Record<string, unknown>;
  interaction?: string[];
  animation?: Record<string, unknown>;
}

export interface PresentationIntent {
  id: string;
  sessionId: string;
  sequence: number;
  environment: {
    id: string;
    type: PresentationEnvironmentType;
    title?: string;
    purpose?: string;
    persistence?: 'ephemeral' | 'session' | 'persistent';
    capabilities?: string[];
    state?: Record<string, unknown>;
  };
  mode?: PresentationMode;
  focus?: {
    target: string;
    source?: DataReference;
    priority?: number;
    reason?: string;
    camera?: Record<string, unknown>;
  };
  scene?: { root: SceneNode };
  visualizations?: Array<{
    id: string;
    type: string;
    data: DataReference;
    configuration?: Record<string, unknown>;
    camera?: Record<string, unknown>;
    overlays?: PresentationIntent['overlays'];
  }>;
  media?: Array<Record<string, unknown>>;
  overlays?: Array<{
    id: string;
    type: string;
    anchor?: string;
    data?: DataReference;
    properties?: Record<string, unknown>;
  }>;
  interactions?: Array<{
    id: string;
    type: string;
    action: { capability: string; action: string; resource?: string };
    requiresConfirmation?: boolean;
  }>;
  assistant?: {
    state: string;
    presence?: string;
    expression?: string;
    emphasis?: number;
    message?: string;
    audio?: Record<string, unknown>;
  };
  voice?: {
    enabled: boolean;
    state: 'silent' | 'listening' | 'processing' | 'speaking';
    transcript?: string;
    emphasis?: string[];
    interruption?: 'allowed' | 'blocked';
  };
  spatial?: Record<string, unknown>;
  transitions?: Array<Record<string, unknown>>;
  emphasis?: Array<Record<string, unknown>>;
  context?: Record<string, unknown>;
  constraints?: Record<string, unknown>;
  lifecycle?: Record<string, unknown>;
}

export interface PresentationEnvelope {
  protocol: 'jarvis.presentation';
  version: string;
  intent: PresentationIntent;
  issuedAt: string;
  source: { runtime: string; requestId: string };
  security: { authorizationContext: string; capabilities: string[] };
}

export interface PresentationEvent {
  protocol: 'jarvis.presentation';
  version: string;
  presentationId: string;
  sessionId: string;
  sequence: number;
  type:
    | 'created'
    | 'updated'
    | 'transitioned'
    | 'interaction'
    | 'capability_changed'
    | 'media_ready'
    | 'error'
    | 'closed';
  occurredAt: string;
  payload: Record<string, unknown>;
}

export interface PresentationCapabilities {
  clientId: string;
  runtimeVersion?: string;
  platform?: 'web' | 'desktop' | 'mobile' | 'tablet' | 'automotive' | 'ar' | 'vr' | 'unknown';
  surfaces: string[];
  renderers?: string[];
  environments: string[];
  primitives: string[];
  media: string[];
  spatial: string[];
  input: string[];
  output: string[];
  constraints?: Record<string, unknown>;
  performanceProfile?: string;
  accessibility?: Record<string, unknown>;
}

export interface ClientPresentationRegistration {
  clientId: string;
  protocolVersion: string;
  accepted: boolean;
  runtimeCapabilities: RendererNegotiation;
}

export interface CapabilityOutput {
  id: string;
  type:
    | 'text'
    | 'structured_data'
    | 'image'
    | 'video'
    | 'audio'
    | 'location'
    | 'route'
    | 'document'
    | 'device_state'
    | 'task'
    | 'event'
    | 'model'
    | 'stream';
  schema?: string;
  sensitivity?: 'public' | 'internal' | 'sensitive' | 'restricted';
  freshness?: { required?: boolean; maxAgeMs?: number };
}

export interface CapabilityPresentationDefinition {
  id: string;
  version: string;
  name: string;
  description: string;
  category: string;
  outputs: CapabilityOutput[];
  presentation: {
    environments: Array<{
      environment: string;
      suitability: 'primary' | 'secondary' | 'contextual';
      priority: number;
    }>;
    visualizations: Array<{
      type: string;
      inputTypes: string[];
      requiredClientCapabilities: string[];
      priority: number;
    }>;
    modalities: string[];
  };
  operationalStatus: string;
}

export interface RendererDefinition {
  type: string;
  version: string;
  supportedClients: string[];
  supportedPrimitives: string[];
  capabilities: string[];
  constraints: Record<string, unknown>;
  presentationTypes?: string[];
  requiredCapabilities?: string[];
  limitations?: string[];
  securityClass?: 'standard' | 'sensitive' | 'restricted';
}

export interface PresentationContractMetadata {
  protocol: 'jarvis.presentation';
  version: string;
  renderers: RendererDefinition[];
  intentOwner: 'jarvis_core';
  executionAuthority: 'backend_policy';
}

export interface PresentationFallback {
  requested: string;
  available: string[];
  selected: string;
  reason: string;
}

export interface RendererNegotiation {
  clientId: string;
  renderers: RendererDefinition[];
  fallbacks: PresentationFallback[];
}

export interface PresentationFeedback {
  presentationId: string;
  type:
    | 'interaction'
    | 'viewport_changed'
    | 'media_state'
    | 'permission_request'
    | 'capability_error'
    | 'user_override'
    | 'client_error';
  payload: Record<string, unknown>;
  timestamp: string;
}

export interface PresentationTrace {
  presentationId: string;
  requestId: string;
  sessionId: string;
  intentVersion: string;
  renderer?: string;
  capabilitySources: string[];
  timestamps: {
    created: string;
    rendered?: string;
    completed?: string;
  };
  errors?: string[];
}

export type RuntimeState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'planning'
  | 'executing'
  | 'searching'
  | 'browsing'
  | 'observing'
  | 'navigating'
  | 'generating'
  | 'speaking'
  | 'explaining'
  | 'working'
  | 'learning'
  | 'waiting'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'offline';

export interface RuntimeEvent {
  id: string;
  protocolVersion: string;
  type: string;
  timestamp: string;
  requestId?: string;
  sessionId: string;
  conversationId?: string;
  capabilityId?: string;
  executionId?: string;
  messageId?: string;
  presentationId?: string;
  source: string;
  sequence: number;
  state?: RuntimeState;
  data: Record<string, unknown>;
  presentation?: Record<string, unknown> | null;
  correlation?: Record<string, unknown>;
  security: {
    retention: 'ephemeral' | 'session' | 'audit' | 'durable';
    sensitivity: 'public' | 'user' | 'private' | 'sensitive' | 'restricted';
  };
}

export interface RuntimeSnapshot {
  sessionId: string;
  activeRequests: Array<Record<string, unknown>>;
  activeExecutions: Array<Record<string, unknown>>;
  activePresentations: Array<Record<string, unknown>>;
  assistantState: RuntimeState;
  activeMedia: Array<Record<string, unknown>>;
  activeTasks: Array<Record<string, unknown>>;
  sequence: number;
  oldestAvailableSequence?: number;
  retentionFloor?: number;
}
