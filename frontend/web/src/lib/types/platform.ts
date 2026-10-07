/**
 * Unified platform state types — single source of truth for the shell.
 *
 * These types define the vocabulary shared across the entire JARVIS shell.
 * Every section (Chat, Security, Observatory, etc.) reads from and writes
 * to the same state model rather than maintaining isolated copies.
 */

/** The operational lifecycle state of a domain resource or async operation. */
export type ResourceStatus =
  | 'idle'
  | 'loading'
  | 'streaming'
  | 'working'
  | 'completed'
  | 'failed'
  | 'offline'
  | 'degraded'
  | 'unauthorized'
  | 'rate_limited'
  | 'queued'
  | 'paused'
  | 'cancelled';

/** Severity levels used across events, alerts, and notifications. */
export type SeverityLevel = 'info' | 'low' | 'medium' | 'high' | 'critical';

/** Where a heavy workload is executing. */
export type ComputeLocation = 'LOCAL' | 'REMOTE' | 'CLOUD' | 'PROVIDER_API' | 'KAGGLE' | 'GPU_WORKER';

/** A single activity event from anywhere in the platform. */
export interface ActivityEvent {
  id: string;
  timestamp: number;
  domain: 'agent' | 'tool' | 'model' | 'provider' | 'security' | 'training' | 'learning' | 'mission' | 'research' | 'system' | 'chat' | 'browser';
  operation: string;
  title: string;
  detail?: string;
  severity: SeverityLevel;
  user?: string;
  resourceId?: string;
  resourceType?: string;
  metadata?: Record<string, unknown>;
}

/** Provider status summary returned by the control/status endpoint. */
export interface ProviderStatus {
  provider: string;
  display_name: string;
  connected: boolean;
  status: string;
  capabilities: string[];
  model_count: number;
  detail?: string;
  last_tested?: string;
  expires_at?: string;
  configured: boolean;
}

/** Credential reference returned by the control/credentials endpoint. */
export interface CredentialRef {
  provider: string;
  display_name: string;
  key: string;
  label?: string;
  status: 'set' | 'unset';
  source: 'env' | 'vault' | 'override';
  identity_provider: boolean;
}

/** Live system resource usage from the monitoring endpoints. */
export interface SystemResourceUsage {
  cpu_percent: number;
  memory_percent: number;
  memory_available_mb: number;
  disk_percent: number;
  processes: number;
  timestamp: number;
}

/** Connection / compute state surfaced in the shell header. */
export interface BackendConnection {
  connected: boolean;
  status: ResourceStatus;
  latencyMs?: number;
  error?: string | null;
  lastChecked: Date | null;
}

/** Unified notification used by the notification center. */
export interface NotificationItem {
  id: string;
  title: string;
  detail: string;
  severity: SeverityLevel;
  read: boolean;
  timestamp: number;
  domain: ActivityEvent['domain'];
  action?: { label: string; onClick: () => void };
}

/** Workspace-level persisted UI state. */
export interface WorkspaceState {
  activeMission?: string;
  activeResearchSession?: string;
  selectedAgent?: string;
  panelState: Record<string, { collapsed?: boolean; width?: number; height?: number; open?: boolean }>;
}

/** Context saved when leaving a page so it can be restored on return.
 *  Each entry captures the working state that would otherwise be lost
 *  when navigating away. */
export interface NavigationContext {
  path: string;
  context: Record<string, unknown>;
  timestamp: number;
}

/** In-memory navigation context history (not persisted — only useful for the
 *  current session's back/forward navigation). */
export interface NavigationHistoryState {
  history: NavigationContext[];
}

/**
 * The single shell-level state consumed by the dashboard layout.
 *
 * This replaces the ad-hoc, duplicated state that previously lived in
 * `stores/monitoring-store.ts`, `stores/system-store.ts`, the header, and
 * the sidebar in isolated, non-synchronised copies.
 */
export interface PlatformState {
  /** Auth / user identity */
  user: {
    id: string | null;
    email: string | null;
    full_name: string | null;
    roles: string[];
    isAuthenticated: boolean;
  };

  /** Backend connectivity (JARVIS Brain, Silverwing, providers) */
  backend: BackendConnection;
  silverwing: { connected: boolean; status: string; model: string | null };

  /** Provider fleet */
  providers: ProviderStatus[];
  providerSummary: { total: number; connected: number; disconnected: number };

  /** Real system resource usage (from public monitoring endpoints) */
  system: SystemResourceUsage | null;

  /** Unified activity stream (capped to last N events) */
  activity: ActivityEvent[];

  /** Notifications surfaced from activity events */
  notifications: NotificationItem[];

  /** Workspace-persisted selection state */
  workspace: WorkspaceState;

  /** Navigation context history for context-preserving navigation */
  navigationHistory: NavigationContext[];

  /** Overall error / banner message */
  error: string | null;
}

export type PlatformAction =
  | { type: 'HYDRATE'; state: Partial<PlatformState> }
  | { type: 'SET_BACKEND'; connection: Partial<BackendConnection> }
  | { type: 'SET_SILVERWING'; status: { connected: boolean; model: string | null; status: string } }
  | { type: 'SET_PROVIDERS'; providers: ProviderStatus[]; summary: { total: number; connected: number; disconnected: number } }
  | { type: 'SET_SYSTEM'; usage: SystemResourceUsage }
  | { type: 'ADD_ACTIVITY'; event: ActivityEvent }
  | { type: 'ADD_NOTIFICATION'; notification: Omit<NotificationItem, 'id' | 'timestamp' | 'read'> }
  | { type: 'MARK_NOTIFICATION_READ'; id: string }
  | { type: 'CLEAR_NOTIFICATIONS' }
  | { type: 'SET_WORKSPACE'; patch: Partial<WorkspaceState> }
  | { type: 'SAVE_NAVIGATION_CONTEXT'; context: NavigationContext }
  | { type: 'CLEAR_NAVIGATION_CONTEXT'; path: string }
  | { type: 'SET_ERROR'; error: string | null }
  | { type: 'SET_USER'; user: { id: string | null; email: string | null; full_name: string | null; roles: string[]; isAuthenticated: boolean } };
