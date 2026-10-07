import { getApiUrl, getWsUrl } from './runtime-url';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

/**
 * Per-request timeout budget. A live provider completion takes tens of seconds
 * (measured ~50s for POST /api/v1/ai/process), so this is set well above the
 * slowest realistic backend response.
 */
const REQUEST_TIMEOUT_MS = 180_000;

/**
 * Get the API base URL for client-side requests.
 * In browser environments (SSR), use relative paths when possible.
 * In development, use the configured API_URL or 127.0.0.1:8000.
 */
export function getApiBaseUrl(): string {
  // Check if we're in a browser environment
  if (typeof window !== 'undefined') {
    // In Replit/cloud environments, the API is typically proxied
    // Use relative path for same-origin requests (works with Next.js rewrites)
    if (typeof process.env.NEXT_PUBLIC_API_URL === 'undefined' || !process.env.NEXT_PUBLIC_API_URL) {
      // Default to relative path for cloud deployments
      return '';
    }
  }
  // Server-side or when API_URL is configured
  return API_BASE;
}

/**
 * Get the WebSocket base URL for client-side requests.
 */
export function getWsBaseUrl(): string {
  if (typeof window !== 'undefined') {
    if (typeof process.env.NEXT_PUBLIC_WS_URL === 'undefined' || !process.env.NEXT_PUBLIC_WS_URL) {
      // Use window.location for dynamic protocol detection
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      return `${protocol}//${window.location.host}`;
    }
  }
  return getWsUrl('');
}

import { SystemCapabilities } from '../types';

// Connection status tracking
export interface ConnectionStatus {
  connected: boolean;
  lastChecked: Date | null;
  error: string | null;
  retryCount: number;
}

let connectionStatus: ConnectionStatus = {
  connected: false,
  lastChecked: null,
  error: null,
  retryCount: 0,
};

export function getConnectionStatus(): ConnectionStatus {
  return connectionStatus;
}

export function setConnectionStatus(status: Partial<ConnectionStatus>): void {
  connectionStatus = { ...connectionStatus, ...status };
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
  tool_calls?: any[];
  sources?: string[];
  confidence?: number;
  model?: string;
}

export interface ChatResponse {
  success: boolean;
  response?: string;
  content?: string;
  answer?: string;
  title?: string;
  summary?: string;
  steps?: any[];
  mission_type?: string;
  live_data_used?: boolean;
  message?: string;
  model?: string;
  confidence?: number;
  sources?: string[];
  intent?: string;
  processing_time?: number;
  timestamp?: string;
  tool_calls?: any[];
  tool_results?: any[];
}

export interface HealthStatus {
  status: string;
  timestamp: string;
  version: string;
  milestone?: string;
  app_name?: string;
}

export interface HealthReport {
  current_status: string;
  last_check: string;
  health_rate_percent: number;
  total_checks: number;
  healthy_checks: number;
  avg_api_response_time_ms: number;
  recent_recoveries: number;
  recent_failures: number;
  latest_checks: Array<{
    name: string;
    status: string;
    message: string;
    response_time_ms: number;
  }>;
}

export interface KnowledgeEntry {
  key: string;
  value: string;
  category: string;
  tags: string[];
  created_at: string;
  read_only?: boolean;
}

export interface SystemProcess {
  pid: number;
  name: string;
  cpu_percent: number;
  memory_percent: number;
  status: string;
  created_at: string;
}

export interface MetricsData {
  system: {
    cpu_percent: number;
    memory_percent: number;
    memory_available_mb: number;
    disk_percent: number;
    disk_used_gb: number;
    process_count: number;
  };
  application: any;
  uptime_seconds: number;
}

export interface SystemDashboard {
  timestamp: string;
  platform: { name: string; version: string; instance_id: string; ai_enabled: boolean };
  services: string[];
  agents: {
    total: number;
    active: number;
    idle: number;
    by_role: Record<string, number>;
    entries: Array<{ id: string; name: string; role: string; status: string; capabilities: string[] }>;
  };
  providers: { ai_enabled: boolean; configured: string[] };
  automation: { tasks: number; scheduler_running: boolean; engine: string };
  capabilities: string[];
  recent_actions: Array<Record<string, any>>;
  resource_pressure: string;
}

export interface NotificationConfiguration {
  transport: 'smtp' | 'none' | 'unavailable';
  email_enabled: boolean;
  default_recipient: string | null;
}

export interface PlatformIdentity {
  platform_name: string;
  environment: string;
  instance_id: string;
  version: string;
  production_email_identity: string | null;
  developer_identity: string | null;
  verification_status: 'verified' | 'unverified';
  notification_configuration: NotificationConfiguration;
  ai_enabled: boolean;
  configured_providers: string[];
  provider_count: number;
  provenance: string;
  last_checked: string;
}

