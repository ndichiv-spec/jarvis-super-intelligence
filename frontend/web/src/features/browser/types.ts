/**
 * Browser feature types — AI-native browser workspace.
 *
 * These types model the persistent browser context: sessions, tabs,
 * page metadata, AI context, evidence, security state, and workspaces.
 */

// ---------------------------------------------------------------------------
// Privacy modes
// ---------------------------------------------------------------------------

export type PrivacyMode = 'standard' | 'private' | 'research' | 'agent' | 'automation' | 'authenticated';

// ---------------------------------------------------------------------------
// Core entities
// ---------------------------------------------------------------------------

export interface BrowserTab {
  id: string;
  session_id: string;
  url: string;
  title: string;
  favicon: string;
  is_loading: boolean;
  is_pinned: boolean;
  group: string;
  created_at: string;
  updated_at: string;
  scroll_position?: number | null;
  extracted_content?: string | null;
  prompt_injection_flagged?: boolean;
  security_notes?: string[];
  navigation_revision?: number;
  private_ephemeral_url?: boolean;
}

export interface BrowserSession {
  id: string;
  name: string;
  privacy_mode: PrivacyMode;
  tabs: string[];             // tab IDs
  active_tab_id?: string | null;
  created_at: string;
  updated_at: string;
  research_session_id?: string | null;
  mission_id?: string | null;
}

// ---------------------------------------------------------------------------
// AI Context — what JARVIS knows about the current page
// ---------------------------------------------------------------------------

export interface PageMetadata {
  url: string;
  title: string;
  favicon: string;
  description: string;
  image: string;
  word_count: number;
}

export interface PageEntity {
  type: 'url' | 'email' | 'money' | 'date' | 'person' | 'organization' | 'location';
  value: string;
}

export interface PageStructure {
  headings: Array<{ level: number; text: string }>;
  paragraphs: number;
  links: number;
  images: number;
  tables: number;
  lists: number;
  forms: number;
  code_blocks: number;
  word_count: number;
}

export interface InjectionCheck {
  flagged: boolean;
  confidence: number;
  matches: string[];
}

export interface AIContext {
  metadata: PageMetadata;
  text: string;
  text_length: number;
  structure: PageStructure;
  entities: PageEntity[];
  prompt_injection: InjectionCheck;
  selected_content?: string | null;
}

// ---------------------------------------------------------------------------
// Evidence
// ---------------------------------------------------------------------------

export type VerificationStatus = 'unchecked' | 'verified' | 'refuted' | 'uncertain' | 'disputed';

export interface BrowserEvidence {
  id: string;
  url: string;
  domain: string;
  title: string;
  selected_passage: string;
  page_context: string;
  claim?: string | null;
  verification_status: VerificationStatus;
  research_session_id?: string | null;
  mission_id?: string | null;
  captured_at: string;
  epoch: number;
  tags: string[];
}

export interface EvidenceCaptureInput {
  url: string;
  title?: string;
  selected_passage: string;
  page_context?: string;
  claim?: string | null;
  verification_status?: VerificationStatus;
  research_session_id?: string | null;
  mission_id?: string | null;
}

// ---------------------------------------------------------------------------
// Bookmarks & Downloads
// ---------------------------------------------------------------------------

export interface BrowserBookmark {
  id: string;
  url: string;
  title: string;
  tags: string[];
  notes: string;
  domain: string;
  created_at: string;
  updated_at: string;
}

export interface BrowserBookmarkInput {
  url: string;
  title: string;
  tags?: string[];
  notes?: string;
}

export interface BrowserDownload {
  id: string;
  url: string;
  filename: string;
  size_bytes: number;
  risk_level: 'unknown' | 'low' | 'medium' | 'high' | 'critical';
  status: 'pending' | 'downloading' | 'completed' | 'failed' | 'quarantined';
  created_at: string;
  path?: string;
  quarantined?: boolean;
  scan_status?: string;
}

