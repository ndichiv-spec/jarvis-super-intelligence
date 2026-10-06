import type { BrowserContextSummary } from '@/features/browser/types';

export type { BrowserContextSummary };

export interface ChatMessage {
  id?: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
  model?: string;
  tool_calls?: ToolCall[];
  runtime_events?: RuntimeActivityEvent[];
  sources?: string[];
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
  id?: string;
  index?: number;
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
  runtime_events?: RuntimeActivityEvent[];
  tool_results?: unknown[];
}

export interface RuntimeActivityEvent {
  event_id: string;
  event_type: string;
  timestamp: string;
  capability_id: string;
  action: string;
  status: string;
  message: string;
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
  temperature?: number;
  top_p?: number;
  max_tokens?: number;
  system_prompt?: string;
}

/** Per-chat configuration options that override model defaults. */
export interface ChatSettings {
  temperature: number;
  top_p: number;
  max_tokens: number;
  system_prompt?: string;
  web_search?: boolean;
  code_interpreter?: boolean;
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
  /**
   * `status` carries terminal lifecycle transitions (e.g. `STREAM_INTERRUPTED`)
   * that arrive without body content, so it is a distinct frame type from
   * `complete`/`done`.
   */
  type:
    | 'meta'
    | 'chunk'
    | 'tool_call_delta'
    | 'activity'
    | 'reasoning'
    | 'done'
    | 'error'
    | 'typing'
    | 'complete'
    | 'status';
  session_id?: string;
  text?: string;
  content?: string;
  confidence?: number;
  sources?: string[];
  tool_calls?: ToolCall[];
  index?: number;
  id?: string;
  name?: string;
  arguments?: string;
  error?: string;
  category?: string;
  message?: string;
  request_id?: string;
  retryable?: boolean;
  status?: string;
  message_id?: string;
  model?: string;
  resumed?: boolean;
  event_id?: string;
  event_type?: string;
  timestamp?: string;
  capability_id?: string;
  action?: string;
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
  runtime_events?: RuntimeActivityEvent[];
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
