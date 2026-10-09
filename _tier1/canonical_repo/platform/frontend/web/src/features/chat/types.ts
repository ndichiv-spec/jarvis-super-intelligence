import type { BrowserContextSummary } from '@/features/browser/types';

export type { BrowserContextSummary };

export interface ChatMessage {
  id?: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
  model?: string;
  tool_calls?: ToolCall[];
  sources?: string[];
  presentation?: SemanticPresentationContract;
  canonical_task_id?: string;
  presentation_revision_id?: string;
  confidence?: number;
  skill_used?: string;
  metadata?: Record<string, unknown>;
  status?: 'QUEUED' | 'STREAMING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | 'THINKING' | 'STREAM_INTERRUPTED' | 'DRAFT';
  client_message_id?: string;
  latency_ms?: number;
  error?: string | {
    category?: string;
    message?: string;
    request_id?: string;
    retryable?: boolean;
  };
  interrupted?: boolean;
  feedback?: { rating: number; comment?: string };
}

/** Request body for editing a user message and re-sending it. */
export interface EditAndResendRequest {
  new_content: string;
  client_message_id?: string;
}

/** Request body for restoring (un-archiving) a session. */
export interface RestoreSessionRequest {
  archived: boolean;
}

export interface ChatErrorInfo {
  category: string;
  message: string;
  request_id: string;
  retryable: boolean;
  status_code?: number;
}

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
  status?: 'pending' | 'running' | 'completed' | 'failed';
}

export interface ChatResponse {
  success: boolean;
  response?: string;
  content?: string;
  answer?: string;
  reply?: string;
  session_id?: string;
  message?: string;
  model?: string;
  confidence?: number;
  sources?: string[];
  intent?: string;
  processing_time?: number;
  timestamp?: string;
  tool_calls?: ToolCall[];
  tool_results?: unknown[];
  runtime_command_id?: string;
  presentation?: SemanticPresentationContract;
  canonical_task_id?: string;
  presentation_revision_id?: string;
}

export interface SessionInfo {
  session_id: string;
  preview: string;
  started: string;
  last_active?: string;
  message_count?: number;
  model?: string;
  last_status?: string;
  archived?: boolean;
}

export interface ChatRequest {
  message: string;
  session_id?: string | null;
  stream?: boolean;
  model?: string;
  client_message_id?: string;
  browser_context?: BrowserContextSummary;
}

// ---------------------------------------------------------------------------
// Browser ↔ Chat Integration (bridges browser events into chat context)
// ---------------------------------------------------------------------------

/** Events published by the browser feature and consumed by chat. */
export type BrowserEventType =
  | 'tab_navigated'
  | 'evidence_captured'
  | 'security_alert'
  | 'task_completed'
  | 'task_failed'
  | 'page_extracted'
  | 'bookmark_added'
  | 'browser_connected'
  | 'browser_disconnected';

export interface BrowserEvent {
  type: BrowserEventType;
  timestamp: string;
  session_id?: string | null;
  tab_id?: string | null;
  data: Record<string, unknown>;
}

export interface ToolDispatchResult {
  success: boolean;
  action_type?: string;
  result?: unknown;
  requires_confirmation?: boolean;
  error?: string;
}

export interface ChatStreamChunk {
  type: 'meta' | 'chunk' | 'done' | 'error' | 'typing' | 'complete' | 'status';
  session_id?: string;
  text?: string;
  content?: string;
  confidence?: number;
  sources?: string[];
  tool_calls?: ToolCall[];
  error?: string;
  category?: string;
  message?: string;
  request_id?: string;
  retryable?: boolean;
  status?: string;
  message_id?: string;
  model?: string;
  resumed?: boolean;
  runtime_command_id?: string;
  presentation?: SemanticPresentationContract;
  canonical_task_id?: string;
  presentation_revision_id?: string;
}

export interface MessageTurnResult {
  session_id?: string;
  message?: string | null;
  model?: string;
  latency_ms?: number | null;
  sources?: string[];
  status?: string;
  error?: ChatErrorInfo | null;
  resumed?: boolean;
  message_id?: string;
  timestamp?: string;
  tool_calls?: ToolCall[];
  runtime_command_id?: string;
  presentation?: SemanticPresentationContract;
  canonical_task_id?: string;
  presentation_revision_id?: string;
}