export interface BrowserHistoryEntry {
  id: string;
  url: string;
  title: string;
  domain: string;
  visited_at: string;
  epoch: number;
  user_id: string;
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

export interface SearchResult {
  title: string;
  url: string;
  snippet: string;
  source: 'web' | 'knowledge' | 'memory';
  domain: string;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  external_results: SearchResult[];
  internal_results: SearchResult[];
  session_id: string | null;
}

// ---------------------------------------------------------------------------
// Security
// ---------------------------------------------------------------------------

export interface SecurityIssue {
  tab_id: string;
  url: string;
  type: 'prompt_injection' | 'blocked_domain';
  severity: 'high' | 'critical';
  notes: string[];
}

export interface SecurityReport {
  session: BrowserSession | null;
  tabs: BrowserTab[];
  privacy_mode: PrivacyMode;
  credential_isolation: boolean;
  security_issues: SecurityIssue[];
  issue_count: number;
}

// ---------------------------------------------------------------------------
// Browser Action Model (spec §3)
// ---------------------------------------------------------------------------

export type ActionType = 'navigate' | 'search' | 'open_tab' | 'close_tab' | 'click' | 'type' | 'select' | 'scroll' | 'extract' | 'download' | 'compare' | 'capture_evidence' | 'submit_form' | 'bookmark' | 'switch_tab' | 'go_back' | 'go_forward' | 'reload';

export type ActionPermission = 'allowed' | 'requires_confirmation' | 'denied';
export type ActionStatus = 'queued' | 'running' | 'completed' | 'failed' | 'blocked' | 'verified';

export interface BrowserAction {
  id: string;
  type: ActionType;
  target?: string;
  parameters: Record<string, unknown>;
  source: 'user' | 'agent';
  permission: ActionPermission;
  status: ActionStatus;
  session_id: string;
  tab_id?: string;
  created_at: string;
  executed_at?: string;
  verified_at?: string;
  result?: Record<string, unknown>;
  error?: string;
  evidence_id?: string;
  checkpoint_id?: string;
}

export interface ActionQueue {
  session_id: string;
  actions: BrowserAction[];
  current_action_index: number;
  created_at: string;
  updated_at: string;
  completed: boolean;
  checkpoint_id?: string;
}

// ---------------------------------------------------------------------------
// Page State Representation (spec §6)
// ---------------------------------------------------------------------------

export interface InteractiveElement {
  id: string;
  type: 'button' | 'link' | 'textbox' | 'checkbox' | 'dropdown' | 'table' | 'form' | 'navigation';
  label: string;
  selector: string;
  attributes: Record<string, string>;
  visible: boolean;
  enabled: boolean;
  position?: { x: number; y: number };
}

export interface PageState {
  url: string;
  title: string;
  domain: string;
  page_classification: string;
  metadata: Record<string, unknown>;
  headings: Array<{ level: number; text: string }>;
  main_content: string;
  interactive_elements: InteractiveElement[];
  forms: Array<{ id: string; input_count: number; action?: string }>;
  links: Array<{ url: string; text: string }>;
  tables: Array<{ id: string; rows: number; cells: number }>;
  selected_content: string;
  visible_warnings: string[];
  security_indicators: string[];
  prompt_injection_flagged: boolean;
  word_count: number;
  extracted_at: string;
}

// ---------------------------------------------------------------------------
// Task Execution Engine (spec §10, §13–14)
// ---------------------------------------------------------------------------

export interface TaskStep {
  id: string;
  description: string;
  action_type: ActionType;
  parameters: Record<string, unknown>;
  status: ActionStatus;
  result?: Record<string, unknown>;
  error?: string;
  verified: boolean;
  evidence_ids: string[];
}

export interface BrowserTask {
  id: string;
  session_id: string;
  mission_id?: string | null;
  research_session_id?: string | null;
  goal: string;
  plan: string[];
  steps: TaskStep[];
  current_step_index: number;
  status: ActionStatus;
  created_at: string;
  updated_at: string;
  checkpoint_id?: string;
  completed_at?: string;
  error?: string;
  evidence_ids: string[];
  agent_id?: string;
  pause_on_risk: boolean;
}

export interface TaskCheckpoint {
  id: string;
  task_id: string;
  session_id: string;
  step_index: number;
  page_state?: Record<string, unknown>;
  evidence_ids: string[];
  created_at: string;
  metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Browser Workspace (spec §17)
// ---------------------------------------------------------------------------

export interface BrowserWorkspace {
  id: string;
  name: string;
  description: string;
  session_ids: string[];
  tabs: string[];
  permissions: Record<string, unknown>;
  notes: string;
  evidence_ids: string[];
  mission_ids: string[];
  created_at: string;
  updated_at: string;
  privacy_mode: string;
}

// ---------------------------------------------------------------------------
// Browser Telemetry (spec §42)
// ---------------------------------------------------------------------------

export interface BrowserTelemetryEntry {
  id: string;
  timestamp: string;
  session_id: string;
  action: string;
  navigation_latency_ms?: number | null;
  extraction_latency_ms?: number | null;
  ai_latency_ms?: number | null;
  provider?: string | null;
  model?: string | null;
  tokens?: number | null;
  cost?: number | null;
  downloads: number;
  errors: number;
  security_blocks: number;
  automation_actions: number;
}

// ---------------------------------------------------------------------------
// Source Graph (spec §36)
// ---------------------------------------------------------------------------

export interface SourceGraph {
  id: string;
  session_id: string;
  claim: string;
  sources: Array<Record<string, unknown>>;
  evidence: Array<Record<string, unknown>>;
  connections: Array<{ source_a: string; source_b: string; type: string; agreement: boolean | null }>;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Timeline (spec §37) — distinct from telemetry entries
// ---------------------------------------------------------------------------

export interface TimelineEntry {
  id: string;
  timestamp: string;
  epoch: number;
  session_id: string;
  action: string;
  detail: string;
  url: string;
  user_id: string;
}

// ---------------------------------------------------------------------------
// Model Routing (spec §9, §44)
// ---------------------------------------------------------------------------

export interface ModelRoute {
  task_type: string;
  capability: string;
  model_type: string;
  privacy_mode: string;
  routing_policy: {
    provider: string;
    model: string;
    reason?: string;
    cost?: number;
    cost_estimate?: string;
    fallback?: string;
    latency_target?: string;
    [key: string]: unknown;
  };
}

// ---------------------------------------------------------------------------
// Remote Browser (spec §40)
// ---------------------------------------------------------------------------

export interface RemoteBrowserStatus {
  remote_browser_enabled: boolean;
  remote_browser_url: string;
  api_key_configured: boolean;
  local_browsing_available: boolean;
  routing_policy: {
    mode: 'local' | 'remote';
    reason: string;
  };
}

export interface RemoteBrowserSession {
  session_id: string;
  remote: boolean;
  status: string;
  worker_url: string;
}

// ---------------------------------------------------------------------------
// Browser Identity Indicator (spec §19)
// ---------------------------------------------------------------------------

export interface AuthProviderInfo {
  provider: string;
  account: string;
  connected_at: string;
  connected_by: string;
}

export interface AuthState {
  authenticated_providers: AuthProviderInfo[];
  active_authenticated_session: BrowserSession | null;
  note: string;
}

// ---------------------------------------------------------------------------
// High-Risk DOM Detection (spec §23)
// ---------------------------------------------------------------------------

export interface HighRiskDomMatch {
  type: string;
  snippet: string;
}

export interface HighRiskDomResult {
  flagged: boolean;
  matches: HighRiskDomMatch[];
  warnings: string[];
  confidence: number;
}

// ---------------------------------------------------------------------------
// Artifacts (spec §50)
// ---------------------------------------------------------------------------

export interface ArtifactCollection {
  sessions: BrowserSession[];
  tabs: BrowserTab[];
  evidence: BrowserEvidence[];
  bookmarks: BrowserBookmark[];
  history: BrowserHistoryEntry[];
  downloads: BrowserDownload[];
  tasks: BrowserTask[];
  workspaces: BrowserWorkspace[];
  timeline: TimelineEntry[];
  counts: {
    sessions: number;
    tabs: number;
    evidence: number;
    bookmarks: number;
    history: number;
    downloads: number;
    tasks: number;
    workspaces: number;
    timeline: number;
  };
}

// ---------------------------------------------------------------------------
// Local Resource Protection (spec §41)
// ---------------------------------------------------------------------------

export interface ResourceUsageDetail {
  id: string;
  goal: string;
  step: number;
}

export interface ResourceUsage {
  cpu_time_seconds: number;
  memory_mb: number;
  running_tasks: number;
  running_task_details: ResourceUsageDetail[];
  recommendation: string;
  remote_browser_available: boolean;
}

// ---------------------------------------------------------------------------
// Observe → Act Loop (spec §4)
// ---------------------------------------------------------------------------

export interface ObserveActResult {
  page_state: Record<string, unknown>;
  observation: string;
  proposed_action: Record<string, unknown>;
  policy_check: { passed: boolean; reasons: string[] };
  execution_result: Record<string, unknown>;
  verification: {
    verified: boolean;
    page_state_changed: boolean;
    policy_reasons: string[];
  };
}

// ---------------------------------------------------------------------------
// Execution Plan View (spec §11)
// ---------------------------------------------------------------------------

export interface TaskPlan {
  task_id: string;
  goal: string;
  plan: string[];
  current_step: TaskStep | null;
  completed_steps: TaskStep[];
  completed_count: number;
  total_steps: number;
  next_action: string;
  blocked_actions: TaskStep[];
  verification: boolean;
  checkpoint_id?: string | null;
  status: string;
}

// ---------------------------------------------------------------------------
// Action Execution Results
// ---------------------------------------------------------------------------

export interface ActionExecutionResult {
  executed: boolean;
  action_id: string;
  type: string;
  requires_confirmation?: boolean;
  message?: string;
  blocked?: boolean;
  reason?: string;
  tab_id?: string;
  url?: string;
  search_results?: unknown[];
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Evidence → Knowledge / Mission / Memory (spec §27–31)
// ---------------------------------------------------------------------------

export interface EvidencePromotionResult {
  knowledge_id: string;
  knowledge: Record<string, unknown>;
  learning_id?: string;
}

export interface EvidenceToMissionResult {
  result: Record<string, unknown>;
  evidence_id: string;
}

export interface EvidenceToMemoryResult {
  memory_id: string;
  memory: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Mission Browser Context (spec §29–30)
// ---------------------------------------------------------------------------

export interface MissionBrowserContext {
  mission_id: string;
  sessions: BrowserSession[];
  tabs: BrowserTab[];
  evidence: BrowserEvidence[];
  tasks: BrowserTask[];
  evidence_count: number;
  tab_count: number;
}

// ---------------------------------------------------------------------------
// Summon Browser (spec §49)
// ---------------------------------------------------------------------------

export interface SummonResult {
  session: BrowserSession;
  context_followed: boolean;
  summon_url: string;
}

// ---------------------------------------------------------------------------
// Error / Offline State
// ---------------------------------------------------------------------------

export type BrowserErrorType = 'network' | 'auth' | 'permission' | 'validation' | 'server' | 'unknown';

export interface BrowserError {
  type: BrowserErrorType;
  message: string;
  status_code?: number;
  endpoint?: string;
  timestamp: string;
  retry_count: number;
  can_retry: boolean;
}

export interface NetworkStatus {
  is_online: boolean;
  is_backend_reachable: boolean;
  last_checked: string | null;
  latency_ms?: number;
}

// ---------------------------------------------------------------------------
// Browser Network Intelligence Layer — Diagnostic types (spec §51)
// ---------------------------------------------------------------------------

/** Stable error taxonomy for navigation failures. */
export type BrowserErrorCategory =
  | 'DNS_RESOLUTION_FAILED'
  | 'DNS_TIMEOUT'
  | 'DNS_SERVER_UNAVAILABLE'
  | 'PROXY_RESOLUTION_FAILED'
  | 'PROXY_CONNECTION_FAILED'
  | 'CONNECTION_REFUSED'
  | 'CONNECTION_TIMEOUT'
  | 'TLS_HANDSHAKE_FAILED'
  | 'CERTIFICATE_INVALID'
  | 'HTTP_4XX'
  | 'HTTP_5XX'
  | 'REDIRECT_LOOP'
  | 'CONTENT_BLOCKED'
  | 'AUTH_REQUIRED'
  | 'BROWSER_ENGINE_ERROR'
  | 'SERVICE_WORKER_ERROR'
  | 'BROWSER_CRASH'
  | 'REMOTE_BROWSER_UNAVAILABLE'
  | 'UNKNOWN_NETWORK_ERROR';

export interface BrowserErrorRecord {
  category: BrowserErrorCategory;
  message: string;
  category_message?: string;
  status_code?: number;
  timestamp: string;
  endpoint?: string;
}

export interface DnsRecord {
  rtype: string;
  value: string;
  ttl: number;
}

export interface DnsDiagnosticResult {
  resolver: string;
  hostname: string;
  available: boolean;
  latency_ms: number | null;
  records: DnsRecord[];
  cache_state: string;
  error: string | null;
}

export interface DnsDiagnosticsResult {
  hostname: string;
  system_resolver: DnsDiagnosticResult | null;
  alternate_resolvers: DnsDiagnosticResult[];
  all_available: boolean;
  records: DnsRecord[];
  summary: string;
  timestamp: string;
}

export interface ProxyDiagnosticResult {
  url: string;
  scheme: string;
  proxy_applies: boolean;
  proxy_bypass: boolean;
  proxy_url: string | null;
  proxy_reachable: boolean | null;
  proxy_latency_ms: number | null;
  proxy_error: string | null;
}

export interface ProxyConfigInfo {
  proxies: Record<string, string>;
  has_proxy: boolean;
  proxy_count: number;
  sources: string[];
}

export interface ProxyDiagnosticsResult {
  url: string;
  proxy_config: ProxyConfigInfo;
  proxy_check: ProxyDiagnosticResult;
}

export interface TcpDiagnosticResult {
  host: string;
  port: number;
  reached: boolean;
  latency_ms: number | null;
  error: string | null;
}

export interface TlsDiagnosticResult {
  host: string;
  port: number;
  tls_version: string | null;
  cipher: string | null;
  cert_valid: boolean | null;
  cert_subject: Record<string, string> | null;
  cert_issuer: Record<string, string> | null;
  cert_not_after: string | null;
  reachable: boolean;
  latency_ms: number | null;
  error: string | null;
}

export interface HttpDiagnosticResult {
  url: string;
  reached: boolean;
  status_code: number | null;
  content_type: string | null;
  content_length: number;
  latency_ms: number | null;
  redirect_count: number;
  final_url: string;
  error_category: string | null;
  error: string | null;
}

export interface RecoveryPlan {
  action: string;
  max_attempts: number;
  description: string;
  safe: boolean;
}

export interface RecoveryResult {
  success: boolean;
  strategy: string;
  attempts: number;
  max_attempts: number;
  final_error: string | null;
  recovered_category: string | null;
  details: string[];
}

export interface NavigationErrorContext {
  url: string;
  error_message: string;
  error_category: BrowserErrorCategory | null;
}

export interface NetworkDiagnosticResult {
  url: string;
  hostname: string;
  error_category: BrowserErrorCategory;
  dns: DnsDiagnosticsResult | null;
  proxy: ProxyDiagnosticsResult | null;
  tcp: TcpDiagnosticResult | null;
  tls: TlsDiagnosticResult | null;
  http: HttpDiagnosticResult | null;
  diagnosis: string;
  recovery_plan: RecoveryPlan | null;
  recommendations: string[];
  timestamp: string;
}

export interface NetworkEventEntry {
  id: string;
  timestamp: string;
  epoch: number;
  type: string;
  url: string;
  category: string;
  severity: string;
  detail: string;
  extra: Record<string, unknown>;
}

export interface NavigationTimelineEntry {
  id: string;
  timestamp: string;
  epoch: number;
  session_id: string;
  tab_id: string | null;
  url: string;
  action: string;
  detail: string;
  category: string | null;
  extra: Record<string, unknown>;
}

export interface BrowserHealthCheck {
  name: string;
  passed: boolean;
  detail: string;
  latency_ms: number | null;
}

export interface BrowserHealthStatus {
  overall: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
  checks: BrowserHealthCheck[];
  timestamp: string;
}

/** Summary of the active browser state sent to chat so the LLM backend
 *  can reason about the DOM, recent evidence, and security status. */
export interface BrowserContextSummary {
  active_tab?: {
    url: string;
    title: string;
    domain: string;
  } | null;
  active_session?: {
    id: string;
    privacy_mode: string;
  } | null;
  recent_evidence?: Array<{
    id: string;
    claim: string;
    verification_status: string;
    captured_at: string;
    source_url: string;
  }>;
  security_notes?: string[];
  prompt_injection_flagged?: boolean;
  page_text_preview?: string;
}

// ---------------------------------------------------------------------------
// Browser State (state managed by the store)
// ---------------------------------------------------------------------------

export interface BrowserState {
  // Sessions & tabs
  sessions: BrowserSession[];
  tabs: Record<string, BrowserTab>;
  activeSessionId: string | null;
  activeTabId: string | null;