export interface AgentTask {
  id?: string;
  name: string;
  description?: string;
  schedule_type: string;
  schedule_value: string;
  priority: string;
  enabled: boolean;
  timeout: number;
  max_retries: number;
  last_run_at?: string;
  last_run_status?: string;
  last_run_duration_ms?: number;
  created_at?: string;
}

export interface TaskExecution {
  id: string;
  task_name: string;
  status: 'completed' | 'failed' | 'retrying' | 'running';
  started_at: string;
  completed_at?: string;
  duration_ms: number;
  retries: number;
  error?: string;
}

export interface AgentStats {
  total_tasks: number;
  active_tasks: number;
  success_rate_percent: number;
  avg_execution_time_ms: number;
}

export interface SchedulerStatus {
  running: boolean;
  total_scheduled: number;
  next_run_at?: string;
  single_worker_required?: boolean;
}

export interface ServiceTailoringStatus {
  success: boolean;
  changed: boolean;
  last_synced_at?: string | null;
  last_change_at?: string | null;
  sync_count: number;
  changes_detected: number;
  current_profile?: {
    configured_service_count: number;
    active_capabilities: string[];
    configured_services: Record<
      string,
      {
        label: string;
        features: string[];
        summary: string;
      }
    >;
  };
  history?: Array<{
    changed_at: string;
    configured_service_count: number;
    configured_services: string[];
    active_capabilities: string[];
  }>;
}

export interface FileUploadResponse {
  success: boolean;
  filename: string;
  size: number;
  type: string;
  message?: string;
}

export interface AuditLogEntry {
  id: string;
  user_id: string;
  user_email?: string;
  user_name?: string;
  action: string;
  resource_type: string;
  resource_id?: string;
  details?: Record<string, any>;
  ip_address?: string;
  created_at: string;
}

export interface Role {
  id: string;
  name: string;
  description?: string;
  permissions: string[];
  is_system: boolean;
  user_count?: number;
  created_at?: string;
}

export interface Permission {
  id: string;
  resource: string;
  action: string;
  description?: string;
}

export interface User {
  id: string;
  email: string;
  username: string;
  full_name?: string;
  roles: string[];
  status: 'active' | 'inactive' | 'suspended';
  last_login_at?: string;
  created_at?: string;
}

export interface TenantSettings {
  id: string;
  name: string;
  slug: string;
  plan: string;
  status: string;
  created_at: string;
  max_users: number;
  max_storage_mb: number;
  max_api_calls_per_day: number;
  settings?: Record<string, any>;
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

export interface ImageProviderStatus {
  configured: boolean;
  status: 'CONFIGURED' | 'NOT_CONFIGURED';
}

export interface ProviderSettingsResponse {
  success: boolean;
  settings: ProviderSettings;
  providers: Record<string, ProviderFeatureStatus>;
  env_file_exists: boolean;
  env_path: string;
  message?: string;
  timestamp?: string;
}

export interface LoginResponse {
  access_token?: string;
  token_type?: string;
  user: {
    id: string;
    email: string;
    username: string;
    full_name?: string;
    avatar_url?: string;
    status: string;
    tenant_id: string;
    last_login_at?: string;
    created_at?: string;
  };
}

export interface RegistrationResponse {
  success: boolean;
  status: 'verification_required';
  email_verified: false;
}

export interface RegisterRequest {
  email: string;
  username: string;
  password: string;
  full_name?: string;
  tenant_slug?: string;
}

export interface SessionInfo {
  id: string;
  user_id: string;
  device?: string;
  ip?: string | null;
  ip_address?: string;
  user_agent?: string;
  created_at: string;
  last_active_at?: string;
  is_current?: boolean | null;
}

export interface APIKeyInfo {
  id: string;
  name: string;
  description?: string;
  scopes: string[];
  prefix: string;
  created_at: string;
  expires_at?: string;
  last_used_at?: string;
}

export interface APIKeyCreate {
  name: string;
  description?: string;
  scopes?: string[];
  expires_in_days?: number;
}

export interface StarkChatRequest {
  message: string;
  context?: Record<string, any>;
  priority?: 'auto' | 'omega' | 'ai_engine' | 'agent';
  stream?: boolean;
}

export interface StarkChatResponse {
  success: boolean;
  response: string;
  source: string;
  engine: string;
  confidence: number;
  models_used: string[];
  tools_used: string[];
  processing_time: number;
  timestamp: string;
}

export interface StarkSystemStatus {
  gateway: {
    active: boolean;
    uptime: string | null;
    engines_connected: number;
    tools_registered: number;
  };
  engines: {
    omega: { status: string; type: string };
    ai_engine: { status: string; type: string };
    agent_system: { status: string; type: string };
    memory: { status: string; type: string };
    observation: { status: string; type: string };
    speech: { status: string; type: string };
    global_knowledge: { status: string; type: string };
  };
  tools: {
    registered: string[];
  };
  timestamp: string;
}

export interface AuditLogFilters {
  date_from?: string;
  date_to?: string;
  user_id?: string;
  action?: string;
  resource_type?: string;
  page?: number;
  per_page?: number;
}

class ApiRequestError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'ApiRequestError';
  }
}

