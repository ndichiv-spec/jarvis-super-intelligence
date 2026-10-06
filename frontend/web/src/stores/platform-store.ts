/**
 * Unified platform store — single source of truth for the JARVIS shell.
 *
 * This store consolidates what was previously scattered across:
 *   - stores/monitoring-store.ts     (metrics, health, status)
 *   - stores/system-store.ts         (system status)
 *   - lib/api.ts setConnectionStatus (connection tracking)
 *   - features/chat/store.ts         (connected flag)
 *   - header.tsx                      (notifications as local component state)
 *   - sidebar.tsx                     (hardcoded system metrics)
 *
 * The shell (dashboard layout, header, sidebar) subscribes to this store
 * for real-time updates. Feature areas can also publish activity events
 * and notifications here so the entire platform shares one coherent
 * view of "what is JARVIS doing right now."
 */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import { getAuthToken } from '@/lib/api-client';
import wsClient from '@/lib/websocket-client';
import env from '@/config/env';
import API_ENDPOINTS from '@/config/api';
import type {
  PlatformState,
  ProviderStatus,
  CredentialRef,
  SystemResourceUsage,
  ActivityEvent,
  NotificationItem,
  WorkspaceState,
  NavigationContext,
  BackendConnection,
  ResourceStatus,
} from '@/lib/types/platform';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let _activityId = 0;
function nextActivityId(): string {
  _activityId += 1;
  return `act-${Date.now()}-${_activityId}`;
}

let _notificationId = 0;
function nextNotificationId(): string {
  _notificationId += 1;
  return `notif-${Date.now()}-${_notificationId}`;
}

/** Map a raw monitoring metrics / health-report response to our normalised shape. */
function normaliseSystemUsage(raw: any): SystemResourceUsage {
  const sys = raw?.system ?? raw ?? {};
  return {
    cpu_percent: typeof raw?.cpu_percent === 'number' ? raw.cpu_percent
      : typeof sys?.cpu_percent === 'number' ? sys.cpu_percent : 0,
    memory_percent: typeof raw?.memory?.percent === 'number' ? raw.memory.percent
      : typeof sys?.memory_percent === 'number' ? sys.memory_percent : 0,
    memory_available_mb: typeof raw?.memory?.available === 'number' ? raw.memory.available / 1048576
      : typeof sys?.memory_available_mb === 'number' ? sys.memory_available_mb : 0,
    disk_percent: typeof raw?.disk === 'number' ? raw.disk
      : typeof sys?.disk_percent === 'number' ? sys.disk_percent : 0,
    processes: typeof raw?.processes === 'number' ? raw.processes
      : typeof sys?.processes === 'number' ? sys.processes
      : typeof sys?.process_count === 'number' ? sys.process_count : 0,
    timestamp: Date.now(),
  };
}

/** Build provider status list from the control/status endpoint. */
function normaliseProviders(raw: any): { providers: ProviderStatus[]; summary: { total: number; connected: number; disconnected: number } } {
  const providers: ProviderStatus[] = Array.isArray(raw?.providers) ? raw.providers : [];
  const summary = raw?.provider_summary ?? { total: providers.length, connected: 0, disconnected: providers.length };
  const connected = summary.connected ?? providers.filter((p: any) => p.connected === true).length;
  const total = summary.total ?? providers.length;
  return {
    providers,
    summary: {
      total,
      connected,
      disconnected: (summary.disconnected ?? total - connected),
    },
  };
}

/** Workspace persistence helpers (manual, so only workspace state is persisted). */
const WORKSPACE_KEY = 'jarvis-workspace';
function loadWorkspace(): WorkspaceState {
  if (typeof window === 'undefined') return defaultWorkspace();
  try {
    const raw = localStorage.getItem(WORKSPACE_KEY);
    if (raw) return { ...defaultWorkspace(), ...JSON.parse(raw) };
  } catch { /* ignore */ }
  return defaultWorkspace();
}

function defaultWorkspace(): WorkspaceState {
  return {
    selectedModel: 'auto',
    selectedProvider: 'jarvis-brain',
    panelState: {},
  };
}

function saveWorkspace(ws: WorkspaceState) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(WORKSPACE_KEY, JSON.stringify(ws));
  } catch { /* ignore */ }
}

// ---------------------------------------------------------------------------
// Store interface
// ---------------------------------------------------------------------------