  // UI state
  isLoading: boolean;
  error: string | null;
  privacyMode: PrivacyMode;
  showAIContext: boolean;
  showResearchControls: boolean;
  showEvidencePanel: boolean;
  showSecurityPanel: boolean;
  showDownloadsPanel: boolean;
  showBookmarksPanel: boolean;
  showHistoryPanel: boolean;

  // AI context for the active tab
  aiContext: AIContext | null;

  // Data
  bookmarks: BrowserBookmark[];
  history: BrowserHistoryEntry[];
  downloads: BrowserDownload[];
  evidence: BrowserEvidence[];

  // Search
  searchResults: SearchResult[];
  searchQuery: string;
  isSearching: boolean;

  // Security
  securityReport: SecurityReport | null;

  // Status
  status: Record<string, unknown>;

  // Actions
  actions: Record<string, BrowserAction>;
  actionQueues: Record<string, ActionQueue>;

  // Tasks
  tasks: Record<string, BrowserTask>;
  taskCheckpoints: Record<string, TaskCheckpoint>;

  // Workspaces
  workspaces: Record<string, BrowserWorkspace>;

  // Telemetry & Timeline
  telemetry: BrowserTelemetryEntry[];
  timeline: TimelineEntry[];

  // Source Graphs
  sourceGraphs: SourceGraph[];

