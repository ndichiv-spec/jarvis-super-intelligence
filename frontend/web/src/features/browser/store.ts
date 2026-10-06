/**
 * Browser feature store — Zustand.
 *
 * Persistent browser context: sessions, tabs, bookmarks, history,
 * evidence, downloads, and AI page-understanding state.
 *
 * Integrates with the platform store to publish activity events.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type {
  BrowserSession,
  BrowserTab,
  AIContext,
  BrowserEvidence,
  BrowserBookmark,
  SecurityReport,
  InjectionCheck,
  PrivacyMode,
  BrowserAction,
  ActionQueue,
  BrowserTask,
  TaskCheckpoint,
  BrowserWorkspace,
  BrowserTelemetryEntry,
  SourceGraph,
  TimelineEntry,
  ModelRoute,
  RemoteBrowserStatus,
  RemoteBrowserSession,
  AuthState,
  HighRiskDomResult,
  ArtifactCollection,
  ResourceUsage,
  ObserveActResult,
  TaskPlan,
  PageState,
  ActionExecutionResult,
  MissionBrowserContext,
  SummonResult,
  EvidencePromotionResult,
  EvidenceToMissionResult,
  EvidenceToMemoryResult,
  BrowserError,
  BrowserErrorType,
  BrowserErrorCategory,
  NetworkStatus,
  BrowserContextSummary,
  SecurityIssue,
  NetworkDiagnosticResult,
  DnsDiagnosticsResult,
  ProxyDiagnosticsResult,
  BrowserHealthStatus,
  RecoveryResult,
  NetworkEventEntry,
  NavigationTimelineEntry,
} from './types';
import type { BrowserStore } from './types';
import browserApi from './api';
import wsClient from '@/lib/websocket-client';
import API_ENDPOINTS from '@/config/api';
import { usePlatformStore } from '@/stores/platform-store';

const _now = () => new Date().toISOString();

async function _controlActiveNavigation(action: 'back' | 'forward' | 'reload'): Promise<boolean> {
  const state = useBrowserStore.getState();
  const sessionId = state.activeSessionId;
  const tabId = state.activeTabId;
  if (!sessionId || !tabId || !state.tabs[tabId]) return false;

  useBrowserStore.setState({ isLoading: true, error: null });
  try {
    const result = await browserApi.controlNavigation(sessionId, tabId, action);
    if (!result.navigated) {
      useBrowserStore.setState({ isLoading: false });
      return false;
    }
    useBrowserStore.setState((current) => {
      const tab = current.tabs[tabId];
      if (!tab) return { isLoading: false };
      return {
        tabs: {
          ...current.tabs,
          [tabId]: {
            ...tab,
            url: result.url,
            is_loading: true,
            updated_at: _now(),
            private_ephemeral_url: result.privacy_mode === 'private',
            navigation_revision: (tab.navigation_revision ?? 0) + (action === 'reload' ? 1 : 0),
          },
        },
        sessions: current.sessions.map((session) => session.id === sessionId
          ? { ...session, active_tab_id: tabId }
          : session),
        activeSessionId: sessionId,
        activeTabId: tabId,
        privacyMode: result.privacy_mode,
        aiContext: null,
        isLoading: false,
      };
    });
    _publishToChat({
      type: 'tab_navigated',
      session_id: sessionId,
      tab_id: tabId,
      data: { url: result.url, action, privacy_mode: result.privacy_mode },
    });
    return true;
  } catch (error) {
    useBrowserStore.setState({
      isLoading: false,
      error: error instanceof Error ? error.message : `Unable to ${action} browser tab`,
    });
    return false;
  }
}

/** Publish a browser event to all registered chat subscribers. */
function _publishToChat(event: {
  type: string;
  session_id?: string | null;
  tab_id?: string | null;
  data: Record<string, unknown>;
}) {
  const fullEvent = { ...event, timestamp: _now() };
  _chatSubscribers.forEach((cb) => cb(fullEvent));
}

let _wsUnsubscribe: (() => void) | null = null;
const _chatSubscribers: Set<(event: { type: string; timestamp: string; session_id?: string | null; tab_id?: string | null; data: Record<string, unknown> }) => void> = new Set();

/** Classify an error into a structured BrowserError based on status code or message. */
function _classifyError(e: unknown, endpoint?: string): BrowserError {
  const msg = e instanceof Error ? e.message : String(e ?? 'Unknown error');
  const isAbort = (e instanceof Error && e.name === 'AbortError');

  // Try to extract status code from Axios-style or fetch-style errors
  let status: number | undefined;
  if (e && typeof e === 'object' && 'response' in e) {
    const resp = (e as any).response;
    if (resp && typeof resp === 'object') {
      status = resp.status;
    }
  }

  // Extract the classified error category from the API client's error details
  // (set by the api-client from the X-Browser-Error-Category response header).
  let errorCategory: string | undefined;
  if (e && typeof e === 'object' && 'details' in e) {
    const details = (e as any).details;
    if (details && typeof details === 'object' && 'error_category' in details) {
      errorCategory = details.error_category;
    }
  }

  let errorType: BrowserErrorType = 'unknown';
  if (status === 401 || /\b401\b/.test(msg)) errorType = 'auth';
  else if (status === 403 || /\b403\b/.test(msg)) errorType = 'permission';
  else if (status === 400 || status === 422) errorType = 'validation';
  else if (status !== undefined && (status >= 500 || status === 502 || status === 503 || status === 504)) errorType = 'server';
  else if (msg.toLowerCase().includes('network') || msg.toLowerCase().includes('fetch') || isAbort) errorType = 'network';

  const browserError: BrowserError = {
    type: errorType,
    message: msg,
    status_code: status,
    endpoint,
    timestamp: _now(),
    retry_count: 0,
    can_retry: errorType === 'network' || errorType === 'server',
  };
  // Attach the classified error category if available (may be undefined)
  (browserError as any).error_category = errorCategory;
  return browserError;
}

