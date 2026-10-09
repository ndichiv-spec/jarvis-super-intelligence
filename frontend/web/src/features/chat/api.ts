import apiClient, { ApiClientError } from '@/lib/api-client';
import API_ENDPOINTS from '@/config/api';
import type {
  ChatResponse,
  ChatRequest,
  SessionInfo,
  ChatStreamChunk,
  ChatErrorInfo,
  MessageTurnResult,
  ModelCatalog,
  ToolCall,
  RuntimeActivityEvent,
} from './types';

function newClientMessageId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `cm-${crypto.randomUUID()}`;
  }
  return `cm-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

let activeStreamController: AbortController | null = null;

export function cancelStreamingMessage(): void {
  activeStreamController?.abort('user');
}

function toMessageTurnResult(data: Record<string, unknown>): MessageTurnResult {
  return {
    session_id: data.session_id as string,
    message: (data.reply as string) ?? (data.message as string) ?? null,
    model: data.model as string,
    provider: data.provider as string | undefined,
    latency_ms: data.latency_ms as number | null,
    sources: data.sources as string[],
    status: (data.status as string) ?? 'COMPLETED',
    error: data.error as ChatErrorInfo,
    resumed: Boolean(data.resumed),
    message_id: data.message_id as string,
    timestamp: data.timestamp as string | undefined,
    tool_calls: data.tool_calls as ToolCall[] | undefined,
    runtime_events: data.runtime_events as RuntimeActivityEvent[] | undefined,
    presentation: data.presentation as MessageTurnResult['presentation'],
    presentation_events: data.presentation_events as MessageTurnResult['presentation_events'],
  };
}

export const chatApi = {
  createSession(): Promise<{ id: string }> {
    return apiClient.post<{ id: string }>(API_ENDPOINTS.chat.sessions, {});
  },

  getLocationAuthorization(): Promise<{ authorized: boolean }> {
    return apiClient.get<{ authorized: boolean }>(API_ENDPOINTS.presentation.locationAuthorization);
  },

  sendMessage(request: ChatRequest): Promise<MessageTurnResult> {
    return apiClient
      .post<Record<string, unknown>>(API_ENDPOINTS.chat.send, {
        message: request.message,
        session_id: request.session_id,
        model: request.model || 'auto',
        client_message_id: request.client_message_id || newClientMessageId(),
        browser_context: request.browser_context,
        location: request.location,
        location_error: request.location_error,
      })
      .then(toMessageTurnResult);
  },

  async sendStreamingMessage(
    request: ChatRequest,
    onChunk: (chunk: ChatStreamChunk) => void,
    onError: (error: Error, info?: ChatErrorInfo) => void,
    onComplete: () => void
  ): Promise<void> {
    const controller = new AbortController();
    activeStreamController?.abort();
    activeStreamController = controller;
    const timeoutId = setTimeout(() => controller.abort('timeout'), 120000);
    try {
      const response = await fetch(API_ENDPOINTS.chat.stream, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        signal: controller.signal,
        credentials: 'include',
        body: JSON.stringify({
          message: request.message,
          session_id: request.session_id,
          model: request.model || 'auto',
          client_message_id: request.client_message_id || newClientMessageId(),
          browser_context: request.browser_context,
          location: request.location,
          location_error: request.location_error,
        }),
      });

      if (!response.ok) {
        let info: ChatErrorInfo | undefined;
        try {
          const body = await response.json();
          const err = body?.error;
          if (err) {
            info = {
              category: err.category || err.code,
              message: err.message,
              request_id: err.request_id,
              retryable: err.retryable,
              status_code: err.status_code,
            };
          }
        } catch {
          // ignore non-JSON error bodies
        }
        onError(
          new Error(info?.message || `Chat request failed (HTTP ${response.status})`),
          info
        );
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        onError(new Error('No response body reader available'));
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let terminalReceived = false;

      const dispatchChunk = (raw: string) => {
        try {
          const chunk = JSON.parse(raw) as ChatStreamChunk;
          if (
            chunk.type === 'complete'
            || chunk.type === 'done'
            || chunk.type === 'error'
            || (chunk.type === 'status' && chunk.status === 'STREAM_INTERRUPTED')
          ) {
            terminalReceived = true;
          }
          onChunk(chunk);
        } catch {
          // Skip malformed chunks; EOF without a terminal frame is surfaced below.
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            dispatchChunk(line.slice(6));
          }
        }
      }

      if (buffer.startsWith('data: ')) {
        dispatchChunk(buffer.slice(6));
      }

      if (!terminalReceived) {
        onError(
          new Error('The response stream ended before JARVIS reported a final status.'),
          {
            category: 'STREAM_INTERRUPTED',
            message: 'The response stream ended before completion.',
            request_id: '',
            retryable: true,
          },
        );
        return;
      }

      onComplete();
    } catch (error) {
      if (controller.signal.reason === 'user') {
        onError(new Error('Response stopped. Your message is saved and can be retried.'), {
          category: 'CANCELLED',
          message: 'The response was cancelled.',
          request_id: '',
          retryable: true,
        });
        return;
      }
      const msg = error instanceof Error ? error.message : String(error);
      onError(
        new Error('Connection lost while streaming. Your message is safe and can be retried.'),
        {
          category: 'STREAM_INTERRUPTED',
          message: msg,
          request_id: '',
          retryable: true,
        }
      );
    } finally {
        clearTimeout(timeoutId);
        if (activeStreamController === controller) {
        activeStreamController = null;
      }
    }
  },

  async getSessions(params?: {
    limit?: number;
    offset?: number;
    q?: string;
    search_messages?: boolean;
    include_archived?: boolean;
  }): Promise<{ sessions: SessionInfo[]; total: number; offset: number; limit: number; has_more: boolean }> {
    const data = await apiClient.get<{
      sessions: Array<Record<string, unknown>>;
      total?: number;
      offset?: number;
      limit?: number;
      has_more?: boolean;
    }>(API_ENDPOINTS.chat.sessions, { params });
    const list = data?.sessions ?? [];
    return {
      sessions: list.map((s) => ({
        session_id: String(s.id ?? ''),
        title: String(s.title ?? 'New conversation'),
        preview: String(s.title ?? 'New conversation'),
        started: String(s.created_at ?? new Date().toISOString()),
        last_active: String(s.updated_at ?? s.created_at ?? new Date().toISOString()),
        message_count: Number(s.message_count ?? 0),
        last_status: s.last_status as SessionInfo['last_status'],
        archived: Boolean(s.archived),
      })),
      total: Number(data?.total ?? list.length),
      offset: Number(data?.offset ?? 0),
      limit: Number(data?.limit ?? 100),
      has_more: Boolean(data?.has_more),
    };
  },

  getSessionHistory(
    sessionId: string,
    params?: { limit?: number; offset?: number }
  ): Promise<{ session: Record<string, unknown>; messages: Array<Record<string, unknown>>; total: number }> {
    return apiClient.get(API_ENDPOINTS.chat.history(sessionId), { params });
  },

  deleteSession(sessionId: string): Promise<{ success: boolean }> {
    return apiClient.delete<{ success: boolean }>(API_ENDPOINTS.chat.history(sessionId));
  },

  renameSession(sessionId: string, title: string): Promise<Record<string, unknown>> {
    return apiClient.patch<Record<string, unknown>>(API_ENDPOINTS.chat.sessions + `/${sessionId}`, {
      title,
    });
  },

  setArchived(sessionId: string, archived: boolean): Promise<Record<string, unknown>> {
    return apiClient.patch<Record<string, unknown>>(API_ENDPOINTS.chat.sessions + `/${sessionId}`, {
      archived,
    });
  },

  restoreSession(sessionId: string): Promise<Record<string, unknown>> {
    return apiClient.put<Record<string, unknown>>(API_ENDPOINTS.chat.restore(sessionId));
  },

  editAndResend(
    sessionId: string,
    messageId: string,
    payload: { new_content: string; client_message_id?: string }
  ): Promise<Record<string, unknown>> {
    return apiClient.post<Record<string, unknown>>(
      API_ENDPOINTS.chat.editAndResend(sessionId, messageId),
      payload
    );
  },

  exportSession(sessionId: string, format: 'json' | 'markdown' = 'json'): Promise<Record<string, unknown>> {
    return apiClient.get<Record<string, unknown>>(
      `${API_ENDPOINTS.chat.export(sessionId)}?format=${format}`
    );
  },

  regenerate(sessionId: string, messageId: string, model?: string): Promise<MessageTurnResult> {
    return apiClient
      .post<Record<string, unknown>>(API_ENDPOINTS.chat.regenerate(sessionId, messageId), {
        model: model || 'auto',
      })
      .then(toMessageTurnResult);
  },

  sendFeedback(sessionId: string, messageId: string, rating: number, comment?: string): Promise<{ success: boolean }> {
    return apiClient.post<{ success: boolean }>(
      API_ENDPOINTS.chat.feedbackMessage(sessionId, messageId),
      { rating, comment }
    );
  },

  switchModel(model: string): Promise<{ active_model: string }> {
    return apiClient.post<{ active_model: string }>(API_ENDPOINTS.chat.switchModel, { model });
  },

  getStatus(): Promise<{ status: string; model: string }> {
    return apiClient.get<{ status: string; model: string }>(API_ENDPOINTS.chat.status);
  },

  getModelCatalog(): Promise<ModelCatalog> {
    return apiClient.get<ModelCatalog>(API_ENDPOINTS.models.catalog);
  },

  isTransient(category?: string): boolean {
    return !!category && ['RATE_LIMITED', 'PROVIDER_UNAVAILABLE', 'STREAM_INTERRUPTED', 'INTERNAL_ERROR', 'UNKNOWN_ERROR'].includes(category);
  },
};

export { newClientMessageId };
export default chatApi;