  // Page states (structured page state cache, spec §6)
  pageStates: Record<string, PageState>;

  // Model routing
  modelRoute: ModelRoute | null;

  // Remote browser
  remoteBrowserStatus: RemoteBrowserStatus | null;

  // Auth state (identity indicator, spec §19)
  authState: AuthState | null;

  // High-risk DOM results
  highRiskDomResult: HighRiskDomResult | null;

  // Artifacts
  artifacts: ArtifactCollection | null;

  // Resource usage
  resourceUsage: ResourceUsage | null;

  // Observe-Act result
  observeActResult: ObserveActResult | null;

  // Current task plan
  currentTaskPlan: TaskPlan | null;

  // Error & offline state (upgraded error handling)
  isOffline: boolean;
  networkStatus: NetworkStatus;
  errorHistory: BrowserError[];
  retryCount: number;
  lastFailedRequest: string | null;

  // Network Intelligence Layer state (spec §51)
  networkEvents: NetworkEventEntry[];
  navigationTimeline: NavigationTimelineEntry[];
  browserHealth: BrowserHealthStatus | null;
  lastDiagnosticsResult: NetworkDiagnosticResult | null;
  isRecovering: boolean;
  recoveryError: string | null;

  // Initialization
  initialized: boolean;
}

export interface BrowserStore extends BrowserState {
  // Sessions
  createSession: (name?: string, privacyMode?: PrivacyMode, researchSessionId?: string, missionId?: string) => Promise<BrowserSession | null>;
  loadSessions: () => Promise<void>;
  setActiveSession: (sessionId: string | null) => void;
  updateSession: (sessionId: string, patch: Partial<BrowserSession>) => Promise<BrowserSession | null>;
  deleteSession: (sessionId: string) => Promise<void>;