export const useBrowserStore = create<BrowserStore>()(
  persist(
    (set, get) => ({
      sessions: [],
      tabs: {},
      activeSessionId: null,
      activeTabId: null,
      isLoading: false,
      error: null,
      privacyMode: 'standard',
      showAIContext: true,
      showResearchControls: false,
      showEvidencePanel: false,
      showSecurityPanel: false,
      showDownloadsPanel: false,
      showBookmarksPanel: false,
      showHistoryPanel: false,
      aiContext: null,
      bookmarks: [],
      history: [],
      downloads: [],
      evidence: [],
      searchResults: [],
      searchQuery: '',
      isSearching: false,
      securityReport: null,
      status: {},
      // Actions
      actions: {},
      actionQueues: {},
      // Tasks
      tasks: {},
      taskCheckpoints: {},
      // Workspaces
      workspaces: {},
      // Telemetry & Timeline
      telemetry: [],
      timeline: [],
      // Source Graphs
      sourceGraphs: [],
      // Page states
      pageStates: {},
      // Model routing
      modelRoute: null,
      // Remote browser
      remoteBrowserStatus: null,
      // Auth state
      authState: null,
      // High-risk DOM
      highRiskDomResult: null,
      // Artifacts
      artifacts: null,
      // Resource usage
      resourceUsage: null,
      // Observe-Act result
      observeActResult: null,
      // Current task plan
      currentTaskPlan: null,

      // Error & offline state (upgraded error handling)
      isOffline: false,
      networkStatus: { is_online: true, is_backend_reachable: true, last_checked: null },
      errorHistory: [],
      retryCount: 0,
      lastFailedRequest: null,

      // Network Intelligence Layer state (spec §51)
      networkEvents: [],
      navigationTimeline: [],
      browserHealth: null,
      lastDiagnosticsResult: null,
      isRecovering: false,
      recoveryError: null,

      // Initialization
      initialized: false,

      createSession: async (name?, privacyMode?, researchSessionId?, missionId?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.createSession(name, privacyMode, researchSessionId, missionId);
          const session = resp.session;
          set((s: BrowserStore) => ({ sessions: [session, ...s.sessions], activeSessionId: session.id }));
          usePlatformStore.getState().addActivity({
            domain: 'browser', operation: 'session_created',
            title: 'Browser session created', detail: session.name, severity: 'info',
          });
          return session;
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to create session' });
          return null;
        } finally {
          set({ isLoading: false });
        }
      },

      loadSessions: async () => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.listSessions();
          set({ sessions: resp.sessions, isLoading: false });
          if (resp.sessions.length > 0 && !get().activeSessionId) {
            const first = resp.sessions[0];
            set({ activeSessionId: first.id });
            await get().loadTabs(first.id);
          }
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load sessions' });
        }
      },

      setActiveSession: (sessionId: string | null) => {
        set({ activeSessionId: sessionId, activeTabId: null, aiContext: null });
        if (sessionId) void get().loadTabs(sessionId);
      },

      updateSession: async (sessionId, patch) => {
        try {
          const resp = await browserApi.updateSession(sessionId, patch);
          set((s: BrowserStore) => ({ sessions: s.sessions.map((sess: BrowserSession) =>
            sess.id === sessionId ? resp.session : sess) }));
          return resp.session;
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to update session' });
          return null;
        }
      },

      deleteSession: async (sessionId) => {
        try {
          await browserApi.deleteSession(sessionId);
          set((s: BrowserStore) => ({
            sessions: s.sessions.filter((sess: BrowserSession) => sess.id !== sessionId),
            tabs: Object.fromEntries(Object.entries(s.tabs).filter(([, t]: [string, BrowserTab]) => t.session_id !== sessionId)),
            activeSessionId: s.activeSessionId === sessionId ? null : s.activeSessionId,
          }));
          usePlatformStore.getState().addActivity({
            domain: 'browser', operation: 'session_deleted', title: 'Browser session closed', severity: 'info',
          });
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to delete session' });
        }
      },

      createTab: async (sessionId, url?, title?, isPinned?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.createTab(sessionId, url, title, isPinned);
          const privateSession = get().sessions.find((session: BrowserSession) =>
            session.id === sessionId)?.privacy_mode === 'private';
          const tab = {
            ...resp.tab,
            private_ephemeral_url: privateSession && resp.tab.url !== 'about:blank',
          };
          set((s: BrowserStore) => ({
            tabs: { ...s.tabs, [tab.id]: tab },
            sessions: s.sessions.map((sess: BrowserSession) =>
              sess.id === sessionId
                ? { ...sess, tabs: [...sess.tabs, tab.id], active_tab_id: tab.id }
                : sess),
            activeTabId: tab.id,
            isLoading: false,
          }));
          usePlatformStore.getState().addActivity({
            domain: 'browser', operation: 'tab_created',
            title: 'New tab opened',
            detail: privateSession ? 'Private tab' : tab.title || tab.url,
            severity: 'info',
          });
          return tab;
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to create tab', isLoading: false });
          return null;
        }
      },

      loadTabs: async (sessionId?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.listTabs(sessionId);
          const tabMap: Record<string, BrowserTab> = {};
          resp.tabs.forEach((t: BrowserTab) => { tabMap[t.id] = t; });
          set({ tabs: tabMap, isLoading: false });
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load tabs' });
        }
      },

      setActiveTab: (tabId: string | null) => {
        set({ activeTabId: tabId, aiContext: null });
      },

      closeTab: async (tabId) => {
        try {
          await browserApi.closeTab(tabId);
          set((s: BrowserStore) => {
            const { [tabId]: _, ...rest } = s.tabs;
            const sessions = s.sessions.map((sess: BrowserSession) => {
              const newTabs = sess.tabs.filter((t) => t !== tabId);
              return { ...sess, tabs: newTabs,
                active_tab_id: sess.active_tab_id === tabId ? newTabs[newTabs.length - 1] || null : sess.active_tab_id };
            });
            return {
              tabs: rest,
              sessions,
              activeTabId: s.activeTabId === tabId
                ? (sessions.find((sess: BrowserSession) => sess.active_tab_id)?.active_tab_id ?? null)
                : s.activeTabId,
            };
          });
          usePlatformStore.getState().addActivity({
            domain: 'browser', operation: 'tab_closed', title: 'Tab closed', severity: 'info',
          });
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to close tab' });
        }
      },

      navigate: async (sessionId, url, tabId?, privacyMode?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.navigate(sessionId, url, tabId, privacyMode);
          if (resp.blocked) {
            set({ error: resp.reason || 'Navigation blocked', isLoading: false });
            usePlatformStore.getState().addActivity({
              domain: 'security', operation: 'navigation_blocked',
              title: 'Navigation blocked', detail: `${resp.reason} (${url})`, severity: 'high',
            });
            return resp;
          }
          set((s: BrowserStore) => {
            const tab = s.tabs[resp.window_id];
            if (!tab) return {};
            return {
              tabs: {
                ...s.tabs,
                [tab.id]: {
                  ...tab,
                  url: resp.url,
                  is_loading: true,
                  updated_at: _now(),
                  private_ephemeral_url: resp.privacy_mode === 'private',
                },
              },
              activeTabId: tab.id,
              activeSessionId: sessionId,
            };
          });
          if (resp.privacy_mode && resp.privacy_mode !== get().privacyMode) {
            set({ privacyMode: resp.privacy_mode as PrivacyMode });
          }
          usePlatformStore.getState().addActivity({
            domain: 'browser', operation: 'navigate', title: 'Navigated to page', detail: resp.url, severity: 'info',
          });
          _publishToChat({
            type: 'tab_navigated',
            session_id: sessionId,
            tab_id: resp.window_id,
            data: { url: resp.url, privacy_mode: resp.privacy_mode },
          });
          set({ isLoading: false });
          return resp;
        } catch (e) {
          const classifiedError = _classifyError(e, 'navigate');
          set({
            error: e instanceof Error ? e.message : 'Navigation failed',
            isLoading: false,
            lastFailedRequest: url,
          });
          set((s: BrowserStore) => ({
            errorHistory: [classifiedError, ...s.errorHistory.slice(0, 49)],
          }));
          // Publish the classified error to chat subscribers for AI reasoning
          _publishToChat({
            type: 'navigation_error',
            session_id: sessionId,
            tab_id: tabId ?? undefined,
            data: {
              url,
              error: classifiedError.message,
              error_category: (classifiedError as any).error_category || null,
              status_code: classifiedError.status_code,
            },
          });
          return null;
        }
      },

      goBack: () => _controlActiveNavigation('back'),
      goForward: () => _controlActiveNavigation('forward'),
      reload: () => _controlActiveNavigation('reload'),

      extractPage: async (url, content?, userSelection?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.extractPage(url, content, userSelection);
          const aiContext: AIContext = {
            metadata: {
              url: resp.url, title: resp.title, favicon: '',
              description: (resp.metadata?.description as string) ?? '',
              image: (resp.metadata?.image as string) ?? '',
              word_count: resp.text_length,
            },
            text: resp.text, text_length: resp.text_length,
            structure: resp.structure as unknown as AIContext['structure'],
            entities: resp.entities as unknown as AIContext['entities'],
            prompt_injection: resp.prompt_injection,
            selected_content: userSelection ?? resp.selection ?? null,
          };
          set({ aiContext, isLoading: false });
          _publishToChat({
            type: 'page_extracted',
            data: { url: resp.url, title: resp.title, word_count: resp.text_length },
          });
          if (resp.prompt_injection.flagged) {
            usePlatformStore.getState().addActivity({
              domain: 'security', operation: 'prompt_injection_detected',
              title: 'Prompt injection detected',
              detail: `Confidence: ${resp.prompt_injection.confidence}`, severity: 'high',
            });
          }
          return aiContext;
        } catch (e) {
          const classifiedError = _classifyError(e, 'extract');
          set((s: BrowserStore) => ({
            errorHistory: [classifiedError, ...s.errorHistory.slice(0, 49)],
          }));
          set({ error: e instanceof Error ? e.message : 'Failed to extract page', isLoading: false });
          return null;
        }
      },

      clearAIContext: () => set({ aiContext: null }),

      search: async (query, sessionId?) => {
        if (!query.trim()) return [];
        set({ isSearching: true, searchQuery: query, error: null });
        try {
          const resp = await browserApi.search(query, sessionId);
          set({ searchResults: resp.results, isSearching: false });
          usePlatformStore.getState().addActivity({
            domain: 'browser', operation: 'search',
            title: `Web search: ${query}`, detail: `${resp.results.length} results`, severity: 'info',
          });
          return resp.results;
        } catch (e) {
          set({ isSearching: false, error: e instanceof Error ? e.message : 'Search failed' });
          return [];
        }
      },

      captureEvidence: async (input) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.captureEvidence(input);
          set((s: BrowserStore) => ({ evidence: [resp.evidence, ...s.evidence] }));
          usePlatformStore.getState().addActivity({
            domain: 'research', operation: 'evidence_captured',
            title: 'Evidence captured from browser',
            detail: input.claim || input.selected_passage.slice(0, 80), severity: 'info',
          });
          _publishToChat({
            type: 'evidence_captured',
            session_id: input.research_session_id ?? null,
            data: { evidence: resp.evidence },
          });
          set({ isLoading: false });
          return resp.evidence;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to capture evidence' });
          return null;
        }
      },

      loadEvidence: async (researchSessionId?, missionId?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.listEvidence(researchSessionId, missionId);
          set({ evidence: resp.evidence, isLoading: false });
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load evidence' });
        }
      },

      loadBookmarks: async (q?, tags?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.listBookmarks(q, tags);
          set({ bookmarks: resp.bookmarks, isLoading: false });
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load bookmarks' });
        }
      },

      addBookmark: async (input) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.addBookmark(input);
          set((s: BrowserStore) => ({ bookmarks: [resp.bookmark, ...s.bookmarks] }));
          usePlatformStore.getState().addActivity({
            domain: 'browser', operation: 'bookmark_added',
            title: 'Bookmark saved', detail: input.title, severity: 'info',
          });
          set({ isLoading: false });
          return resp.bookmark;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to add bookmark' });
          return null;
        }
      },

      deleteBookmark: async (id) => {
        try {
          await browserApi.deleteBookmark(id);
          set((s: BrowserStore) => ({ bookmarks: s.bookmarks.filter((b: BrowserBookmark) => b.id !== id) }));
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to delete bookmark' });
        }
      },

      loadHistory: async (q?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.getHistory(q);
          set({ history: resp.history, isLoading: false });
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load history' });
        }
      },

      loadDownloads: async () => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.getDownloads();
          set({ downloads: resp.downloads, isLoading: false });
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load downloads' });
        }
      },

      checkPromptInjection: async (content) => {
        try {
          const resp = await browserApi.checkPromptInjection(content);
          return { flagged: resp.flagged, confidence: resp.confidence, matches: resp.matches };
        } catch {
          return { flagged: false, confidence: 0, matches: [] };
        }
      },

      loadSecurityReport: async (sessionId?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.getSecurityReport(sessionId);
          set({ securityReport: resp, isLoading: false });
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load security report' });
        }
      },

      loadStatus: async () => {
        try {
          const resp = await browserApi.getStatus();
          set({ status: resp });
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to load browser status' });
        }
      },

      // ---- Actions ----
      createAction: async (body) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.createAction(body);
          set((s: BrowserStore) => ({
            actions: { ...s.actions, [resp.action.id]: resp.action },
          }));
          set({ isLoading: false });
          return resp.action;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to create action' });
          return null;
        }
      },

      listActions: async (sessionId?, status?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.listActions(sessionId, status);
          set((s: BrowserStore) => {
            const actions: Record<string, BrowserAction> = { ...s.actions };
            resp.actions.forEach((a: BrowserAction) => { actions[a.id] = a; });
            return { actions, isLoading: false };
          });
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load actions' });
        }
      },

      executeAction: async (actionId) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.executeAction(actionId);
          if (resp.requires_confirmation && Object.keys(resp).length > 0) {
            return {
              executed: false,
              action_id: actionId,
              type: '',
              requires_confirmation: true,
              message: resp.message,
            };
          }
          set((s: BrowserStore) => ({
            actions: {
              ...s.actions,
              [actionId]: { ...s.actions[actionId], status: resp.executed ? 'completed' : 'failed', result: resp, executed_at: new Date().toISOString() } as BrowserAction,
            },
          }));
          set({ isLoading: false });
          return resp as ActionExecutionResult;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to execute action' });
          return null;
        }
      },

      replayActions: async (sessionId) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.replayActions(sessionId);
          set({ isLoading: false });
          return resp.actions;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to replay actions' });
          return null;
        }
      },

      // ---- Observe → Act Loop ----
      runObserveActLoop: async (body) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.observeActLoop(body);
          set({ observeActResult: resp as unknown as ObserveActResult, isLoading: false });
          return resp as unknown as ObserveActResult;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Observe-Act loop failed' });
          return null;
        }
      },

      // ---- Page State ----
      loadPageState: async (body) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.getPageState(body);
          set((s: BrowserStore) => ({
            pageStates: { ...s.pageStates, [resp.page_state_id]: resp.page_state as unknown as PageState },
            isLoading: false,
          }));
          return resp;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load page state' });
          return null;
        }
      },

      // ---- Tasks ----
      createTask: async (body) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.createTask(body);
          set((s: BrowserStore) => ({
            tasks: { ...s.tasks, [resp.task.id]: resp.task },
          }));
          set({ isLoading: false });
          return resp.task;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to create task' });
          return null;
        }
      },

      listTasks: async (sessionId?, status?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.listTasks(sessionId, status);
          set((s: BrowserStore) => {
            const tasks: Record<string, BrowserTask> = { ...s.tasks };
            resp.tasks.forEach((t: BrowserTask) => { tasks[t.id] = t; });
            return { tasks, isLoading: false };
          });
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load tasks' });
        }
      },

      executeTaskStep: async (taskId, stepId) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.executeTaskStep(taskId, stepId);
          set((s: BrowserStore) => ({
            tasks: {
              ...s.tasks,
              [taskId]: { ...s.tasks[taskId], current_step_index: resp.step?.verified ? (s.tasks[taskId]?.current_step_index ?? 0) + 1 : (s.tasks[taskId]?.current_step_index ?? 0) } as BrowserTask,
            },
          }));
          set({ isLoading: false });
          return resp;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to execute task step' });
          return null;
        }
      },

      createTaskCheckpoint: async (taskId) => {
        try {
          const resp = await browserApi.createTaskCheckpoint(taskId);
          set((s: BrowserStore) => ({
            taskCheckpoints: { ...s.taskCheckpoints, [resp.checkpoint.id]: resp.checkpoint },
          }));
          return resp.checkpoint;
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to create checkpoint' });
          return null;
        }
      },

      resumeTask: async (taskId) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.resumeTask(taskId);
          set((s: BrowserStore) => ({
            tasks: { ...s.tasks, [taskId]: resp.task },
          }));
          set({ isLoading: false });
          return resp;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to resume task' });
          return null;
        }
      },

      pauseTask: async (taskId) => {
        try {
          const resp = await browserApi.pauseTask(taskId);
          set((s: BrowserStore) => ({
            tasks: { ...s.tasks, [taskId]: resp.task },
          }));
          return resp;
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to pause task' });
          return null;
        }
      },

      cancelTask: async (taskId) => {
        try {
          const resp = await browserApi.cancelTask(taskId);
          set((s: BrowserStore) => ({
            tasks: { ...s.tasks, [taskId]: resp.task },
          }));
          return resp;
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to cancel task' });
          return null;
        }
      },

      getTaskPlan: async (taskId) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.getTaskPlan(taskId);
          set({ currentTaskPlan: resp, isLoading: false });
          return resp;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load task plan' });
          return null;
        }
      },

      // ---- Workspaces ----
      createWorkspace: async (body) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.createWorkspace(body);
          set((s: BrowserStore) => ({
            workspaces: { ...s.workspaces, [resp.workspace.id]: resp.workspace },
          }));
          set({ isLoading: false });
          return resp.workspace;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to create workspace' });
          return null;
        }
      },

      listWorkspaces: async () => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.listWorkspaces();
          const workspaceMap: Record<string, BrowserWorkspace> = {};
          resp.workspaces.forEach((w: BrowserWorkspace) => { workspaceMap[w.id] = w; });
          set({ workspaces: workspaceMap, isLoading: false });
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load workspaces' });
        }
      },

      updateWorkspace: async (workspaceId, patch) => {
        try {
          const resp = await browserApi.updateWorkspace(workspaceId, patch);
          set((s: BrowserStore) => ({
            workspaces: { ...s.workspaces, [workspaceId]: resp.workspace },
          }));
          return resp.workspace;
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to update workspace' });
          return null;
        }
      },

      associateWorkspace: async (workspaceId, body) => {
        try {
          const resp = await browserApi.associateWorkspace(workspaceId, body);
          set((s: BrowserStore) => ({
            workspaces: { ...s.workspaces, [workspaceId]: resp.workspace },
          }));
          return resp.workspace;
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to associate workspace' });
          return null;
        }
      },

      // ---- Telemetry ----
      loadTelemetry: async (sessionId?, limit?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.getTelemetry(sessionId, limit);
          set({ telemetry: resp.telemetry, isLoading: false });
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load telemetry' });
        }
      },

      recordTelemetry: async (body) => {
        try {
          const resp = await browserApi.recordTelemetry(body);
          set((s: BrowserStore) => ({
            telemetry: [...s.telemetry, resp.telemetry],
          }));
          return resp.telemetry;
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to record telemetry' });
          return null;
        }
      },

      // ---- Source Graph ----
      buildSourceGraph: async (body) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.buildSourceGraph(body);
          set((s: BrowserStore) => ({
            sourceGraphs: [resp.source_graph, ...s.sourceGraphs],
          }));
          set({ isLoading: false });
          return resp.source_graph;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to build source graph' });
          return null;
        }
      },

      listSourceGraphs: async (sessionId?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.listSourceGraphs(sessionId);
          set({ sourceGraphs: resp.source_graphs, isLoading: false });
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load source graphs' });
        }
      },

      // ---- Timeline ----
      loadTimeline: async (sessionId?, limit?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.getTimeline(sessionId, limit);
          set({ timeline: resp.timeline, isLoading: false });
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load timeline' });
        }
      },

      addTimelineEntry: async (body) => {
        try {
          const resp = await browserApi.addTimelineEntry(body);
          set((s: BrowserStore) => ({
            timeline: [resp.timeline_entry, ...s.timeline],
          }));
          return resp.timeline_entry;
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to add timeline entry' });
          return null;
        }
      },

      // ---- Model Routing ----
      getModelRoute: async (body) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.getModelRoute(body);
          set({ modelRoute: resp, isLoading: false });
          return resp;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to get model route' });
          return null;
        }
      },

      // ---- Remote Browser ----
      getRemoteBrowserStatus: async () => {
        try {
          const resp = await browserApi.getRemoteBrowserStatus();
          set({ remoteBrowserStatus: resp });
          return resp;
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to load remote browser status' });
          return null;
        }
      },

      createRemoteBrowserSession: async (body) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.createRemoteBrowserSession(body);
          set({ isLoading: false });
          return resp;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to create remote session' });
          return null;
        }
      },

      // ---- Auth State ----
      getAuthState: async () => {
        try {
          const resp = await browserApi.getAuthState();
          set({ authState: resp });
          return resp;
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to load auth state' });
          return null;
        }
      },

      // ---- High-Risk DOM ----
      checkHighRiskDom: async (content) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.checkHighRiskDom(content);
          set({ highRiskDomResult: resp, isLoading: false });
          if (resp.flagged) {
            usePlatformStore.getState().addActivity({
              domain: 'security', operation: 'high_risk_dom_detected',
              title: 'High-risk DOM detected',
              detail: resp.warnings.join('; '),
              severity: 'high',
            });
          }
          return resp;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to check high-risk DOM' });
          return null;
        }
      },

      // ---- Summon Browser ----
      summonBrowser: async (body) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.summonBrowser(body);
          set((s: BrowserStore) => ({
            sessions: [resp.session, ...s.sessions],
            activeSessionId: resp.session.id,
          }));
          set({ isLoading: false });
          return resp;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to summon browser' });
          return null;
        }
      },

      // ---- Artifacts ----
      loadArtifacts: async (sessionId?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.getArtifacts(sessionId);
          set({ artifacts: resp, isLoading: false });
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load artifacts' });
        }
      },

      // ---- Resource Usage ----
      loadResourceUsage: async () => {
        try {
          const resp = await browserApi.getResourceUsage();
          set({ resourceUsage: resp });
          return resp;
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to load resource usage' });
          return null;
        }
      },

      // ---- Evidence → Knowledge / Mission / Memory ----
      promoteEvidence: async (evidenceId, body?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.promoteEvidence(evidenceId, body);
          set({ isLoading: false });
          // Publish knowledge_promoted event to chat subscribers
          _publishToChat({
            type: 'knowledge_promoted',
            session_id: get().activeSessionId,
            data: { evidence_id: evidenceId, result: resp ?? null, source: 'browser' },
          });
          usePlatformStore.getState().addActivity({
            domain: 'mission', operation: 'knowledge_promoted',
            title: 'Evidence promoted to knowledge',
            detail: `Evidence ${evidenceId} added to knowledge base`, severity: 'info',
          });
          return resp;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to promote evidence' });
          return null;
        }
      },

      evidenceToMission: async (evidenceId, body?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.evidenceToMission(evidenceId, body);
          set({ isLoading: false });
          // Publish mission_created event to chat subscribers
          _publishToChat({
            type: 'mission_created',
            data: { evidence_id: evidenceId, mission: resp?.result?.mission ?? resp ?? null, source: 'browser_evidence' },
          });
          usePlatformStore.getState().addActivity({
            domain: 'mission', operation: 'mission_created',
            title: 'Mission created from browser evidence',
            detail: `Evidence ${evidenceId} promoted to mission`, severity: 'info',
          });
          return resp;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to send evidence to mission' });
          return null;
        }
      },

      getMissionContext: async (missionId) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.getMissionContext(missionId);
          set({ isLoading: false });
          return resp;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to load mission context' });
          return null;
        }
      },

      createMissionBrowserTask: async (missionId, body) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.createMissionBrowserTask(missionId, body);
          set((s: BrowserStore) => ({
            tasks: { ...s.tasks, [resp.task.id]: resp.task },
          }));
          set({ isLoading: false });
          return resp.task;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to create mission browser task' });
          return null;
        }
      },

      evidenceToMemory: async (evidenceId, body?) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.evidenceToMemory(evidenceId, body);
          set({ isLoading: false });
          return resp;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to store evidence to memory' });
          return null;
        }
      },

      // ---- Agent integration: dispatch a task to the agent system from browser context ----
      dispatchAgentTask: async (body) => {
        set({ isLoading: true, error: null });
        try {
          // Use the agents API via dynamic import to avoid circular dependency
          const { useAgentsStore } = await import('@/features/agents/store');
          const agentsStore = useAgentsStore.getState();
          // Build task description from browser context
          const summary = get().getBrowserContextSummary();
          const taskBody = {
            ...body,
            browser_context: summary,
            source: 'browser',
          };
          // Register and immediately run the agent task
          const task = await agentsStore.registerTask({
            name: (body.name as string) || 'Browser-triggered task',
            description: (body.description as string) || (body.goal as string) || '',
            schedule_type: (body.schedule_type as string) || 'once',
            schedule_value: (body.schedule_value as string) || '',
            priority: (body.priority as 'low' | 'normal' | 'high' | 'critical') || 'normal',
            timeout: (body.timeout as number) || 300,
            max_retries: (body.max_retries as number) || 3,
          });
          if (task?.id) {
            await agentsStore.runTask(task.id);
          }
          set({ isLoading: false });
          // Publish task_created event to chat
          _publishToChat({
            type: 'task_created',
            session_id: body.session_id as string | null ?? null,
            data: { task_id: task?.id, task_name: task?.name, source: 'browser', browser_context: summary },
          });
          usePlatformStore.getState().addActivity({
            domain: 'agent', operation: 'task_created',
            title: 'Agent task created from browser',
            detail: task?.name || 'Browser-triggered task', severity: 'info',
          });
          return { task, triggered: true } as Record<string, unknown>;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Failed to dispatch agent task' });
          return null;
        }
      },

      // ---- UI toggles ----
      setShowAIContext: (show) => set({ showAIContext: show }),
      setShowResearchControls: (show) => set({ showResearchControls: show }),
      setShowEvidencePanel: (show) => set({ showEvidencePanel: show }),
      setShowSecurityPanel: (show) => set({ showSecurityPanel: show }),
      setShowDownloadsPanel: (show) => set({ showDownloadsPanel: show }),
      setShowBookmarksPanel: (show) => set({ showBookmarksPanel: show }),
      setShowHistoryPanel: (show) => set({ showHistoryPanel: show }),
      setPrivacyMode: (mode) => set({ privacyMode: mode }),

      // ---- Browser ↔ Chat integration ----

      /** Build a BrowserContextSummary from current store state for chat. */
      getBrowserContextSummary: (): BrowserContextSummary | null => {
        const state = get();
        const activeTab = state.activeTabId ? state.tabs[state.activeTabId] : null;
        const activeSession = state.activeSessionId ? state.sessions.find((s: BrowserSession) => s.id === state.activeSessionId) : null;

        const recentEvidence = state.evidence.slice(0, 5).map((e: BrowserEvidence) => ({
          id: e.id,
          claim: e.claim ?? e.selected_passage,
          verification_status: e.verification_status,
          captured_at: e.captured_at,
          source_url: e.url,
        }));

        const securityNotes: string[] = [];
        if (state.aiContext?.prompt_injection.flagged) {
          securityNotes.push(`Prompt injection detected (confidence: ${state.aiContext.prompt_injection.confidence})`);
        }
        if (state.securityReport?.security_issues && state.securityReport.issue_count > 0) {
          securityNotes.push(...state.securityReport.security_issues.map((s: SecurityIssue) => `${s.type}: ${s.url}`));
        }

        const _extractDomain = (url: string): string => {
          try { return new URL(url).hostname; } catch { return ''; }
        };

        return {
          active_tab: activeTab
            ? { url: activeTab.url, title: activeTab.title, domain: _extractDomain(activeTab.url) }
            : null,
          active_session: activeSession
            ? { id: activeSession.id, privacy_mode: activeSession.privacy_mode }
            : null,
          recent_evidence: recentEvidence,
          security_notes: securityNotes,
          prompt_injection_flagged: state.aiContext?.prompt_injection.flagged ?? false,
          page_text_preview: state.aiContext?.text.slice(0, 200),
        };
      },

      /** Allow chat store to subscribe to browser events. */
      subscribeToChat: (callback) => {
        _chatSubscribers.add(callback);
        return () => {
          _chatSubscribers.delete(callback);
        };
      },

      // ---------------------------------------------------------------------------
      // Network Intelligence Layer methods (spec §51)
      // ---------------------------------------------------------------------------

      runNetworkDiagnostics: async (url, timeout = 15.0) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.runNetworkDiagnostics(url, timeout);
          set({ lastDiagnosticsResult: resp, isLoading: false });
          // Record the error event if it's a classified failure
          if (resp.error_category && resp.error_category !== 'UNKNOWN_NETWORK_ERROR') {
            usePlatformStore.getState().addActivity({
              domain: 'browser', operation: 'network_diagnostic',
              title: 'Network diagnostic completed',
              detail: resp.diagnosis?.substring(0, 120) || resp.error_category,
              severity: 'high',
            });
          }
          return resp;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Diagnostics failed' });
          return null;
        }
      },

      runDnsDiagnostics: async (url, alternateResolvers) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.runDnsDiagnostics(url, alternateResolvers);
          set({ isLoading: false });
          return resp;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'DNS diagnostics failed' });
          return null;
        }
      },

      runProxyDiagnostics: async (url) => {
        set({ isLoading: true, error: null });
        try {
          const resp = await browserApi.runProxyDiagnostics(url);
          set({ isLoading: false });
          return resp;
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : 'Proxy diagnostics failed' });
          return null;
        }
      },

      checkBrowserHealth: async () => {
        try {
          const resp = await browserApi.getBrowserHealth();
          set({ browserHealth: resp });
          return resp;
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Health check failed' });
          return null;
        }
      },

      recoverNavigation: async (url, strategy = 'auto', maxAttempts = 3) => {
        set({ isRecovering: true, recoveryError: null });
        try {
          const resp = await browserApi.recoverNavigation(url, strategy, maxAttempts);
          set({ isRecovering: false });
          usePlatformStore.getState().addActivity({
            domain: 'browser', operation: 'navigation_recovery',
            title: 'Recovery attempted',
            detail: resp.success ? 'Recovery succeeded' : `Recovery failed (${resp.attempts} attempts)`,
            severity: resp.success ? 'info' : 'high',
          });
          return resp;
        } catch (e) {
          set({ isRecovering: false, recoveryError: e instanceof Error ? e.message : 'Recovery failed' });
          return null;
        }
      },

      loadNetworkEvents: async () => {
        try {
          const resp = await browserApi.getNetworkEvents();
          set({ networkEvents: resp.events });
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to load network events' });
        }
      },

      loadNavigationTimeline: async (sessionId?) => {
        try {
          const resp = await browserApi.getNavigationTimeline(sessionId);
          set({ navigationTimeline: resp.timeline });
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to load navigation timeline' });
        }
      },

      loadBrowserHealth: async () => {
        try {
          const resp = await browserApi.getBrowserHealth();
          set({ browserHealth: resp });
        } catch (e) {
          set({ error: e instanceof Error ? e.message : 'Failed to load browser health' });
        }
      },

      // ---------------------------------------------------------------------------
      // Utilities
      // ---------------------------------------------------------------------------
      clearError: () => set({ error: null }),
      clearErrorHistory: () => set({ errorHistory: [], retryCount: 0, lastFailedRequest: null }),

      /** Check whether the browser backend is reachable. */
      checkBackendConnection: async () => {
        const t0 = Date.now();
        try {
          const resp = await browserApi.getStatus();
          const latency = Date.now() - t0;
          const status: NetworkStatus = {
            is_online: navigator.onLine,
            is_backend_reachable: true,
            last_checked: _now(),
            latency_ms: latency,
          };
          set({ networkStatus: status });
          return status;
        } catch {
          const status: NetworkStatus = {
            is_online: navigator.onLine,
            is_backend_reachable: false,
            last_checked: _now(),
          };
          set({ networkStatus: status, isOffline: !navigator.onLine });
          return status;
        }
      },

      /** Retry the last failed request, if one exists. */
      retryLastFailedRequest: async () => {
        const lastEndpoint = get().lastFailedRequest;
        if (!lastEndpoint) return;
        set({ isLoading: true, error: null });
        const handlers: Record<string, () => Promise<void>> = {
          status: get().loadStatus,
          sessions: get().loadSessions,
          auth_state: get().getAuthState,
          remote_browser: get().getRemoteBrowserStatus,
          resource_usage: get().loadResourceUsage,
        };
        const handler = handlers[lastEndpoint];
        if (!handler) {
          set({ isLoading: false });
          return;
        }
        try {
          await handler();
          set({ retryCount: 0, lastFailedRequest: null });
        } catch (e) {
          const err = _classifyError(e, lastEndpoint);
          set((s: BrowserStore) => ({
            errorHistory: [...s.errorHistory, err],
            retryCount: s.retryCount + 1,
          }));
        } finally {
          set({ isLoading: false });
        }
      },

      setOnline: (online: boolean) => {
        set({ isOffline: !online });
        if (online) {
          void get().checkBackendConnection();
        }
      },

      init: async () => {
        if (get().initialized) return;

        // Listen for browser online/offline events
        if (typeof window !== 'undefined') {
          window.addEventListener('online', () => get().setOnline(true));
          window.addEventListener('offline', () => get().setOnline(false));
          set({ isOffline: !navigator.onLine });
        }

        await get().loadStatus();
        await get().loadSessions();
        await get().getRemoteBrowserStatus();
        await get().getAuthState();
        await get().loadResourceUsage();
        await get().checkBackendConnection();
        // Load Network Intelligence Layer state
        await get().loadBrowserHealth();
        await get().loadNetworkEvents();
        _publishToChat({ type: 'browser_connected', data: {} });
        if (!_wsUnsubscribe) {
          _wsUnsubscribe = wsClient.subscribe(API_ENDPOINTS.ws.monitoring, (event: any) => {
            if (event.type === 'browser_navigation') {
              usePlatformStore.getState().addActivity({
                domain: 'browser', operation: 'navigate',
                title: 'Navigation (WS)', detail: String(event.data?.url ?? ''), severity: 'info',
              });
            } else if (event.type === 'browser_evidence') {
              const ev = event.data as BrowserEvidence;
              set((s: BrowserStore) => ({ evidence: [ev, ...s.evidence] }));
            }
          });
        }
        set({ initialized: true });
      },
    }),
    {
      name: 'jarvis-browser-store',
      storage: createJSONStorage(() => localStorage),
      partialize: (state: any) => {
        const privateSessionIds = new Set(
          state.sessions.filter((session: BrowserSession) => session.privacy_mode === 'private')
            .map((session: BrowserSession) => session.id),
        );
        const ephemeralTabIds = new Set(
          Object.values(state.tabs as Record<string, BrowserTab>)
            .filter((tab: BrowserTab) => tab.private_ephemeral_url)
            .map((tab: BrowserTab) => tab.id),
        );
        const persistedTabs = Object.fromEntries(
          Object.entries(state.tabs as Record<string, BrowserTab>).filter(([, tab]) =>
            !privateSessionIds.has(tab.session_id) && !ephemeralTabIds.has(tab.id)),
        );
        const persistedSessions = state.sessions
          .filter((session: BrowserSession) => !privateSessionIds.has(session.id))
          .map((session: BrowserSession) => ({
            ...session,
            tabs: session.tabs.filter((tabId) => !ephemeralTabIds.has(tabId)),
            active_tab_id: session.active_tab_id && ephemeralTabIds.has(session.active_tab_id)
              ? null
              : session.active_tab_id,
          }));
        return {
        sessions: persistedSessions,
        tabs: persistedTabs,
        activeSessionId: privateSessionIds.has(state.activeSessionId) ? null : state.activeSessionId,
        activeTabId: state.activeTabId && !persistedTabs[state.activeTabId] ? null : state.activeTabId,
        privacyMode: state.privacyMode,
        bookmarks: state.bookmarks,
        history: state.history,
        evidence: state.evidence,
        downloads: state.downloads,
        actions: state.actions,
        tasks: state.tasks,
        workspaces: state.workspaces,
        sourceGraphs: state.sourceGraphs,
        modelRoute: state.modelRoute,
        errorHistory: state.errorHistory,
        isOffline: state.isOffline,
        retryCount: state.retryCount,
      };
      },
    },
  ),
);

export default useBrowserStore;
