/**
 * Browser feature API client.
 *
 * All browser platform operations go through the shared apiClient which
 * handles authentication (401 → refresh → retry, then auth error redirect).
 * Endpoints are defined in config/api.ts under API_ENDPOINTS.browser.
 */

import apiClient from '@/lib/api-client';
import API_ENDPOINTS from '@/config/api';
import type {
  BrowserSession,
  BrowserTab,
  AIContext,
  SearchResponse,
  BrowserEvidence,
  EvidenceCaptureInput,
  BrowserBookmark,
  BrowserBookmarkInput,
  BrowserDownload,
  BrowserHistoryEntry,
  SecurityReport,
  InjectionCheck,
  PrivacyMode,
  BrowserAction,
  ActionQueue,
  PageState,
  BrowserTask,
  TaskStep,
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
  ActionExecutionResult,
  MissionBrowserContext,
  SummonResult,
  EvidencePromotionResult,
  EvidenceToMissionResult,
  EvidenceToMemoryResult,
  BrowserErrorCategory,
  NetworkDiagnosticResult,
  DnsDiagnosticsResult,
  ProxyDiagnosticsResult,
  BrowserHealthStatus,
  RecoveryResult,
  NetworkEventEntry,
  NavigationTimelineEntry,
} from './types';

export const browserApi = {
  // ---- Sessions ----
  async createSession(
    name?: string,
    privacyMode?: PrivacyMode,
    researchSessionId?: string,
    missionId?: string,
  ): Promise<{ session: BrowserSession }> {
    const body: Record<string, unknown> = {};
    if (name) body.name = name;
    if (privacyMode) body.privacy_mode = privacyMode;
    if (researchSessionId) body.research_session_id = researchSessionId;
    if (missionId) body.mission_id = missionId;
    return apiClient.post<{ session: BrowserSession }>(API_ENDPOINTS.browser.sessions, body);
  },

  async listSessions(): Promise<{ sessions: BrowserSession[]; count: number }> {
    return apiClient.get<{ sessions: BrowserSession[]; count: number }>(API_ENDPOINTS.browser.sessions);
  },

  async updateSession(
    sessionId: string,
    patch: Record<string, unknown>,
  ): Promise<{ session: BrowserSession }> {
    return apiClient.put<{ session: BrowserSession }>(
      `${API_ENDPOINTS.browser.sessions}/${sessionId}`,
      patch,
    );
  },

  async deleteSession(sessionId: string): Promise<{ success: boolean }> {
    return apiClient.delete<{ success: boolean }>(
      `${API_ENDPOINTS.browser.sessions}/${sessionId}`,
    );
  },

  // ---- Tabs ----
  async createTab(
    sessionId: string,
    url?: string,
    title?: string,
    isPinned?: boolean,
  ): Promise<{ tab: BrowserTab; session_id: string }> {
    const body: Record<string, unknown> = { session_id: sessionId };
    if (url) body.url = url;
    if (title) body.title = title;
    if (isPinned !== undefined) body.is_pinned = isPinned;
    return apiClient.post<{ tab: BrowserTab; session_id: string }>(API_ENDPOINTS.browser.tabs, body);
  },

  async listTabs(sessionId?: string): Promise<{ tabs: BrowserTab[]; count: number }> {
    const params = new URLSearchParams();
    if (sessionId) params.set('session_id', sessionId);
    const qs = params.toString();
    return apiClient.get<{ tabs: BrowserTab[]; count: number }>(
      `${API_ENDPOINTS.browser.tabs}${qs ? `?${qs}` : ''}`,
    );
  },

  async closeTab(tabId: string): Promise<{ success: boolean }> {
    return apiClient.delete<{ success: boolean }>(`${API_ENDPOINTS.browser.tabs}/${tabId}`);
  },

  // ---- Navigation ----
  async navigate(
    sessionId: string,
    url: string,
    tabId?: string,
    privacyMode?: PrivacyMode,
  ): Promise<{ window_id: string; url: string; navigated: boolean; blocked: boolean; reason?: string; privacy_mode?: string }> {
    const body: Record<string, unknown> = { session_id: sessionId, url };
    if (tabId) body.tab_id = tabId;
    if (privacyMode) body.privacy_mode = privacyMode;
    return apiClient.post(API_ENDPOINTS.browser.navigate, body);
  },

  async controlNavigation(
    sessionId: string,
    tabId: string,
    action: 'back' | 'forward' | 'reload',
  ): Promise<{ navigated: boolean; url: string; action: string; privacy_mode: PrivacyMode }> {
    return apiClient.post(API_ENDPOINTS.browser.navigationControl, {
      session_id: sessionId,
      tab_id: tabId,
      action,
    });
  },

  // ---- Page extraction / AI context ----
  async extractPage(
    url: string,
    content?: string,
    userSelection?: string,
  ): Promise<{
    url: string;
    title: string;
    text: string;
    text_length: number;
    metadata: Record<string, unknown>;
    structure: Record<string, unknown>;
    entities: Array<Record<string, unknown>>;
    prompt_injection: InjectionCheck;
    selection?: string | null;
  }> {
    const body: Record<string, unknown> = { url };
    if (content) body.content = content;
    if (userSelection) body.user_selection = userSelection;
    return apiClient.post(API_ENDPOINTS.browser.extract, body);
  },

  async getPage(url: string): Promise<{ html?: string; content_type?: string; status?: number; final_url?: string; is_html?: boolean }> {
    const params = new URLSearchParams({ url });
    return apiClient.get(API_ENDPOINTS.browser.page + `?${params.toString()}`);
  },

  // ---- Search ----
  async search(query: string, sessionId?: string): Promise<SearchResponse> {
    const body: Record<string, unknown> = { query };
    if (sessionId) body.session_id = sessionId;
    return apiClient.post<SearchResponse>(API_ENDPOINTS.browser.search, body);
  },

  // ---- Evidence ----
  async captureEvidence(input: EvidenceCaptureInput): Promise<{ id: string; evidence: BrowserEvidence }> {
    const body: Record<string, unknown> = {
      url: input.url,
      title: input.title ?? '',
      selected_passage: input.selected_passage,
      page_context: input.page_context ?? '',
      claim: input.claim ?? null,
      verification_status: input.verification_status ?? 'unchecked',
      research_session_id: input.research_session_id ?? null,
      mission_id: input.mission_id ?? null,
    };
    return apiClient.post<{ id: string; evidence: BrowserEvidence }>(
      API_ENDPOINTS.browser.evidence,
      body,
    );
  },

  async listEvidence(
    researchSessionId?: string,
    missionId?: string,
    verified?: boolean,
  ): Promise<{ evidence: BrowserEvidence[]; count: number }> {
    const params = new URLSearchParams();
    if (researchSessionId) params.set('research_session_id', researchSessionId);
    if (missionId) params.set('mission_id', missionId);
    if (verified !== undefined) params.set('verified', String(verified));
    const qs = params.toString();
    return apiClient.get<{ evidence: BrowserEvidence[]; count: number }>(
      `${API_ENDPOINTS.browser.evidence}${qs ? `?${qs}` : ''}`,
    );
  },

  // ---- Bookmarks ----
  async listBookmarks(q?: string, tags?: string): Promise<{ bookmarks: BrowserBookmark[]; count: number }> {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (tags) params.set('tags', tags);
    const qs = params.toString();
    return apiClient.get<{ bookmarks: BrowserBookmark[]; count: number }>(
      `${API_ENDPOINTS.browser.bookmarks}${qs ? `?${qs}` : ''}`,
    );
  },

  async addBookmark(input: BrowserBookmarkInput): Promise<{ id: string; bookmark: BrowserBookmark }> {
    return apiClient.post<{ id: string; bookmark: BrowserBookmark }>(
      API_ENDPOINTS.browser.bookmarks,
      { url: input.url, title: input.title, tags: input.tags ?? [], notes: input.notes ?? '' },
    );
  },

  async deleteBookmark(bookmarkId: string): Promise<{ success: boolean }> {
    return apiClient.delete<{ success: boolean }>(
      `${API_ENDPOINTS.browser.bookmarks}/${bookmarkId}`,
    );
  },

  // ---- History ----
  async getHistory(q?: string, domain?: string, limit = 100): Promise<{ history: BrowserHistoryEntry[]; count: number }> {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (domain) params.set('domain', domain);
    params.set('limit', String(limit));
    return apiClient.get<{ history: BrowserHistoryEntry[]; count: number }>(
      `${API_ENDPOINTS.browser.history}?${params.toString()}`,
    );
  },

  // ---- Downloads ----
  async getDownloads(): Promise<{ downloads: BrowserDownload[]; count: number }> {
    return apiClient.get<{ downloads: BrowserDownload[]; count: number }>(API_ENDPOINTS.browser.downloads);
  },

  // ---- Security ----
  async checkPromptInjection(content: string, source = 'page'): Promise<{
    source: string;
    flagged: boolean;
    confidence: number;
    matches: string[];
    recommendation: string;
  }> {
    return apiClient.post(API_ENDPOINTS.browser.security.promptInjection, { content, source });
  },

  async getSecurityReport(sessionId?: string): Promise<SecurityReport> {
    const params = new URLSearchParams();
    if (sessionId) params.set('session_id', sessionId);
    const qs = params.toString();
    return apiClient.get<SecurityReport>(
      `${API_ENDPOINTS.browser.security.report}${qs ? `?${qs}` : ''}`,
    );
  },

  // ---- Status ----
  async getStatus(): Promise<Record<string, unknown>> {
    return apiClient.get(API_ENDPOINTS.browser.status);
  },

  // ---- Autonomous browsing ----
  async autonomousBrowse(
    sessionId: string,
    action: string,
    params: Record<string, unknown>,
    consent: boolean,
    url?: string,
  ): Promise<Record<string, unknown>> {
    return apiClient.post(API_ENDPOINTS.browser.autonomous, {
      session_id: sessionId,
      action,
      params,
      consent,
      url: url ?? null,
    });
  },

  // =========================================================================
  // Browser Action Model (spec §3)
  // =========================================================================

  async createAction(body: Record<string, unknown>): Promise<{ action: BrowserAction }> {
    return apiClient.post<{ action: BrowserAction }>(API_ENDPOINTS.browser.actions, body);
  },

  async listActions(sessionId?: string, status?: string): Promise<{ actions: BrowserAction[]; count: number }> {
    const params = new URLSearchParams();
    if (sessionId) params.set('session_id', sessionId);
    if (status) params.set('status', status);
    const qs = params.toString();
    return apiClient.get<{ actions: BrowserAction[]; count: number }>(
      `${API_ENDPOINTS.browser.actions}${qs ? `?${qs}` : ''}`,
    );
  },

  async executeAction(actionId: string): Promise<Record<string, unknown>> {
    return apiClient.post<Record<string, unknown>>(`${API_ENDPOINTS.browser.actions}/${actionId}/execute`);
  },

  // =========================================================================
  // Observe → Act Loop (spec §4)
  // =========================================================================

  async observeActLoop(body: Record<string, unknown>): Promise<Record<string, unknown>> {
    return apiClient.post<Record<string, unknown>>(API_ENDPOINTS.browser.observeAct, body);
  },

  // =========================================================================
  // Page State (spec §6)
  // =========================================================================

  async getPageState(body: Record<string, unknown>): Promise<{ page_state: PageState; page_state_id: string }> {
    return apiClient.post<{ page_state: PageState; page_state_id: string }>(API_ENDPOINTS.browser.pageState, body);
  },

  // =========================================================================
  // Task Execution Engine (spec §10, §13–14)
  // =========================================================================

  async createTask(body: Record<string, unknown>): Promise<{ task: BrowserTask }> {
    return apiClient.post<{ task: BrowserTask }>(API_ENDPOINTS.browser.tasks, body);
  },

  async listTasks(sessionId?: string, status?: string): Promise<{ tasks: BrowserTask[]; count: number }> {
    const params = new URLSearchParams();
    if (sessionId) params.set('session_id', sessionId);
    if (status) params.set('status', status);
    const qs = params.toString();
    return apiClient.get<{ tasks: BrowserTask[]; count: number }>(
      `${API_ENDPOINTS.browser.tasks}${qs ? `?${qs}` : ''}`,
    );
  },

  async executeTaskStep(taskId: string, stepId: string): Promise<{ step: TaskStep; result: Record<string, unknown>; checkpoint_id: string }> {
    return apiClient.post<{ step: TaskStep; result: Record<string, unknown>; checkpoint_id: string }>(
      `${API_ENDPOINTS.browser.tasks}/${taskId}/step/${stepId}/execute`,
    );
  },

  async createTaskCheckpoint(taskId: string): Promise<{ checkpoint: TaskCheckpoint }> {
    return apiClient.post<{ checkpoint: TaskCheckpoint }>(`${API_ENDPOINTS.browser.tasks}/${taskId}/checkpoint`);
  },

  async resumeTask(taskId: string): Promise<{ task: BrowserTask; resumed: boolean; checkpoint_id: string; step_index: number }> {
    return apiClient.post<{ task: BrowserTask; resumed: boolean; checkpoint_id: string; step_index: number }>(
      `${API_ENDPOINTS.browser.tasks}/${taskId}/resume`,
    );
  },

  async pauseTask(taskId: string): Promise<{ task: BrowserTask; paused: boolean }> {
    return apiClient.post<{ task: BrowserTask; paused: boolean }>(`${API_ENDPOINTS.browser.tasks}/${taskId}/pause`);
  },

  async cancelTask(taskId: string): Promise<{ task: BrowserTask; cancelled: boolean }> {
    return apiClient.post<{ task: BrowserTask; cancelled: boolean }>(`${API_ENDPOINTS.browser.tasks}/${taskId}/cancel`);
  },

  // =========================================================================
  // Browser Workspaces (spec §17)
  // =========================================================================

  async createWorkspace(body: Record<string, unknown>): Promise<{ workspace: BrowserWorkspace }> {
    return apiClient.post<{ workspace: BrowserWorkspace }>(API_ENDPOINTS.browser.workspaces, body);
  },

  async listWorkspaces(): Promise<{ workspaces: BrowserWorkspace[]; count: number }> {
    return apiClient.get<{ workspaces: BrowserWorkspace[]; count: number }>(API_ENDPOINTS.browser.workspaces);
  },

  async updateWorkspace(workspaceId: string, patch: Record<string, unknown>): Promise<{ workspace: BrowserWorkspace }> {
    return apiClient.put<{ workspace: BrowserWorkspace }>(`${API_ENDPOINTS.browser.workspaces}/${workspaceId}`, patch);
  },

  async associateWorkspace(workspaceId: string, body: Record<string, unknown>): Promise<{ workspace: BrowserWorkspace }> {
    return apiClient.post<{ workspace: BrowserWorkspace }>(`${API_ENDPOINTS.browser.workspaces}/${workspaceId}/associate`, body);
  },

  // =========================================================================
  // Browser Telemetry (spec §42)
  // =========================================================================

  async recordTelemetry(body: Record<string, unknown>): Promise<{ telemetry: BrowserTelemetryEntry }> {
    return apiClient.post<{ telemetry: BrowserTelemetryEntry }>(API_ENDPOINTS.browser.telemetry, body);
  },

  async getTelemetry(sessionId?: string, limit?: number): Promise<{ telemetry: BrowserTelemetryEntry[]; count: number }> {
    const params = new URLSearchParams();
    if (sessionId) params.set('session_id', sessionId);
    if (limit) params.set('limit', String(limit));
    const qs = params.toString();
    return apiClient.get<{ telemetry: BrowserTelemetryEntry[]; count: number }>(
      `${API_ENDPOINTS.browser.telemetry}${qs ? `?${qs}` : ''}`,
    );
  },

  // =========================================================================
  // Source Graph (spec §36)
  // =========================================================================

  async buildSourceGraph(body: Record<string, unknown>): Promise<{ source_graph: SourceGraph }> {
    return apiClient.post<{ source_graph: SourceGraph }>(API_ENDPOINTS.browser.sourceGraph, body);
  },

  async listSourceGraphs(sessionId?: string): Promise<{ source_graphs: SourceGraph[]; count: number }> {
    const params = new URLSearchParams();
    if (sessionId) params.set('session_id', sessionId);
    const qs = params.toString();
    return apiClient.get<{ source_graphs: SourceGraph[]; count: number }>(
      `${API_ENDPOINTS.browser.sourceGraph}${qs ? `?${qs}` : ''}`,
    );
  },

  // =========================================================================
  // Browser Timeline (spec §37)
  // =========================================================================

  async addTimelineEntry(body: Record<string, unknown>): Promise<{ timeline_entry: TimelineEntry }> {
    return apiClient.post<{ timeline_entry: TimelineEntry }>(API_ENDPOINTS.browser.timeline, body);
  },

  async getTimeline(sessionId?: string, limit?: number): Promise<{ timeline: TimelineEntry[]; count: number }> {
    const params = new URLSearchParams();
    if (sessionId) params.set('session_id', sessionId);
    if (limit) params.set('limit', String(limit));
    const qs = params.toString();
    return apiClient.get<{ timeline: TimelineEntry[]; count: number }>(
      `${API_ENDPOINTS.browser.timeline}${qs ? `?${qs}` : ''}`,
    );
  },

  // =========================================================================
  // Action Replay (spec §38–39)
  // =========================================================================

  async replayActions(sessionId: string): Promise<{ session_id: string; actions: BrowserAction[]; count: number; replay_warning: string }> {
    return apiClient.get<{ session_id: string; actions: BrowserAction[]; count: number; replay_warning: string }>(
      `${API_ENDPOINTS.browser.actions}/replay/${sessionId}`,
    );
  },

  // =========================================================================
  // Model Routing (spec §9, §44)
  // =========================================================================

  async getModelRoute(body: Record<string, unknown>): Promise<ModelRoute> {
    return apiClient.post<ModelRoute>(API_ENDPOINTS.browser.modelRoute, body);
  },

  // =========================================================================
  // Evidence → Knowledge / Mission / Memory (spec §27–31)
  // =========================================================================

  async promoteEvidence(
    evidenceId: string,
    body?: Record<string, unknown>,
  ): Promise<EvidencePromotionResult> {
    return apiClient.post<EvidencePromotionResult>(
      `${API_ENDPOINTS.browser.evidencePromote(evidenceId)}`,
      body ?? {},
    );
  },

  async evidenceToMission(
    evidenceId: string,
    body?: Record<string, unknown>,
  ): Promise<EvidenceToMissionResult> {
    return apiClient.post<EvidenceToMissionResult>(
      `${API_ENDPOINTS.browser.evidenceToMission(evidenceId)}`,
      body ?? {},
    );
  },

  async evidenceToMemory(
    evidenceId: string,
    body?: Record<string, unknown>,
  ): Promise<EvidenceToMemoryResult> {
    return apiClient.post<EvidenceToMemoryResult>(
      `${API_ENDPOINTS.browser.evidenceToMemory(evidenceId)}`,
      body ?? {},
    );
  },

  // =========================================================================
  // Mission Browser Context (spec §29–30)
  // =========================================================================

  async getMissionContext(missionId: string): Promise<MissionBrowserContext> {
    return apiClient.get<MissionBrowserContext>(API_ENDPOINTS.browser.missions.context(missionId));
  },

  async createMissionBrowserTask(
    missionId: string,
    body: Record<string, unknown>,
  ): Promise<{ task: BrowserTask }> {
    return apiClient.post<{ task: BrowserTask }>(
      API_ENDPOINTS.browser.missions.browserTask(missionId),
      body,
    );
  },

  // =========================================================================
  // Remote Browser (spec §40)
  // =========================================================================

  async getRemoteBrowserStatus(): Promise<RemoteBrowserStatus> {
    return apiClient.get<RemoteBrowserStatus>(API_ENDPOINTS.browser.remoteBrowser.status);
  },

  async createRemoteBrowserSession(
    body: Record<string, unknown>,
  ): Promise<RemoteBrowserSession> {
    return apiClient.post<RemoteBrowserSession>(
      API_ENDPOINTS.browser.remoteBrowser.sessions,
      body,
    );
  },

  // =========================================================================
  // Auth State (spec §19)
  // =========================================================================

  async getAuthState(): Promise<AuthState> {
    return apiClient.get<AuthState>(API_ENDPOINTS.browser.authState);
  },

  // =========================================================================
  // High-Risk DOM Detection (spec §23)
  // =========================================================================

  async checkHighRiskDom(content: string): Promise<HighRiskDomResult> {
    return apiClient.post<HighRiskDomResult>(API_ENDPOINTS.browser.security.highRiskDom, { content });
  },

  // =========================================================================
  // Summon Browser (spec §49)
  // =========================================================================

  async summonBrowser(body: Record<string, unknown>): Promise<SummonResult> {
    return apiClient.post<SummonResult>(API_ENDPOINTS.browser.summon, body);
  },

  // =========================================================================
  // Artifacts (spec §50)
  // =========================================================================

  async getArtifacts(sessionId?: string): Promise<ArtifactCollection> {
    const params = new URLSearchParams();
    if (sessionId) params.set('session_id', sessionId);
    const qs = params.toString();
    return apiClient.get<ArtifactCollection>(
      `${API_ENDPOINTS.browser.artifacts}${qs ? `?${qs}` : ''}`,
    );
  },

  // =========================================================================
  // Resource Usage (spec §41)
  // =========================================================================

  async getResourceUsage(): Promise<ResourceUsage> {
    return apiClient.get<ResourceUsage>(API_ENDPOINTS.browser.resourceUsage);
  },

  // =========================================================================
  // Task Plan (spec §11)
  // =========================================================================

  async getTaskPlan(taskId: string): Promise<TaskPlan> {
    return apiClient.get<TaskPlan>(API_ENDPOINTS.browser.taskPlan(taskId));
  },

  // ---- Network Intelligence Layer (spec §51) ----
  async getBrowserHealth(): Promise<BrowserHealthStatus> {
    return apiClient.get<BrowserHealthStatus>(API_ENDPOINTS.browser.browserHealth);
  },
  async runDnsDiagnostics(
    url: string,
    alternateResolvers?: string[],
  ): Promise<DnsDiagnosticsResult> {
    return apiClient.post<DnsDiagnosticsResult>(API_ENDPOINTS.browser.diagnosticsDns, {
      url,
      alternate_resolvers: alternateResolvers,
    });
  },
  async runProxyDiagnostics(url: string): Promise<ProxyDiagnosticsResult> {
    return apiClient.post<ProxyDiagnosticsResult>(API_ENDPOINTS.browser.diagnosticsProxy, {
      url,
    });
  },
  async runNetworkDiagnostics(
    url: string,
    timeout: number = 15.0,
  ): Promise<NetworkDiagnosticResult> {
    return apiClient.post<NetworkDiagnosticResult>(API_ENDPOINTS.browser.diagnosticsNetwork, {
      url,
      timeout,
    });
  },
  async recoverNavigation(
    url: string,
    strategy: string = 'auto',
    maxAttempts: number = 3,
  ): Promise<RecoveryResult> {
    return apiClient.post<RecoveryResult>(API_ENDPOINTS.browser.recover, {
      url,
      strategy,
      max_attempts: maxAttempts,
    });
  },
  async getNetworkEvents(limit: number = 100): Promise<{ events: NetworkEventEntry[]; count: number }> {
    return apiClient.get<{ events: NetworkEventEntry[]; count: number }>(
      `${API_ENDPOINTS.browser.networkEvents}?limit=${limit}`,
    );
  },
  async getNavigationTimeline(
    sessionId?: string,
    limit: number = 100,
  ): Promise<{ timeline: NavigationTimelineEntry[]; count: number }> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (sessionId) params.set('session_id', sessionId);
    return apiClient.get<{ timeline: NavigationTimelineEntry[]; count: number }>(
      `${API_ENDPOINTS.browser.navigationTimeline}?${params.toString()}`,
    );
  },
};

export default browserApi;