  // Tabs
  createTab: (sessionId: string, url?: string, title?: string, isPinned?: boolean) => Promise<BrowserTab | null>;
  loadTabs: (sessionId?: string) => Promise<void>;
  setActiveTab: (tabId: string | null) => void;
  closeTab: (tabId: string) => Promise<void>;

  // Navigation
  navigate: (sessionId: string, url: string, tabId?: string, privacyMode?: PrivacyMode) => Promise<{ navigated: boolean; blocked: boolean; url?: string; reason?: string; privacy_mode?: string } | null>;
  goBack: () => Promise<boolean>;
  goForward: () => Promise<boolean>;
  reload: () => Promise<boolean>;

  // Page extraction / AI context
  extractPage: (url: string, content?: string, userSelection?: string) => Promise<AIContext | null>;
  clearAIContext: () => void;

  // Search
  search: (query: string, sessionId?: string) => Promise<SearchResult[]>;

  // Evidence
  captureEvidence: (input: EvidenceCaptureInput) => Promise<BrowserEvidence | null>;
  loadEvidence: (researchSessionId?: string, missionId?: string) => Promise<void>;

  // Bookmarks
  loadBookmarks: (q?: string, tags?: string) => Promise<void>;
  addBookmark: (input: BrowserBookmarkInput) => Promise<BrowserBookmark | null>;
  deleteBookmark: (id: string) => Promise<void>;