export interface PlatformStore extends PlatformState {
  // --- Mutations ---
  setBackend: (c: Partial<BackendConnection>) => void;
  setSilverwing: (s: { connected: boolean; model: string | null; status: string }) => void;
  setProviders: (providers: ProviderStatus[], summary: { total: number; connected: number; disconnected: number }) => void;
  setSystem: (usage: SystemResourceUsage) => void;
  addActivity: (event: Omit<ActivityEvent, 'id' | 'timestamp'>) => void;
  addNotification: (n: Omit<NotificationItem, 'id' | 'timestamp' | 'read'>) => void;
  markNotificationRead: (id: string) => void;
  markAllNotificationsRead: () => void;
  clearNotifications: () => void;
  setWorkspace: (patch: Partial<WorkspaceState>) => void;
  setError: (error: string | null) => void;
  setUser: (user: { id: string | null; email: string | null; full_name: string | null; roles: string[]; isAuthenticated: boolean }) => void;

  // --- Navigation context (context-preserving navigation) ---
  saveNavigationContext: (path: string, context: Record<string, unknown>) => void;
  getNavigationContext: (path: string) => Record<string, unknown> | null;
  clearNavigationContext: (path: string) => void;

  // --- Data loading ---
  refreshBackend: () => Promise<void>;
  refreshProviders: () => Promise<void>;
  refreshSystem: () => Promise<void>;
  refreshSilverwing: () => Promise<void>;
  refreshAll: () => Promise<void>;

  // --- Real-time subscription ---
  subscribeToEvents: () => () => void;
  clearError: () => void;
}

// ---------------------------------------------------------------------------
// Store factory
// ---------------------------------------------------------------------------

function getInitialState(): PlatformState {
  return {
    user: { id: null, email: null, full_name: null, roles: [], isAuthenticated: false },
    backend: { connected: false, status: 'idle', lastChecked: null },
    silverwing: { connected: false, status: 'unknown', model: null },
    providers: [],
    providerSummary: { total: 0, connected: 0, disconnected: 0 },
    system: null,
    activity: [],
    notifications: [],
    workspace: loadWorkspace(),
    navigationHistory: [],
    error: null,
  };
}

