import { create } from 'zustand';
import type {
  ChatMessage,
  SessionInfo,
  ChatStreamChunk,
  ModelCatalog,
  ProviderInfo,
  BrowserContextSummary,
  BrowserEvent,
  ToolDispatchResult,
} from './types';
import type { AgentTask } from '@/features/agents/types';
import chatApi from './api';
import wsClient from '@/lib/websocket-client';
import API_ENDPOINTS from '@/config/api';

const DRAFT_STORAGE_KEY = 'jarvis-chat-drafts';

function loadDraftMap(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(DRAFT_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function saveDraftMap(drafts: Record<string, string>) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(drafts));
  } catch {
    // ignore storage errors
  }
}

interface ChatState {
  messages: ChatMessage[];
  sessions: SessionInfo[];
  currentSessionId: string | null;
  activeModel: string;
  modelCatalog: ModelCatalog | null;
  availableProviders: ProviderInfo[];
  isLoading: boolean;
  isStreaming: boolean;
  streamingContent: string;
  error: string | null;
  connected: boolean;

  // Browser ↔ Chat integration
  browserContext: BrowserContextSummary | null;
  browserEventHistory: BrowserEvent[];
  _browserSubscribers: Set<(event: BrowserEvent) => void>;
  _drafts: Record<string, string>;