  // History
  loadHistory: (q?: string) => Promise<void>;

  // Downloads
  loadDownloads: () => Promise<void>;

  // Security
  checkPromptInjection: (content: string) => Promise<InjectionCheck>;
  loadSecurityReport: (sessionId?: string) => Promise<void>;

  // Status
  loadStatus: () => Promise<void>;

  // Actions
  createAction: (body: Record<string, unknown>) => Promise<BrowserAction | null>;
  listActions: (sessionId?: string, status?: string) => Promise<void>;
  executeAction: (actionId: string) => Promise<ActionExecutionResult | null>;
  replayActions: (sessionId: string) => Promise<BrowserAction[] | null>;

  // Observe → Act Loop
  runObserveActLoop: (body: Record<string, unknown>) => Promise<ObserveActResult | null>;

  // Page State
  loadPageState: (body: Record<string, unknown>) => Promise<{ page_state: PageState; page_state_id: string } | null>;

  // Tasks
  createTask: (body: Record<string, unknown>) => Promise<BrowserTask | null>;
  listTasks: (sessionId?: string, status?: string) => Promise<void>;
  executeTaskStep: (taskId: string, stepId: string) => Promise<{ step: TaskStep; result: Record<string, unknown>; checkpoint_id: string } | null>;
  createTaskCheckpoint: (taskId: string) => Promise<TaskCheckpoint | null>;
  resumeTask: (taskId: string) => Promise<{ task: BrowserTask; resumed: boolean; checkpoint_id: string; step_index: number } | null>;
  pauseTask: (taskId: string) => Promise<{ task: BrowserTask; paused: boolean } | null>;
  cancelTask: (taskId: string) => Promise<{ task: BrowserTask; cancelled: boolean } | null>;
  getTaskPlan: (taskId: string) => Promise<TaskPlan | null>;