export const usePlatformStore = create<PlatformStore>()(
  devtools(
    (set, get) => ({
      ...getInitialState(),

      // --- Mutations ---
      setBackend: (c) =>
        set((s) => ({
          backend: { ...s.backend, ...c },
        })),

      setSilverwing: (s) =>
        set({ silverwing: { connected: s.connected, model: s.model, status: s.status } }),

      setProviders: (providers, summary) => set({ providers, providerSummary: summary }),

      setSystem: (usage) => set({ system: usage }),

      addActivity: (event) =>
        set((s) => ({
          activity: [{ ...event, id: nextActivityId(), timestamp: Date.now() }, ...s.activity].slice(0, 200),
        })),

      addNotification: (n) =>
        set((s) => ({
          notifications: [
            {
              id: nextNotificationId(),
              timestamp: Date.now(),
              read: false,
              ...n,
            },
            ...s.notifications,
          ],
        })),

      markNotificationRead: (id) =>
        set((s) => ({
          notifications: s.notifications.map((n) => (n.id === id ? { ...n, read: true } : n)),
        })),

      markAllNotificationsRead: () =>
        set((s) => ({
          notifications: s.notifications.map((n) => ({ ...n, read: true })),
        })),

      clearNotifications: () => set({ notifications: [] }),

      setWorkspace: (patch) =>
        set((s) => {
          const workspace = { ...s.workspace, ...patch };
          saveWorkspace(workspace);
          return { workspace };
        }),

      setError: (error) => set({ error }),

      setUser: (user) => set({ user }),

      // --- Navigation context ---
      saveNavigationContext: (path, context) =>
        set((s) => {
          const history = s.navigationHistory.filter((h) => h.path !== path);
          history.push({ path, context, timestamp: Date.now() });
          return { navigationHistory: history.slice(-50) };
        }),

      getNavigationContext: (path: string): Record<string, unknown> | null => {
        const found = get().navigationHistory
          .filter((h) => h.path === path)
          .sort((a, b) => b.timestamp - a.timestamp);
        return found.length ? found[0].context : null;
      },

      clearNavigationContext: (path) =>
        set((s) => ({
          navigationHistory: s.navigationHistory.filter((h) => h.path !== path),
        })),

      clearError: () => set({ error: null }),

      // --- Data loading ---
      refreshBackend: async () => {
        const start = Date.now();
        try {
          const res = await fetch(`${env.API_URL}/api/v1/monitoring/metrics`, {
            headers: { Authorization: `Bearer ${getAuthToken() || ''}` },
          });
          const latency = Date.now() - start;
          if (res.ok) {
            get().setBackend({ connected: true, status: 'completed', latencyMs: latency, error: null, lastChecked: new Date() });
            const data = await res.json();
            if (typeof data.cpu_percent === 'number' || data.system) {
              get().setSystem(normaliseSystemUsage(data));
            }
          } else if (res.status >= 500) {
            get().setBackend({ connected: false, status: 'offline', error: `Backend error: ${res.status}`, lastChecked: new Date() });
          } else {
            get().setBackend({ connected: false, status: 'degraded', error: `HTTP ${res.status}`, lastChecked: new Date() });
          }
        } catch (error) {
          get().setBackend({
            connected: false,
            status: 'offline',
            error: error instanceof Error ? error.message : 'Connection failed',
            lastChecked: new Date(),
          });
        }
      },

      refreshSystem: async () => {
        try {
          const [metricsRes, healthRes] = await Promise.allSettled([
            fetch(API_ENDPOINTS.monitoring.metrics),
            fetch(API_ENDPOINTS.monitoring.healthReport),
          ]);
          let usage: SystemResourceUsage | null = null;
          if (metricsRes.status === 'fulfilled' && (metricsRes.value as Response).ok) {
            usage = normaliseSystemUsage(await (metricsRes.value as Response).json());
          }
          if (!usage && healthRes.status === 'fulfilled' && (healthRes.value as Response).ok) {
            usage = normaliseSystemUsage(await (healthRes.value as Response).json());
          }
          if (usage) get().setSystem(usage);
        } catch {
          // Silent — system metrics are best-effort
        }
      },

      refreshProviders: async () => {
        const token = getAuthToken();
        if (!token) return;
        try {
          const res = await fetch(`${env.API_URL}/api/v1/control/status`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (res.ok) {
            const data = await res.json();
            const { providers, summary } = normaliseProviders(data);
            get().setProviders(providers, summary);
          }
        } catch {
          // Not admin — providers remain empty, dashboard degrades gracefully
        }
      },

      refreshSilverwing: async () => {
        try {
          const res = await fetch(`${env.API_URL}/silverwing/api/laboratory/model`);
          if (res.ok) {
            const data = await res.json();
            get().setSilverwing({ connected: true, model: data.id || data.name || null, status: data.status || 'unknown' });
          } else {
            get().setSilverwing({ connected: false, model: null, status: 'offline' });
          }
        } catch {
          get().setSilverwing({ connected: false, model: null, status: 'unknown' });
        }
      },

      refreshAll: async () => {
        await Promise.all([
          get().refreshBackend(),
          get().refreshSystem(),
          get().refreshProviders(),
          get().refreshSilverwing(),
        ]);
      },

      // --- Real-time subscription ---
      subscribeToEvents: () => {
        const wsUrl = env.WS_URL;
        if (!wsUrl) {
          // No WS URL configured — skip real-time, polling is handled by callers
          return () => {};
        }

        const unsubscribe = wsClient.subscribe(`${wsUrl}/ws/monitoring`, (rawEvent: any) => {
          const event: any = rawEvent;
          const data = event.data as any;
          if (event?.type === 'monitoring_update' && data?.metrics) {
            get().setSystem(normaliseSystemUsage(data.metrics));
          }
          if (event?.type === 'health_update' && data) {
            get().setSystem(normaliseSystemUsage(data));
          }
          // 'activity' and 'notification' are custom types the backend may emit
          if (event?.type === 'activity') {
            get().addActivity(data);
          }
          if (event?.type === 'notification') {
            get().addNotification({
              title: data?.title || 'JARVIS',
              detail: data?.detail || '',
              severity: data?.severity || 'info',
              domain: data?.domain || 'system',
            });
          }
          if (event?.type === 'status_update') {
            get().setBackend({ connected: data?.connected ?? true, status: data?.status as ResourceStatus, lastChecked: new Date() });
          }
        });

        return unsubscribe;
      },
    }),
  )
);

// ---------------------------------------------------------------------------
// Convenience selectors
// ---------------------------------------------------------------------------

export const useBackend = () => usePlatformStore((s) => s.backend);
export const useSystemUsage = () => usePlatformStore((s) => s.system);
export const useProviders = () => usePlatformStore((s) => ({ providers: s.providers, summary: s.providerSummary }));
export const useActivity = () => usePlatformStore((s) => s.activity);
export const useNotifications = () => usePlatformStore((s) => s.notifications);
export const useWorkspace = () => usePlatformStore((s) => s.workspace);
export const useSilverwing = () => usePlatformStore((s) => s.silverwing);
export const useUser = () => usePlatformStore((s) => s.user);
export const useNavigationContext = (path: string) => usePlatformStore((s) => s.navigationHistory.filter((h) => h.path === path).sort((a, b) => b.timestamp - a.timestamp)[0]?.context ?? null);

export default usePlatformStore;