export type SemanticPresentationComponent =
  | {
      id: string;
      type: 'conversation.markdown';
      text: string;
    }
  | {
      id: string;
      type: 'research.source_list';
      title: string;
      items: Array<{
        data_ref: string;
        title: string;
        url: string;
        snippet: string;
      }>;
    }
  | {
      id: string;
      type: 'workspace.match_list';
      title: string;
      items: Array<{
        data_ref: string;
        path: string;
        line: number;
        text: string;
      }>;
    }
  | {
      id: string;
      type: 'geospatial.point_map';
      title: string;
      items: Array<{
        data_ref: string;
        latitude: number;
        longitude: number;
        label: string;
        units: {
          latitude: 'degrees_north';
          longitude: 'degrees_east';
        };
        location_type: 'user_provided';
      }>;
    }
  | {
      id: string;
      type: 'media.image_gallery';
      title: string;
      items: Array<{
        data_ref: string;
        media_ref: string;
        alt: string;
        provider: string;
        model: string;
        content_type: 'image/png' | 'image/jpeg' | 'image/webp';
        width: number;
        height: number;
      }>;
    };

/** JSON semantic contract; deliberately contains no framework or executable UI values. */
export interface SemanticPresentationContract {
  contract_version: '1.0' | '1.1';
  presentation_id: string;
  objective: string;
  environment: 'conversation' | 'web' | 'map' | 'image';
  content_hierarchy: string[];
  focus: string;
  components: SemanticPresentationComponent[];
  assistant_presence: { mode: 'inline'; state: 'available' | 'error' };
  interactions: Array<{
    id: string;
    type: 'external_source_navigation';
    data_ref: string;
    required_permissions: ['web:read'];
    user_gesture_required: true;
  }>;
  visualizations: [];
  modalities: Array<'text' | 'links' | 'map' | 'image'>;
  accessibility: {
    reading_order: string[];
    announce_updates: boolean;
    non_color_status: boolean;
  };
  responsive: { reflow: 'single_column'; minimum_width: string };
  transitions: {
    on_unsupported: 'conversation_fallback';
    on_error: 'retain_observed_text';
  };
  errors: string[];
  task_state?: {
    status: 'completed' | 'partial' | 'error' | 'unsupported';
    message: string;
  };
  source_provenance?: Array<{
    data_ref: string;
    source_type:
      | 'public_web'
      | 'authorized_workspace'
      | 'user_provided_coordinates'
      | 'generated_image';
    observed_at: string;
  }>;
  media_refs?: Array<{
    id: string;
    url: string;
    content_type: 'image/png' | 'image/jpeg' | 'image/webp';
    expires_at: number;
  }>;
  user_preferences?: null;
  view_state?: {
    focus: string;
    selected_data_ref: string | null;
  };
  fallback: { type: 'conversation.markdown'; text: string };
  correlation: {
    request_id: string | null;
    session_id: string | null;
    conversation_id: string | null;
    command_id: string | null;
    execution_id: string | null;
  };
  data_refs: Array<{
    id: string;
    kind:
      | 'public_source'
      | 'workspace_result'
      | 'user_provided_coordinates'
      | 'generated_media';
  }>;
  renderer_requirements: {
    contract_version: '1.0' | '1.1';
    supported_contract_versions?: ['1.0', '1.1'];
    required_components: string[];
    required_modalities?: Array<'text' | 'links' | 'map' | 'image'>;
    fallback_components: ['conversation.markdown'];
  };
}

export const CHAT_MODELS = [
  { id: 'auto', name: 'Auto Select', provider: 'JARVIS' },
  { id: 'jarvis-brain', name: 'JARVIS Brain (Qwen3-4B)', provider: 'JARVIS' },
  { id: 'silverwing', name: 'Silverwing (native)', provider: 'Silverwing' },
  { id: 'openai', name: 'OpenAI GPT-5.6', provider: 'OpenAI' },
  { id: 'anthropic', name: 'Anthropic Claude', provider: 'Anthropic' },
  { id: 'google', name: 'Google Gemini', provider: 'Google' },
  { id: 'groq', name: 'Groq', provider: 'Groq' },
  { id: 'deepseek', name: 'DeepSeek', provider: 'DeepSeek' },
  { id: 'ollama', name: 'Local LLM (Ollama)', provider: 'Ollama' },
  { id: 'llamacpp', name: 'llama.cpp', provider: 'llama.cpp' },
  { id: 'bedrock', name: 'AWS Bedrock', provider: 'AWS' },
  { id: 'vertex', name: 'Google Vertex AI', provider: 'Google Cloud' },
  { id: 'vllm', name: 'vLLM', provider: 'vLLM' },
] as const;

export type ChatModelId = typeof CHAT_MODELS[number]['id'];

export interface ProviderInfo {
  provider: string;
  available: boolean;
  authorized: boolean;
  model: string;
  models: string[];
  endpoint?: string | null;
  display_name?: string;
  healthy?: boolean;
  configured?: boolean;
  capabilities?: string[];
  latency_ms?: number | null;
  health_status?: string;
  errors?: string;
  last_checked?: number | null;
}

export interface ModelCatalog {
  providers: ProviderInfo[];
  default_provider: string;
  default_model: string;
}