  // Workspaces
  createWorkspace: (body: Record<string, unknown>) => Promise<BrowserWorkspace | null>;
  listWorkspaces: () => Promise<void>;
  updateWorkspace: (workspaceId: string, patch: Record<string, unknown>) => Promise<BrowserWorkspace | null>;
  associateWorkspace: (workspaceId: string, body: Record<string, unknown>) => Promise<BrowserWorkspace | null>;

  // Telemetry
  loadTelemetry: (sessionId?: string, limit?: number) => Promise<void>;
  recordTelemetry: (body: Record<string, unknown>) => Promise<BrowserTelemetryEntry | null>;

  // Source Graph
  buildSourceGraph: (body: Record<string, unknown>) => Promise<SourceGraph | null>;
  listSourceGraphs: (sessionId?: string) => Promise<void>;

  // Timeline
  loadTimeline: (sessionId?: string, limit?: number) => Promise<void>;
  addTimelineEntry: (body: Record<string, unknown>) => Promise<TimelineEntry | null>;

  // Model Routing
  getModelRoute: (body: Record<string, unknown>) => Promise<ModelRoute | null>;

  // Remote Browser
  getRemoteBrowserStatus: () => Promise<RemoteBrowserStatus | null>;
  createRemoteBrowserSession: (body: Record<string, unknown>) => Promise<RemoteBrowserSession | null>;