  checkConnection: () => Promise<boolean>;
  sendMessage: (content: string) => Promise<void>;
  sendStreamMessage: (content: string) => Promise<void>;
  loadSessions: () => Promise<void>;
  loadSession: (sessionId: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  newSession: () => void;
  switchModel: (model: string) => Promise<void>;
  setActiveModel: (model: string) => void;
  loadModelCatalog: () => Promise<void>;
  clearChat: () => void;
  clearError: () => void;

  // Session restore + message edit/resend (Phase 5)
  restoreSession: (sessionId: string) => Promise<void>;
  editAndResend: (sessionId: string, messageId: string, newContent: string) => Promise<void>;

  // Draft persistence — save/restore unsent drafts keyed by session ID
  saveDraft: (sessionId: string, draft: string) => void;
  loadDraft: (sessionId: string) => string;
  clearDraft: (sessionId: string) => void;

  // Browser integration methods
  setBrowserContext: (context: BrowserContextSummary | null) => void;
  publishBrowserEvent: (event: Omit<BrowserEvent, 'timestamp'> & { type: string }) => void;
  subscribeToBrowserEvents: (callback: (event: BrowserEvent) => void) => () => void;
  sendBrowserEvidence: (evidence: BrowserContextSummary['recent_evidence']) => Promise<void>;
  dispatchToolCall: (toolCall: { name: string; arguments: Record<string, unknown> }) => Promise<ToolDispatchResult>;
  initChat: () => Promise<void>;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  sessions: [],
  currentSessionId: null,
  activeModel: 'auto',
  modelCatalog: null,
  availableProviders: [],
  isLoading: false,
  isStreaming: false,
  streamingContent: '',
  error: null,
  connected: false,

  // Browser ↔ Chat integration
  browserContext: null,
  browserEventHistory: [],
  _browserSubscribers: new Set(),
  _drafts: {},

  checkConnection: async () => {
    try {
      const res = await fetch(API_ENDPOINTS.health, { method: 'GET' });
      const ok = res.ok;
      set({ connected: ok });
      return ok;
    } catch {
      set({ connected: false });
      return false;
    }
  },

  // ---- Draft persistence (unsent input keyed by session ID) ----
  saveDraft: (sessionId: string, draft: string) => {
    if (!sessionId) return;
    const drafts = { ...get()._drafts };
    if (draft.trim() === '') {
      delete drafts[sessionId];
    } else {
      drafts[sessionId] = draft;
    }
    set({ _drafts: drafts });
    saveDraftMap(drafts);
  },

  loadDraft: (sessionId: string) => {
    if (!sessionId) return '';
    const drafts = { ...get()._drafts, ...loadDraftMap() };
    return drafts[sessionId] || '';
  },

  clearDraft: (sessionId: string) => {
    if (!sessionId) return;
    const drafts = { ...get()._drafts };
    delete drafts[sessionId];
    set({ _drafts: drafts });
    saveDraftMap(drafts);
  },

  // ---- Session restore + message edit/resend (Phase 5) ----
  restoreSession: async (sessionId: string) => {
    try {
      await chatApi.restoreSession(sessionId);
      set((state) => ({
        sessions: state.sessions.map((s) =>
          s.session_id === sessionId ? { ...s, archived: false } : s
        ),
      }));
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to restore session' });
    }
  },

  editAndResend: async (sessionId: string, messageId: string, newContent: string) => {
    try {
      const result = await chatApi.editAndResend(sessionId, messageId, {
        new_content: newContent,
      });
      // Update the user message content locally and append a fresh assistant
      // placeholder. The backend truncates any superseded assistant response.
      set((state) => ({
        messages: state.messages
          .map((msg) =>
            msg.id === messageId ? { ...msg, content: newContent, interrupted: false } : msg
          )
          .concat({
            id: `msg-${Date.now()}`,
            role: 'assistant',
            content: '',
            timestamp: new Date().toISOString(),
            status: 'THINKING',
          }),
        isLoading: true,
        error: null,
      }));
      // Refresh sessions after edit/resend
      get().loadSessions();
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : 'Failed to edit and resend message',
      });
    }
  },

  sendMessage: async (content: string) => {
    if (!content.trim()) return;

    // Save draft before sending (network failure resilience)
    get().saveDraft(get().currentSessionId || 'default', content.trim());

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: content.trim(),
      timestamp: new Date().toISOString(),
    };

    set((state) => ({
      messages: [...state.messages, userMessage],
      isLoading: true,
      error: null,
    }));

    try {
      const response = await chatApi.sendMessage({
        message: content.trim(),
        session_id: get().currentSessionId,
        model: get().activeModel,
        browser_context: get().browserContext ?? undefined,
      });

      const assistantMessage: ChatMessage = {
        id: `msg-${Date.now() + 1}`,
        role: 'assistant',
        content: response.message ?? '',
        timestamp: response.timestamp || new Date().toISOString(),
        model: response.model,
        sources: response.sources,
        tool_calls: response.tool_calls,
        presentation: response.presentation,
        canonical_task_id: response.canonical_task_id,
        presentation_revision_id: response.presentation_revision_id,
        metadata: {
          ...(response.runtime_command_id
            ? { runtime_command_id: response.runtime_command_id }
            : {}),
          ...(response.canonical_task_id
            ? { canonical_task_id: response.canonical_task_id }
            : {}),
          ...(response.presentation_revision_id
            ? { presentation_revision_id: response.presentation_revision_id }
            : {}),
        },
      };

      set((state) => ({
        messages: [...state.messages, assistantMessage],
        currentSessionId: response.session_id || state.currentSessionId,
        isLoading: false,
        connected: true,
      }));

      // Clear draft on success
      if (get().currentSessionId) {
        get().clearDraft(get().currentSessionId);
      }

      get().loadSessions();
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : 'Failed to send message',
        connected: false,
      });
    }
  },

  sendStreamMessage: async (content: string) => {
    if (!content.trim()) return;

    // Save draft before sending
    get().saveDraft(get().currentSessionId || 'default', content.trim());

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: content.trim(),
      timestamp: new Date().toISOString(),
    };

    const assistantId = `msg-${Date.now() + 1}`;
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
    };

    set((state) => ({
      messages: [...state.messages, userMessage, assistantMessage],
      isStreaming: true,
      streamingContent: '',
      error: null,
    }));

    await chatApi.sendStreamingMessage(
      { message: content.trim(), session_id: get().currentSessionId, stream: true, browser_context: get().browserContext ?? undefined },
      (chunk: ChatStreamChunk) => {
        if (chunk.type === 'meta' && chunk.session_id) {
          set({ currentSessionId: chunk.session_id });
        } else if (chunk.type === 'chunk' && chunk.text) {
          set((state) => ({
            streamingContent: state.streamingContent + (chunk.text || ''),
            messages: state.messages.map((msg) =>
              msg.id === assistantId
                ? { ...msg, content: state.streamingContent + (chunk.text || '') }
                : msg
            ),
          }));
        } else if (chunk.type === 'complete' || chunk.type === 'done') {
          set((state) => {
            const finalContent = chunk.content || state.streamingContent;
            return {
              isStreaming: false,
              streamingContent: '',
              messages: state.messages.map((msg) =>
                msg.id === assistantId
                  ? {
                      ...msg,
                      content: finalContent,
                      confidence: chunk.confidence,
                      sources: chunk.sources,
                      tool_calls: chunk.tool_calls,
                      presentation: chunk.presentation,
                      canonical_task_id: chunk.canonical_task_id,
                      presentation_revision_id: chunk.presentation_revision_id,
                      metadata: {
                        ...(msg.metadata ?? {}),
                        ...(chunk.runtime_command_id
                          ? { runtime_command_id: chunk.runtime_command_id }
                          : {}),
                        ...(chunk.canonical_task_id
                          ? { canonical_task_id: chunk.canonical_task_id }
                          : {}),
                        ...(chunk.presentation_revision_id
                          ? { presentation_revision_id: chunk.presentation_revision_id }
                          : {}),
                      },
                      status: chunk.status || 'COMPLETED',
                    }
                  : msg
              ),
            };
          });
          // Clear draft on successful completion
          if (chunk.type === 'complete' && get().currentSessionId) {
            get().clearDraft(get().currentSessionId);
          }
          get().loadSessions();
        } else if (chunk.type === 'error') {
          set({ isStreaming: false, error: chunk.error || 'Stream error' });
        } else if (chunk.type === 'status' && chunk.status === 'STREAM_INTERRUPTED') {
          // Handle STREAM_INTERRUPTED status - mark as interrupted and clear draft
          set((state) => ({
            isStreaming: false,
            messages: state.messages.map((msg) =>
              msg.id === assistantId
                ? { ...msg, content: state.streamingContent, status: 'STREAM_INTERRUPTED', interrupted: true }
                : msg
            ),
          }));
          if (get().currentSessionId) {
            get().clearDraft(get().currentSessionId);
          }
        }
      },
      (error: Error) => {
        const isTransient = chatApi.isTransient('');
        set({ isStreaming: false, error: error.message });
        if (isTransient && get().currentSessionId) {
          // Keep draft for retry on transient errors
        }
      },
      () => {
        set({ isStreaming: false });
      }
    );
  },

  loadSessions: async () => {
    try {
      const result = await chatApi.getSessions();
      set({ sessions: result.sessions });
    } catch {
      // silently fail session loading
    }
  },

  loadSession: async (sessionId: string) => {
    try {
      set({ isLoading: true });
      const data = await chatApi.getSessionHistory(sessionId);
      const messages = (data.messages || []).map((msg) => ({
        id: `msg-${Date.now()}-${Math.random()}`,
        role: (msg.role || 'assistant') as 'user' | 'assistant' | 'system',
         content: (msg.content || msg.response || msg.answer || '') as string,
        timestamp: (msg.timestamp as string) || new Date().toISOString(),
        model: msg.model as string | undefined,
        presentation: msg.presentation as ChatMessage['presentation'],
        sources: msg.sources as string[] | undefined,
        tool_calls: msg.tool_calls as ChatMessage['tool_calls'],
        canonical_task_id: msg.canonical_task_id as string | undefined,
        presentation_revision_id: msg.presentation_revision_id as string | undefined,
      }));
      set({ messages, currentSessionId: sessionId, isLoading: false });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : 'Failed to load session',
      });
    }
  },

  deleteSession: async (sessionId: string) => {
    try {
      await chatApi.deleteSession(sessionId);
      const { currentSessionId } = get();
      if (currentSessionId === sessionId) {
        set({ messages: [], currentSessionId: null });
      }
      get().loadSessions();
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to delete session' });
    }
  },

  newSession: () => {
    // Clear draft for the session when creating a new one
    set({ messages: [], currentSessionId: null, streamingContent: '' });
  },

  switchModel: async (model: string) => {
    try {
      const result = await chatApi.switchModel(model);
      set({ activeModel: result.active_model });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to switch model' });
    }
  },

  setActiveModel: (model: string) => set({ activeModel: model }),

  loadModelCatalog: async () => {
    try {
      const catalog = await chatApi.getModelCatalog();
      // Include providers that are either available OR configured (key set, even if unhealthy)
      const configured = catalog.providers.filter(
        (p) => p.available || p.authorized || p.configured
      );
      set({
        modelCatalog: catalog,
        availableProviders: configured,
        activeModel: catalog.default_model || 'auto',
      });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to load model catalog' });
    }
  },

  clearChat: () => set({ messages: [], streamingContent: '' }),

  clearError: () => set({ error: null }),

  // ---- Browser ↔ Chat integration ----

  /// Subscribe to browser events on init so chat context stays in sync.
  initChat: async () => {
    try {
      const { useBrowserStore } = await import('@/features/browser/store');
      const unsubscribe = useBrowserStore.getState().subscribeToChat((event) => {
        get().publishBrowserEvent(event as Omit<BrowserEvent, 'timestamp'> & { type: string });
        // Auto-update browser context when evidence is captured
        if (event.type === 'evidence_captured') {
          set({ browserContext: useBrowserStore.getState().getBrowserContextSummary() });
        }
      });
      // Store the unsubscribe fn so it can be cleaned up later
      (get() as any)._chatUnsubscribe = unsubscribe;
      set({ browserContext: useBrowserStore.getState().getBrowserContextSummary() });
    } catch {
      // Browser store not available yet — events will connect later
    }
  },

  setBrowserContext: (context) => {
    set({ browserContext: context });
  },

  publishBrowserEvent: (event) => {
    const fullEvent = {
      ...event,
      timestamp: new Date().toISOString(),
    } as BrowserEvent;
    const subscribers = get()._browserSubscribers;
    set((state) => ({
      browserEventHistory: [fullEvent, ...state.browserEventHistory.slice(0, 99)],
    }));
    // Notify all subscribers
    subscribers.forEach((cb) => cb(fullEvent));
  },

  subscribeToBrowserEvents: (callback) => {
    const subscribers = get()._browserSubscribers;
    subscribers.add(callback);
    // Return unsubscribe function
    return () => {
      subscribers.delete(callback);
    };
  },

  sendBrowserEvidence: async (evidence) => {
    if (!evidence || evidence.length === 0) return;
    const summary: string = evidence
      .map((e: NonNullable<BrowserContextSummary['recent_evidence']>[number]) => e.claim || '')
      .filter(Boolean)
      .join('; ');
    const systemMessage: ChatMessage = {
      id: `sys-${Date.now()}`,
      role: 'system',
      content: `[Browser context] New evidence from web research: ${summary}`,
      timestamp: new Date().toISOString(),
    };
    set((state) => ({ messages: [...state.messages, systemMessage] }));
  },

  dispatchToolCall: async (toolCall) => {
    const { name, arguments: args } = toolCall;

    // Map known tool names to browser store actions.
    // This enables chat-computed tool calls to execute in the browser.
    if (name === 'browser_navigate') {
      // No-op: navigation must go through the browser store directly.
      return { success: false, error: 'Use browser store directly for navigation' };
    }

    // Try dynamic import to avoid circular dependency
    try {
      const { useBrowserStore } = await import('@/features/browser/store');
      const browserStore = useBrowserStore.getState();

      if (name === 'browser_create_action') {
        const action = await browserStore.createAction(args as Record<string, unknown>);
        if (action) {
          return { success: true, action_type: name, result: action };
        }
        return { success: false, error: 'createAction returned null' };
      }

      if (name === 'browser_capture_evidence') {
        const evidence = await browserStore.captureEvidence(args as unknown as Parameters<typeof browserStore.captureEvidence>[0]);
        if (evidence) {
          return { success: true, action_type: name, result: evidence };
        }
        return { success: false, error: 'captureEvidence returned null' };
      }

      if (name === 'browser_execute_action') {
        const result = await browserStore.executeAction(args.action_id as string);
        if (result) {
          return { success: true, action_type: name, result };
        }
        return { success: false, error: 'executeAction returned null' };
      }

      if (name === 'browser_create_task') {
        const task = await browserStore.createTask(args as Record<string, unknown>);
        if (task) {
          return { success: true, action_type: name, result: task };
        }
        return { success: false, error: 'createTask returned null' };
      }

      // ── Mission integration tools ──────────────────────────────────────────
      // ... additional tool handlers can be added here
    } catch (error) {
      return { success: false, error: 'Failed to execute browser tool' };
    }

    return { success: false, error: 'Unknown tool: ' + name };
  },
}));

// Re-export draft helpers for use in components
export { loadDraftMap, saveDraftMap };
export default useChatStore;