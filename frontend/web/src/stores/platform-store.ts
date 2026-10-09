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
import wsClient from '@/lib/websocket-client';
import type { WsEvent } from '@/lib/websocket-client';
import env from '@/config/env';
import API_ENDPOINTS from '@/config/api';
import type {
  PlatformState,
  ProviderStatus,
  SystemResourceUsage,
  ActivityEvent,
  NotificationItem,
  WorkspaceState,
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function finiteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/** Map a raw monitoring metrics / health-report response to our normalised shape. */
function normaliseSystemUsage(value: unknown): SystemResourceUsage | null {
  const raw = isRecord(value) ? value : {};
  const sys = isRecord(raw.system) ? raw.system : raw;
  const memoryRaw = isRecord(raw.memory) ? raw.memory : {};
  const cpu = finiteNumber(raw.cpu_percent) ? raw.cpu_percent : sys.cpu_percent;
  const memory = finiteNumber(memoryRaw.percent) ? memoryRaw.percent : sys.memory_percent;
  const available = finiteNumber(memoryRaw.available)
    ? memoryRaw.available / 1048576
    : sys.memory_available_mb;
  const disk = finiteNumber(raw.disk) ? raw.disk : sys.disk_percent;
  const processes = finiteNumber(raw.processes)
    ? raw.processes
    : finiteNumber(sys.processes)
      ? sys.processes
      : sys.process_count;

  if (
    !finiteNumber(cpu) ||
    !finiteNumber(memory) ||
    !finiteNumber(available) ||
    !finiteNumber(disk) ||
    !finiteNumber(processes)
  ) {
    return null;
  }

  return {
    cpu_percent: cpu,
    memory_percent: memory,
    memory_available_mb: available,
    disk_percent: disk,
    processes,
    timestamp: Date.now(),
  };
}

/** Build provider status list from the real provider capability endpoint. */
function normaliseProviders(raw: unknown): { providers: ProviderStatus[]; summary: { total: number; connected: number; disconnected: number } } {
  const data = isRecord(raw) ? raw : {};
  const providers = Array.isArray(data.providers)
    ? data.providers.flatMap((value): ProviderStatus[] => {
        if (!isRecord(value)) return [];
        const provider = value.provider ?? value.id;
        const displayName = value.display_name ?? value.name;
        if (
          typeof provider !== 'string' ||
          typeof displayName !== 'string' ||
          typeof value.connected !== 'boolean' ||
          typeof value.status !== 'string' ||
          !Array.isArray(value.capabilities) ||
          !value.capabilities.every((capability) => typeof capability === 'string') ||
          typeof value.configured !== 'boolean'
        ) {
          return [];
        }
        return [{
          provider,
          display_name: displayName,
          connected: value.connected,
          status: value.status,
          capabilities: value.capabilities,
          configured: value.configured,
          ...(typeof value.model_count === 'number' ? { model_count: value.model_count } : {}),
        }];
      })
    : [];
  const summary = isRecord(data.provider_summary) ? data.provider_summary : {};
  const connected = finiteNumber(summary.connected)
    ? summary.connected
    : providers.filter((provider) => provider.connected).length;
  const total = finiteNumber(summary.total) ? summary.total : providers.length;
  return {
    providers,
    summary: {
      total,
      connected,
      disconnected: finiteNumber(summary.disconnected)
        ? summary.disconnected
        : total - connected,
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
  setSystem: (usage: SystemResourceUsage | null) => void;
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
            credentials: 'include',
          });
          const latency = Date.now() - start;
          if (res.ok) {
            get().setBackend({ connected: true, status: 'completed', latencyMs: latency, error: null, lastChecked: new Date() });
            const data = await res.json();
            const usage = normaliseSystemUsage(data);
            if (usage) get().setSystem(usage);
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
            fetch(API_ENDPOINTS.monitoring.metrics, { credentials: 'include' }),
            fetch(API_ENDPOINTS.monitoring.healthReport, { credentials: 'include' }),
          ]);
          let usage: SystemResourceUsage | null = null;
          if (metricsRes.status === 'fulfilled' && (metricsRes.value as Response).ok) {
            usage = normaliseSystemUsage(await (metricsRes.value as Response).json());
          }
          if (!usage && healthRes.status === 'fulfilled' && (healthRes.value as Response).ok) {
            usage = normaliseSystemUsage(await (healthRes.value as Response).json());
          }
          get().setSystem(usage);
        } catch {
          // Silent — system metrics are best-effort
        }
      },

      refreshProviders: async () => {
        try {
          const res = await fetch('/api/v1/integrations/providers?probe=false', {
            credentials: 'include',
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
          const res = await fetch(`${env.API_URL}/silverwing/api/laboratory/model`, {
            credentials: 'include',
          });
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

        const unsubscribe = wsClient.subscribe(`${wsUrl}/ws/monitoring`, (event: WsEvent) => {
          const data = isRecord(event.data) ? event.data : {};
          if (event.type === 'monitoring_update' && data.metrics) {
            const usage = normaliseSystemUsage(data.metrics);
            if (usage) get().setSystem(usage);
          }
          if (event.type === 'health_update') {
            const usage = normaliseSystemUsage(data);
            if (usage) get().setSystem(usage);
          }
          // 'activity' and 'notification' are custom types the backend may emit
          if (
            event.type === 'activity' &&
            typeof data.domain === 'string' &&
            typeof data.operation === 'string' &&
            typeof data.title === 'string' &&
            typeof data.severity === 'string'
          ) {
            get().addActivity({
              domain: data.domain as ActivityEvent['domain'],
              operation: data.operation,
              title: data.title,
              detail: typeof data.detail === 'string' ? data.detail : undefined,
              severity: data.severity as ActivityEvent['severity'],
              user: typeof data.user === 'string' ? data.user : undefined,
              resourceId: typeof data.resourceId === 'string' ? data.resourceId : undefined,
              resourceType: typeof data.resourceType === 'string' ? data.resourceType : undefined,
              metadata: isRecord(data.metadata) ? data.metadata : undefined,
            });
          }
          if (event.type === 'notification') {
            get().addNotification({
              title: typeof data.title === 'string' ? data.title : 'JARVIS',
              detail: typeof data.detail === 'string' ? data.detail : '',
              severity: data.severity === 'low' || data.severity === 'medium' ||
                data.severity === 'high' || data.severity === 'critical'
                ? data.severity
                : 'info',
              domain: typeof data.domain === 'string'
                ? data.domain as ActivityEvent['domain']
                : 'system',
            });
          }
          if (event.type === 'status_update' && typeof data.status === 'string') {
            get().setBackend({
              connected: typeof data.connected === 'boolean' ? data.connected : true,
              status: data.status as ResourceStatus,
              lastChecked: new Date(),
            });
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