  // Auth State
  getAuthState: () => Promise<AuthState | null>;

  // High-Risk DOM
  checkHighRiskDom: (content: string) => Promise<HighRiskDomResult | null>;

  // Summon Browser
  summonBrowser: (body: Record<string, unknown>) => Promise<SummonResult | null>;

  // Artifacts
  loadArtifacts: (sessionId?: string) => Promise<void>;

  // Resource Usage
  loadResourceUsage: () => Promise<ResourceUsage | null>;

  // Evidence → Knowledge / Mission / Memory
  promoteEvidence: (evidenceId: string, body?: Record<string, unknown>) => Promise<EvidencePromotionResult | null>;
  evidenceToMission: (evidenceId: string, body?: Record<string, unknown>) => Promise<EvidenceToMissionResult | null>;
  getMissionContext: (missionId: string) => Promise<MissionBrowserContext | null>;
  createMissionBrowserTask: (missionId: string, body: Record<string, unknown>) => Promise<BrowserTask | null>;
  evidenceToMemory: (evidenceId: string, body?: Record<string, unknown>) => Promise<EvidenceToMemoryResult | null>;

  // Agent integration — dispatch tasks to the agent system from browser context
  dispatchAgentTask: (body: Record<string, unknown>) => Promise<Record<string, unknown> | null>;

  // UI toggles
  setShowAIContext: (show: boolean) => void;
  setShowResearchControls: (show: boolean) => void;
  setShowEvidencePanel: (show: boolean) => void;
  setShowSecurityPanel: (show: boolean) => void;
  setShowDownloadsPanel: (show: boolean) => void;
  setShowBookmarksPanel: (show: boolean) => void;
  setShowHistoryPanel: (show: boolean) => void;
  setPrivacyMode: (mode: PrivacyMode) => void;

  // Utilities
  clearError: () => void;
  clearErrorHistory: () => void;
  checkBackendConnection: () => Promise<NetworkStatus>;
  retryLastFailedRequest: () => Promise<void>;
  setOnline: (online: boolean) => void;
  getBrowserContextSummary: () => BrowserContextSummary | null;
  subscribeToChat: (callback: (event: { type: string; timestamp: string; session_id?: string | null; tab_id?: string | null; data: Record<string, unknown> }) => void) => () => void;

  // Network Intelligence Layer methods (spec §51)
  runNetworkDiagnostics: (url: string, timeout?: number) => Promise<NetworkDiagnosticResult | null>;
  runDnsDiagnostics: (url: string, alternateResolvers?: string[]) => Promise<DnsDiagnosticsResult | null>;
  runProxyDiagnostics: (url: string) => Promise<ProxyDiagnosticsResult | null>;
  checkBrowserHealth: () => Promise<BrowserHealthStatus | null>;
  recoverNavigation: (url: string, strategy?: string, maxAttempts?: number) => Promise<RecoveryResult | null>;
  loadNetworkEvents: () => Promise<void>;
  loadNavigationTimeline: (sessionId?: string) => Promise<void>;
  loadBrowserHealth: () => Promise<void>;
  init: () => Promise<void>;
}