class JarvisAPI {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  setToken(_token: string | undefined) {
    // Authentication uses server-managed HttpOnly cookies only.
  }

  async openAuthenticatedWebSocket(endpoint: string): Promise<WebSocket> {
    const { ticket } = await this.request<{ ticket: string }>('/api/v1/auth/ws-ticket', {
      method: 'POST',
    });
    const socketUrl = new URL(getWsUrl(endpoint));
    socketUrl.searchParams.set('ticket', ticket);
    return new WebSocket(socketUrl.toString());
  }

  private async request<T>(endpoint: string, options: RequestInit = {}, retries: number = 3): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };

    let lastError: Error | null = null;

    for (let attempt = 0; attempt < retries; attempt++) {
      try {
        const response = await fetch(getApiUrl(endpoint, undefined, this.baseUrl), {
          ...options,
          headers,
          credentials: 'include',
          // Timeout. Must exceed real provider latency: a live chat completion via
          // POST /api/v1/ai/process measured ~50s end to end (model latency ~39s).
          // The previous 30s budget aborted every attempt and then retried, so the
          // UI reported a failure for requests the backend was actually serving.
          signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
        });

        // Update connection status on success
        setConnectionStatus({
          connected: true,
          lastChecked: new Date(),
          error: null,
          retryCount: 0,
        });

        if (!response.ok) {
          const payload: unknown = await response.json().catch(() => null);
          const errorBody = payload && typeof payload === 'object'
            ? payload as Record<string, unknown>
            : {};
          const errorValue = errorBody.error;
          const detailValue = errorBody.detail;
          const nestedError = errorValue && typeof errorValue === 'object'
            ? errorValue as Record<string, unknown>
            : {};
          const nestedDetail = detailValue && typeof detailValue === 'object'
            ? detailValue as Record<string, unknown>
            : {};
          const message = [
            errorValue,
            nestedError.message,
            detailValue,
            nestedDetail.message,
            response.statusText,
          ].find((value): value is string => typeof value === 'string' && value.length > 0);
          throw new ApiRequestError(message || `API error: ${response.status}`, response.status);
        }

        const data = await response.json();
        return data as T;

      } catch (error: any) {
        lastError = error;
        
        // Update connection status on error
        setConnectionStatus({
          connected: false,
          lastChecked: new Date(),
          error: error.message,
          retryCount: attempt + 1,
        });

        // Don't retry for client errors (4xx)
        if (error instanceof ApiRequestError && error.status >= 400 && error.status < 500) {
          throw error;
        }

        // Don't retry after a timeout/abort. The call already consumed the full
        // budget; repeating it only multiplies the user's wait by the retry count
        // and cannot produce a different outcome.
        if (error.name === 'TimeoutError' || error.name === 'AbortError') {
          throw error;
        }

        // Wait before retrying (exponential backoff)
        if (attempt < retries - 1) {
          await new Promise(resolve => setTimeout(resolve, 1000 * Math.pow(2, attempt)));
        }
      }
    }

    // All retries failed
    throw lastError || new Error('Request failed after retries');
  }

  // Check backend connection
  async checkConnection(): Promise<boolean> {
    try {
      await this.getHealthStatus();
      setConnectionStatus({ connected: true, error: null });
      return true;
    } catch (error: any) {
      setConnectionStatus({ connected: false, error: error.message });
      return false;
    }
  }

  // Health & Status
  async getHealthStatus(): Promise<HealthStatus> {
    return this.request('/health');
  }

  async getCapabilities(): Promise<SystemCapabilities> {
    return this.request('/api/v1/system/capabilities');
  }

  async getRecoveryHistory(): Promise<any> {
    return this.request('/api/v1/monitoring/recovery-history');
  }

  async getHealthReport(): Promise<HealthReport> {
    return this.request('/api/v1/monitoring/health-report');
  }

  async getMetrics(): Promise<MetricsData> {
    return this.request('/api/v1/monitoring/metrics');
  }

  async getOptimizationReport(): Promise<any> {
    return this.request('/api/v1/monitoring/optimization-report');
  }

  async triggerOptimization(): Promise<any> {
    return this.request('/api/v1/monitoring/optimize', { method: 'POST' });
  }

  async getSystemDiagnostics(): Promise<any> {
    return this.request('/api/v1/monitoring/system/diagnostics');
  }

  // Chat
  async chat(message: string, model: string = 'local'): Promise<ChatResponse> {
    return this.request('/api/v1/ai/process', {
      method: 'POST',
      body: JSON.stringify({
        input: message,
        mode: 'chat',
        model,
        stream: false,
      }),
    });
  }

  async sendConversationMessage(input: {
    message: string;
    sessionId: string;
    clientMessageId: string;
  }): Promise<{
    session_id: string;
    reply?: string;
    message?: string;
    provider?: string;
    model?: string;
    status: string;
    error?: string;
  }> {
    return this.request('/api/chat', {
      method: 'POST',
      body: JSON.stringify({
        message: input.message,
        session_id: input.sessionId,
        client_message_id: input.clientMessageId,
      }),
    });
  }

  async generate(prompt: string, maxTokens: number = 500): Promise<any> {
    return this.request('/api/v1/ai/generate', {
      method: 'POST',
      body: JSON.stringify({ prompt, max_tokens: maxTokens }),
    });
  }

  async submitFeedback(query: string, response: string, rating: number): Promise<any> {
    return this.request('/api/v1/ai/feedback', {
      method: 'POST',
      body: JSON.stringify({ query, response, rating }),
    });
  }

  async getAIStatus(): Promise<any> {
    return this.request('/api/v1/ai/status');
  }

  // Knowledge
  async searchKnowledge(query: string, category?: string): Promise<{ results: KnowledgeEntry[] }> {
    const params = new URLSearchParams({ q: query });
    if (category) params.append('category', category);
    return this.request(`/api/v1/knowledge/search?${params}`);
  }

  async getKnowledgeEntries(category?: string, limit: number = 50): Promise<any> {
    const params = new URLSearchParams({ limit: limit.toString() });
    if (category) params.append('category', category);
    return this.request(`/api/v1/knowledge?${params}`);
  }

  async addKnowledge(key: string, value: string, category: string = 'general', tags: string[] = []): Promise<any> {
    return this.request('/api/v1/knowledge', {
      method: 'POST',
      body: JSON.stringify({ key, value, category, tags }),
    });
  }

  async deleteKnowledge(key: string): Promise<any> {
    return this.request(`/api/v1/knowledge?key=${encodeURIComponent(key)}`, { method: 'DELETE' });
  }

  async getKnowledgePatterns(): Promise<any> {
    return this.request('/api/v1/knowledge/patterns');
  }

  // System
  async getSystemStatus(): Promise<any> {
    return this.request('/api/v1/system/status');
  }

  async getProviderSettings(): Promise<ProviderSettingsResponse> {
    return this.request('/api/v1/system/provider-settings');
  }

  async getImageProviderStatus(): Promise<{ providers: Record<string, ImageProviderStatus> }> {
    return this.request('/api/v1/image/providers');
  }

  async generateImage(input: {
    prompt: string;
    session_id?: string;
    provider: string;
    size: string;
    quality: string;
    style: string | null;
    negative_prompt: string | null;
    num_images: number;
  }): Promise<{
    success: boolean;
    images: Array<{
      artifact_id: string;
      url: string;
      prompt: string;
      model: string;
      width: number;
      height: number;
      mime_type: string;
    }>;
    count: number;
    detail?: string;
    conversation_messages?: Array<{
      id: string;
      role: 'user' | 'assistant';
      content: string;
      timestamp: string;
      provider?: string;
      metadata?: Record<string, unknown>;
    }> | null;
  }> {
    return this.request('/api/v1/image/generate', {
      method: 'POST',
      body: JSON.stringify(input),
    }, 1);
  }

  async updateProviderSettings(data: Partial<ProviderSettings>): Promise<ProviderSettingsResponse> {
    return this.request('/api/v1/system/provider-settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async getProcesses(limit: number = 50, sortBy: string = 'cpu'): Promise<{ processes: SystemProcess[] }> {
    return this.request(`/api/v1/system/processes?limit=${limit}&sort=${sortBy}`);
  }

  async killProcess(pid: number, force: boolean = false): Promise<any> {
    return this.request('/api/v1/system/process/kill', {
      method: 'POST',
      body: JSON.stringify({ pid, force }),
    });
  }

  async getClipboard(): Promise<any> {
    return this.request('/api/v1/system/clipboard');
  }

  async setClipboard(text: string): Promise<any> {
    return this.request('/api/v1/system/clipboard', {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
  }

  async launchApp(app: string, args: string = ''): Promise<any> {
    return this.request('/api/v1/system/launch', {
      method: 'POST',
      body: JSON.stringify({ app, args }),
    });
  }

  // JARVIS-system dashboard (spec §47): platform state, NOT host PC metrics.
  async getSystemDashboard(): Promise<SystemDashboard> {
    return this.request<SystemDashboard>('/api/v1/system/dashboard');
  }

  async getIdentity(): Promise<PlatformIdentity> {
    return this.request<PlatformIdentity>('/api/v1/platform/identity');
  }

  async updateIdentity(patch: Partial<PlatformIdentity>): Promise<PlatformIdentity> {
    return this.request<PlatformIdentity>('/api/v1/platform/identity', {
      method: 'PUT',
      body: JSON.stringify(patch),
    });
  }

  async getCommonApps(): Promise<any> {
    return this.request('/api/v1/system/launch/apps');
  }

  async takeScreenshot(filename?: string): Promise<any> {
    return this.request('/api/v1/system/screenshot', {
      method: 'POST',
      body: JSON.stringify({ filename }),
    });
  }

  async getWindows(): Promise<any> {
    return this.request('/api/v1/system/windows');
  }

  // Files
  async listFiles(path: string = '.'): Promise<any> {
    return this.request(`/api/v1/system/files?path=${encodeURIComponent(path)}`);
  }

  async readFile(filepath: string): Promise<any> {
    return this.request('/api/v1/system/files/read', {
      method: 'POST',
      body: JSON.stringify({ path: filepath }),
    });
  }

  // Multimodal
  async uploadImage(file: File, description?: string): Promise<FileUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    if (description) formData.append('description', description);

    const response = await fetch(`${this.baseUrl}/api/v1/multimodal/upload/image`, {
      method: 'POST',
      body: formData,
      credentials: 'include',
    });

    return response.json();
  }

  async uploadDocument(file: File, category?: string): Promise<FileUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    if (category) formData.append('category', category);

    const response = await fetch(`${this.baseUrl}/api/v1/multimodal/upload/document`, {
      method: 'POST',
      body: formData,
      credentials: 'include',
    });

    return response.json();
  }

  async getFiles(): Promise<any> {
    return this.request('/api/v1/multimodal/files');
  }

  async deleteFile(filename: string): Promise<any> {
    return this.request(`/api/v1/multimodal/files/${filename}`, { method: 'DELETE' });
  }

  // Agents
  async getAgents(): Promise<{ tasks: AgentTask[] }> {
    return this.request('/api/v1/agents');
  }

  async getAgentStatus(agentId: string): Promise<any> {
    return this.request(`/api/v1/agents/${agentId}`);
  }

  async createAgentTask(name: string, description: string, priority: string = 'normal'): Promise<any> {
    return this.request('/api/v1/agents/task', {
      method: 'POST',
      body: JSON.stringify({ name, description, priority }),
    });
  }

  async registerCustomTask(task: Omit<AgentTask, 'id' | 'enabled' | 'last_run_at' | 'last_run_status' | 'last_run_duration_ms' | 'created_at'>): Promise<{ success: boolean; task: AgentTask }> {
    return this.request('/api/v1/agents/tasks', {
      method: 'POST',
      body: JSON.stringify(task),
    });
  }

  async toggleAgentTask(taskId: string, enabled: boolean): Promise<any> {
    return this.request(`/api/v1/agents/tasks/${taskId}/toggle`, {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    });
  }

  async runAgentTask(taskId: string): Promise<any> {
    return this.request(`/api/v1/agents/tasks/${taskId}/run`, {
      method: 'POST',
    });
  }

  async deleteAgentTask(taskId: string): Promise<any> {
    return this.request(`/api/v1/agents/tasks/${taskId}`, { method: 'DELETE' });
  }

  async getAgentStats(): Promise<AgentStats> {
    return this.request('/api/v1/agents/stats');
  }

  async getSchedulerStatus(): Promise<SchedulerStatus> {
    return this.request('/api/v1/agents/scheduler/status');
  }

  async toggleScheduler(running: boolean): Promise<any> {
    return this.request('/api/v1/agents/scheduler/toggle', {
      method: 'POST',
      body: JSON.stringify({ running }),
    });
  }

  async getTaskExecutions(limit: number = 20): Promise<{ executions: TaskExecution[] }> {
    return this.request(`/api/v1/agents/executions?limit=${limit}`);
  }

  async getServiceTailoringStatus(): Promise<ServiceTailoringStatus> {
    return this.request('/api/v1/agents/service-tailoring');
  }

  // LLM
  async llmChat(input: string, provider?: string): Promise<any> {
    return this.request('/api/v1/llm/chat', {
      method: 'POST',
      body: JSON.stringify({ input, provider }),
    });
  }

  async getLLMStatus(): Promise<any> {
    return this.request('/api/v1/llm/status');
  }

  // Stark Gateway - Unified AI Interface
  async starkChat(request: StarkChatRequest): Promise<StarkChatResponse> {
    return this.request('/api/v1/stark/chat', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async starkExecuteTool(toolName: string, params: Record<string, any> = {}): Promise<StarkChatResponse> {
    return this.request('/api/v1/stark/tool', {
      method: 'POST',
      body: JSON.stringify({
        tool_name: toolName,
        params: params,
      }),
    });
  }

  async starkGetStatus(): Promise<StarkSystemStatus> {
    return this.request('/api/v1/stark/status');
  }

  async starkGetHealth(): Promise<any> {
    return this.request('/api/v1/stark/health');
  }

  // Stark WebSocket Connection Helper
  async connectStarkWebSocket(onMessage: (data: any) => void, onError: (error: any) => void): Promise<WebSocket> {
    const ws = await this.openAuthenticatedWebSocket('/api/v1/stark/ws/chat');
    
    ws.onopen = () => {
      console.log('Stark WebSocket connected');
    };
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };
    
    ws.onerror = (error) => {
      console.error('Stark WebSocket error:', error);
      onError(error);
    };
    
    ws.onclose = () => {
      console.log('Stark WebSocket disconnected');
    };
    
    return ws;
  }

  // Global Knowledge & Observation
  async globalKnowledgeSearch(query: string, sources?: string, maxResults: number = 10): Promise<any> {
    const params = new URLSearchParams({ query, max_results: maxResults.toString() });
    if (sources) params.append('sources', sources);
    return this.request(`/api/v1/global/knowledge/global/search?${params}`);
  }

  async globalTrends(limit: number = 10): Promise<any> {
    return this.request(`/api/v1/global/knowledge/global/trends?limit=${limit}`);
  }

  async codeSearch(query: string, language?: string, maxResults: number = 10): Promise<any> {
    const params = new URLSearchParams({ query, max_results: maxResults.toString() });
    if (language) params.append('language', language);
    return this.request(`/api/v1/global/knowledge/global/code?${params}`);
  }

  async getKnowledgeSources(): Promise<any> {
    return this.request('/api/v1/global/knowledge/global/sources');
  }

  async getObservationStatus(): Promise<any> {
    return this.request('/api/v1/global/observation/status');
  }

  async getObservationReport(): Promise<any> {
    return this.request('/api/v1/global/observation/report');
  }

  async getObservationEvents(limit: number = 50): Promise<any> {
    return this.request(`/api/v1/global/observation/events?limit=${limit}`);
  }

  async getObservationMetrics(minutes: number = 5): Promise<any> {
    return this.request(`/api/v1/global/observation/metrics?minutes=${minutes}`);
  }

  async getRSSFeeds(): Promise<any> {
    return this.request('/api/v1/global/rss/feeds');
  }

  async getLatestRSSEntries(limit: number = 20): Promise<any> {
    return this.request(`/api/v1/global/rss/latest?limit=${limit}`);
  }

  async refreshRSSFeeds(): Promise<any> {
    return this.request('/api/v1/global/rss/refresh', { method: 'POST' });
  }

  // Voice Interface
  async voiceSpeak(text: string, profileName?: string): Promise<any> {
    return this.request('/api/v1/voice/speak', {
      method: 'POST',
      body: JSON.stringify({
        text: text,
        profile_name: profileName,
      }),
    });
  }

  async voiceListen(timeout: number = 5, phraseTimeLimit: number = 10): Promise<any> {
    return this.request('/api/v1/voice/listen', {
      method: 'POST',
      body: JSON.stringify({
        timeout: timeout,
        phrase_time_limit: phraseTimeLimit,
      }),
    });
  }

  async voiceTranscribe(file: File): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${this.baseUrl}/api/v1/voice/transcribe`, {
      method: 'POST',
      body: formData,
      credentials: 'include',
    });

    return response.json();
  }

  async voiceCreateProfile(name: string, rate: number = 150, volume: number = 0.9): Promise<any> {
    return this.request('/api/v1/voice/profile/create', {
      method: 'POST',
      body: JSON.stringify({
        name: name,
        rate: rate,
        volume: volume,
      }),
    });
  }

  async voiceListProfiles(): Promise<any> {
    return this.request('/api/v1/voice/profile/list');
  }

  async voiceGetVoices(): Promise<any> {
    return this.request('/api/v1/voice/voices');
  }

  async voiceGetStatus(): Promise<any> {
    return this.request('/api/v1/voice/status');
  }

  async connectVoiceWebSocket(onMessage: (data: any) => void, onError: (error: any) => void): Promise<WebSocket> {
    const ws = await this.openAuthenticatedWebSocket('/api/v1/voice/ws/chat');
    
    ws.onopen = () => {
      console.log('Voice WebSocket connected');
    };
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (error) {
        console.error('Failed to parse voice WebSocket message:', error);
      }
    };
    
    ws.onerror = (error) => {
      console.error('Voice WebSocket error:', error);
      onError(error);
    };
    
    ws.onclose = () => {
      console.log('Voice WebSocket disconnected');
    };
    
    return ws;
  }

  // Automation
  async getAutomationTasks(): Promise<any> {
    return this.request('/api/v1/automation');
  }

  async runAutomationTask(taskId: string): Promise<any> {
    return this.request(`/api/v1/automation/task/${taskId}/run`, { method: 'POST' });
  }

  // Cognitive Systems (Advanced Memory & Consciousness)
  async getCognitiveReport(): Promise<any> {
    return this.request('/api/v1/cognitive/consciousness/report');
  }

  async processCognitiveInteraction(userInput: string, aiResponse: string, userId: string = 'default'): Promise<any> {
    return this.request('/api/v1/cognitive/process', {
      method: 'POST',
      body: JSON.stringify({
        user_input: userInput,
        ai_response: aiResponse,
        user_id: userId,
      }),
    });
  }

  async storeMemory(content: string, layer: string = 'short_term', importance?: number): Promise<any> {
    return this.request('/api/v1/cognitive/memory/store', {
      method: 'POST',
      body: JSON.stringify({
        content,
        layer,
        importance,
      }),
    });
  }

  async recallMemories(query?: string, limit: number = 10): Promise<any> {
    const params = new URLSearchParams();
    if (query) params.append('query', query);
    params.append('limit', limit.toString());
    return this.request(`/api/v1/cognitive/memory/recall?${params}`);
  }

  async consolidateMemories(): Promise<any> {
    return this.request('/api/v1/cognitive/memory/consolidate', { method: 'POST' });
  }

  async getMemoryStats(): Promise<any> {
    return this.request('/api/v1/cognitive/memory/stats');
  }

  async analyzeEmotions(text: string): Promise<any> {
    return this.request(`/api/v1/cognitive/emotion/analyze?text=${encodeURIComponent(text)}`);
  }

  async getUserProfile(userId: string): Promise<any> {
    return this.request(`/api/v1/cognitive/user/${userId}/profile`);
  }

  async getPersonalizedContext(userId: string): Promise<any> {
    return this.request(`/api/v1/cognitive/context/${userId}`);
  }

  async triggerCognitiveReflection(): Promise<any> {
    return this.request('/api/v1/cognitive/consciousness/reflect', { method: 'POST' });
  }

  async setAttentionFocus(focus: string): Promise<any> {
    return this.request(`/api/v1/cognitive/consciousness/focus?focus=${encodeURIComponent(focus)}`, { method: 'POST' });
  }

  async addCognitiveGoal(goal: string): Promise<any> {
    return this.request(`/api/v1/cognitive/consciousness/goal?goal=${encodeURIComponent(goal)}`, { method: 'POST' });
  }

  async searchKnowledgeGraph(query: string, category?: string): Promise<any> {
    const params = new URLSearchParams({ query });
    if (category) params.append('category', category);
    return this.request(`/api/v1/cognitive/knowledge/search?${params}`);
  }

  // Agent Collaboration
  async getCollaborationAgents(): Promise<any> {
    return this.request('/api/v1/agents/collaboration/agents/list');
  }

  async getCollaborationTasks(status?: string, limit: number = 50): Promise<any> {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    params.append('limit', limit.toString());
    return this.request(`/api/v1/agents/collaboration/tasks/list?${params}`);
  }

  async createCollaborationTask(description: string, agents: string[], pattern: string): Promise<any> {
    return this.request('/api/v1/agents/collaboration/task/create', {
      method: 'POST',
      body: JSON.stringify({
        description,
        agents_needed: agents,
        collaboration_pattern: pattern,
      }),
    });
  }

  async executeCollaborationTask(taskId: string): Promise<any> {
    return this.request('/api/v1/agents/collaboration/task/execute', {
      method: 'POST',
      body: JSON.stringify({ task_id: taskId }),
    });
  }

  async getCollaborationMetrics(): Promise<any> {
    return this.request('/api/v1/agents/collaboration/metrics');
  }

  async selfOrganizeTask(description: string): Promise<any> {
    return this.request(`/api/v1/agents/collaboration/self-organize?description=${encodeURIComponent(description)}`, {
      method: 'POST',
    });
  }

  // Code Generation
  async generateProject(spec: any): Promise<any> {
    return this.request('/api/v1/codegen/generate', {
      method: 'POST',
      body: JSON.stringify(spec),
    });
  }

  async reviewProject(projectPath: string): Promise<any> {
    return this.request(`/api/v1/codegen/review?path=${encodeURIComponent(projectPath)}`);
  }

  async prepareDeployment(projectPath: string, platform: string, projectName: string): Promise<any> {
    return this.request('/api/v1/codegen/deploy', {
      method: 'POST',
      body: JSON.stringify({
        project_path: projectPath,
        platform,
        project_name: projectName,
      }),
    });
  }

  async triggerRecovery(): Promise<any> {
    return this.request('/api/v1/monitoring/trigger-recovery', { method: 'POST' });
  }

  // Auth
  async login(identifier: string, password: string): Promise<LoginResponse> {
    const response = await this.request<LoginResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ identifier, password }),
    });
    if ('access_token' in response) {
      this.setToken(response.access_token);
    }
    return response;
  }

  async register(data: RegisterRequest): Promise<RegistrationResponse> {
    return this.request<RegistrationResponse>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async verifyEmail(token: string): Promise<{ success: boolean; email_verified: boolean }> {
    return this.request('/api/v1/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify({ token }),
    });
  }

  async forgotPassword(email: string): Promise<{ message: string }> {
    return this.request('/api/v1/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
  }

  async resetPassword(token: string, newPassword: string): Promise<{ message: string }> {
    return this.request('/api/v1/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({ token, new_password: newPassword }),
    });
  }

  async logout(): Promise<{ message: string }> {
    return this.request('/api/v1/auth/logout', {
      method: 'POST',
    });
  }

  async getMe(): Promise<any> {
    return this.request('/api/v1/auth/me');
  }

  async updateMe(data: { full_name?: string; username?: string; avatar_url?: string }): Promise<any> {
    return this.request('/api/v1/auth/me', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async changePassword(currentPassword: string, newPassword: string): Promise<{ message: string }> {
    return this.request('/api/v1/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    });
  }

  async getSessions(): Promise<SessionInfo[]> {
    const response = await this.request<{ sessions: SessionInfo[] }>('/api/v1/auth/sessions');
    return response.sessions;
  }

  async revokeSession(sessionId: string): Promise<{ message: string }> {
    return this.request(`/api/v1/auth/sessions/${sessionId}`, {
      method: 'DELETE',
    });
  }

  async revokeAllSessions(): Promise<{ message: string }> {
    return this.request('/api/v1/auth/sessions', {
      method: 'DELETE',
    });
  }

  async getApiKeys(): Promise<APIKeyInfo[]> {
    const response = await this.request<{ api_keys: APIKeyInfo[] }>('/api/v1/auth/api-keys');
    return response.api_keys;
  }

  async createApiKey(data: APIKeyCreate): Promise<any> {
    return this.request('/api/v1/auth/api-keys', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async revokeApiKey(keyId: string): Promise<{ message: string }> {
    return this.request(`/api/v1/auth/api-keys/${keyId}`, {
      method: 'DELETE',
    });
  }

  // RBAC
  rbac = {
    getUsers: async (page: number = 1, perPage: number = 10, search?: string): Promise<{ users: User[]; total: number; page: number; per_page: number }> => {
      const params = new URLSearchParams({ page: page.toString(), per_page: perPage.toString() });
      if (search) params.append('search', search);
      return this.request(`/api/v1/rbac/users?${params}`);
    },

    createUser: async (data: { email: string; username: string; password: string; full_name?: string; roles: string[] }): Promise<{ success: boolean; user: User }> => {
      return this.request('/api/v1/rbac/users', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },

    updateUser: async (userId: string, data: Partial<User>): Promise<{ success: boolean; user: User }> => {
      return this.request(`/api/v1/rbac/users/${userId}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },

    deleteUser: async (userId: string): Promise<{ success: boolean }> => {
      return this.request(`/api/v1/rbac/users/${userId}`, { method: 'DELETE' });
    },

    getRoles: async (): Promise<{ roles: Role[] }> => {
      return this.request('/api/v1/rbac/roles');
    },

    createRole: async (data: { name: string; description?: string; permissions: string[] }): Promise<{ success: boolean; role: Role }> => {
      return this.request('/api/v1/rbac/roles', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },

    updateRole: async (roleId: string, data: Partial<Role>): Promise<{ success: boolean; role: Role }> => {
      return this.request(`/api/v1/rbac/roles/${roleId}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },

    deleteRole: async (roleId: string): Promise<{ success: boolean }> => {
      return this.request(`/api/v1/rbac/roles/${roleId}`, { method: 'DELETE' });
    },

    getPermissions: async (resource?: string): Promise<{ permissions: Permission[] }> => {
      const params = resource ? `?resource=${resource}` : '';
      return this.request(`/api/v1/rbac/permissions${params}`);
    },

    getAuditLogs: async (filters: AuditLogFilters = {}): Promise<{ logs: AuditLogEntry[]; total: number; page: number; per_page: number }> => {
      const params = new URLSearchParams();
      if (filters.date_from) params.append('date_from', filters.date_from);
      if (filters.date_to) params.append('date_to', filters.date_to);
      if (filters.user_id) params.append('user_id', filters.user_id);
      if (filters.action) params.append('action', filters.action);
      if (filters.resource_type) params.append('resource_type', filters.resource_type);
      if (filters.page) params.append('page', filters.page.toString());
      if (filters.per_page) params.append('per_page', filters.per_page.toString());
      return this.request(`/api/v1/rbac/audit-logs?${params}`);
    },

    exportAuditLogs: async (filters: AuditLogFilters = {}): Promise<Blob> => {
      const params = new URLSearchParams();
      if (filters.date_from) params.append('date_from', filters.date_from);
      if (filters.date_to) params.append('date_to', filters.date_to);
      if (filters.user_id) params.append('user_id', filters.user_id);
      if (filters.action) params.append('action', filters.action);
      if (filters.resource_type) params.append('resource_type', filters.resource_type);
      const response = await fetch(`${this.baseUrl}/api/v1/rbac/audit-logs/export?${params}`, {
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Export failed');
      return response.blob();
    },

    getTenantSettings: async (): Promise<TenantSettings> => {
      return this.request('/api/v1/rbac/tenant/settings');
    },

    updateTenantSettings: async (data: { max_users: number; max_storage_mb: number; max_api_calls_per_day: number; settings: Record<string, any> }): Promise<{ success: boolean; settings: TenantSettings }> => {
      return this.request('/api/v1/rbac/tenant/settings', {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },
  };
}

export const jarvisAPI = new JarvisAPI();
export default jarvisAPI;
