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
import apiClient, { ApiClientError, getAuthToken } from '@/lib/api-client';
import wsClient, { type WsEvent } from '@/lib/websocket-client';
import env from '@/config/env';
import API_ENDPOINTS from '@/config/api';
import type {
  PlatformState,
  ProviderStatus,
  SystemResourceUsage,
  SystemResourceSample,
  ActivityEvent,
  NotificationItem,
  SeverityLevel,
  WorkspaceState,
  BackendConnection,
  ResourceStatus,
} from '@/lib/types/platform';
import type { RuntimeCapability, RuntimeCommand } from '@/lib/types/runtime';

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

let commandsRefreshInFlight: Promise<void> | null = null;

/** Convert real host metrics to the shared shape without inventing missing values. */
function normaliseSystemUsage(raw: unknown): SystemResourceUsage | null {
  if (!raw || typeof raw !== 'object') return null;
  const value = raw as Record<string, unknown>;
  const system = value.system && typeof value.system === 'object'
    ? value.system as Record<string, unknown>
    : value;
  const memory = value.memory && typeof value.memory === 'object'
    ? value.memory as Record<string, unknown>
    : null;

  if (value.available === false || system.available === false) return null;

  const cpu = typeof value.cpu_percent === 'number' ? value.cpu_percent : system.cpu_percent;
  const memoryPercent = typeof memory?.percent === 'number' ? memory.percent : system.memory_percent;
  const memoryAvailable = typeof memory?.available === 'number'
    ? memory.available / 1048576
    : system.memory_available_mb;
  const disk = typeof value.disk === 'number' ? value.disk : system.disk_percent;
  const processes = typeof value.processes === 'number'
    ? value.processes
    : typeof system.processes === 'number'
      ? system.processes
      : system.process_count;

  if (
    typeof cpu !== 'number' || !Number.isFinite(cpu)
    || typeof memoryPercent !== 'number' || !Number.isFinite(memoryPercent)
    || typeof memoryAvailable !== 'number' || !Number.isFinite(memoryAvailable)
    || typeof disk !== 'number' || !Number.isFinite(disk)
    || typeof processes !== 'number' || !Number.isFinite(processes)
  ) return null;

  const parsedTimestamp = typeof value.timestamp === 'string' ? Date.parse(value.timestamp) : Date.now();
  return {
    cpu_percent: cpu,
    memory_percent: memoryPercent,
    memory_available_mb: memoryAvailable,
    disk_percent: disk,
    processes,
    timestamp: Number.isFinite(parsedTimestamp) ? parsedTimestamp : Date.now(),
  };
}

/** Parse the server-side provider inventory without equating configuration with health. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parseProvider(value: unknown): ProviderStatus | null {
  if (!isRecord(value)) return null;
  const { id, name, category, connect_type, connected, configured, status, capabilities, reason, code_present } = value;
  if (
    typeof id !== 'string' || typeof name !== 'string' || typeof category !== 'string'
    || typeof connect_type !== 'string' || typeof connected !== 'boolean'
    || typeof configured !== 'boolean' || typeof status !== 'string'
    || !Array.isArray(capabilities) || !capabilities.every((capability) => typeof capability === 'string')
  ) return null;
  return {
    id, name, category, connect_type, connected, configured, status,
    capabilities,
    reason: typeof reason === 'string' ? reason : null,
    code_present: typeof code_present === 'boolean' ? code_present : undefined,
  };
}

function normaliseProviders(raw: unknown): { providers: ProviderStatus[]; summary: { total: number; connected: number; disconnected: number } } {
  const response = isRecord(raw) ? raw : {};
  const providers = (Array.isArray(response.providers) ? response.providers : [])
    .map(parseProvider)
    .filter((provider): provider is ProviderStatus => provider !== null);
  // "CONFIGURED" is not proof of a successful provider connection.
  const connected = providers.filter((provider) =>
    provider.status === 'HEALTHY' || provider.status.toLowerCase() === 'connected'
  ).length;
  const total = providers.length;
  return {
    providers,
    summary: {
      total,
      connected,
      disconnected: total - connected,
    },
  };
}

const RESOURCE_STATUSES = new Set<ResourceStatus>([
  'idle', 'loading', 'streaming', 'working', 'completed', 'failed', 'offline',
  'degraded', 'unauthorized', 'rate_limited', 'queued', 'paused', 'cancelled',
]);
const ACTIVITY_DOMAINS = new Set<ActivityEvent['domain']>([
  'agent', 'tool', 'model', 'provider', 'security', 'training', 'learning',
  'mission', 'research', 'system', 'chat', 'browser',
]);
const SEVERITIES = new Set<SeverityLevel>(['info', 'low', 'medium', 'high', 'critical']);

function parseActivity(value: unknown): Omit<ActivityEvent, 'id' | 'timestamp'> | null {
  if (!isRecord(value)) return null;
  const { domain, operation, title, detail, severity, user, resourceId, resourceType, metadata } = value;
  if (
    typeof domain !== 'string' || !ACTIVITY_DOMAINS.has(domain as ActivityEvent['domain'])
    || typeof operation !== 'string' || typeof title !== 'string'
    || typeof severity !== 'string' || !SEVERITIES.has(severity as SeverityLevel)
  ) return null;
  return {
    domain: domain as ActivityEvent['domain'],
    operation,
    title,
    detail: typeof detail === 'string' ? detail : undefined,
    severity: severity as SeverityLevel,
    user: typeof user === 'string' ? user : undefined,
    resourceId: typeof resourceId === 'string' ? resourceId : undefined,
    resourceType: typeof resourceType === 'string' ? resourceType : undefined,
    metadata: isRecord(metadata) ? metadata : undefined,
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
  setProviders: (
    providers: ProviderStatus[],
    summary: { total: number; connected: number; disconnected: number },
    availability?: ResourceStatus,
  ) => void;
  setSystem: (usage: SystemResourceUsage | null) => void;
  setRuntimeCommand: (command: RuntimeCommand) => void;
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
  refreshCommands: () => Promise<void>;
  refreshProviders: () => Promise<void>;
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
    providerAvailability: 'idle',
    system: null,
    systemHistory: [],
    commands: [],
    commandCapabilities: [],
    commandAvailability: 'idle',
    commandCapabilitiesAvailability: 'idle',
    commandError: null,
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

      setProviders: (providers, summary, availability = 'completed') =>
        set({ providers, providerSummary: summary, providerAvailability: availability }),

      setSystem: (usage) =>
        set((state) => {
          if (!usage) return { system: null, systemHistory: [] };
          const lastSample = state.systemHistory[state.systemHistory.length - 1];
          const sample: SystemResourceSample = {
            cpu_percent: usage.cpu_percent,
            timestamp: usage.timestamp,
          };
          return {
            system: usage,
            systemHistory: lastSample?.timestamp === sample.timestamp
              ? state.systemHistory
              : [...state.systemHistory, sample].slice(-30),
          };
        }),

      setRuntimeCommand: (command) =>
        set((state) => ({
          commands: [
            command,
            ...state.commands.filter((item) => item.command_id !== command.command_id),
          ].slice(0, 100),
          commandAvailability: 'completed',
        })),

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
            get().setSystem(normaliseSystemUsage(data));
          } else if (res.status === 401 || res.status === 403) {
            get().setSystem(null);
            get().setBackend({ connected: false, status: 'unauthorized', error: `HTTP ${res.status}`, lastChecked: new Date() });
          } else if (res.status >= 500) {
            get().setSystem(null);
            get().setBackend({ connected: false, status: 'offline', error: `Backend error: ${res.status}`, lastChecked: new Date() });
          } else {
            get().setSystem(null);
            get().setBackend({ connected: false, status: 'degraded', error: `HTTP ${res.status}`, lastChecked: new Date() });
          }
        } catch (error) {
          get().setSystem(null);
          get().setBackend({
            connected: false,
            status: 'offline',
            error: error instanceof Error ? error.message : 'Connection failed',
            lastChecked: new Date(),
          });
        }
      },

      refreshCommands: async () => {
        if (commandsRefreshInFlight) return commandsRefreshInFlight;
        commandsRefreshInFlight = (async () => {
          const token = getAuthToken();
          if (!token) {
            set({
              commands: [],
              commandCapabilities: [],
              commandAvailability: 'unauthorized',
              commandCapabilitiesAvailability: 'unauthorized',
              commandError: null,
            });
            return;
          }

          const [commandsResult, capabilitiesResult] = await Promise.allSettled([
            apiClient.get<{ commands: RuntimeCommand[] }>('/api/v1/commands?limit=100'),
            apiClient.get<{ capabilities: RuntimeCapability[] }>('/api/v1/commands/capabilities'),
          ]);
          const commandError = commandsResult.status === 'rejected'
            ? commandsResult.reason instanceof Error
              ? commandsResult.reason.message
              : 'Command runtime state could not be loaded.'
            : capabilitiesResult.status === 'rejected'
              ? capabilitiesResult.reason instanceof Error
                ? capabilitiesResult.reason.message
                : 'Command capability registry could not be loaded.'
              : null;

          set({
            commands: commandsResult.status === 'fulfilled' && Array.isArray(commandsResult.value.commands)
              ? commandsResult.value.commands
              : [],
            commandCapabilities: capabilitiesResult.status === 'fulfilled' && Array.isArray(capabilitiesResult.value.capabilities)
              ? capabilitiesResult.value.capabilities
              : [],
            commandAvailability: commandsResult.status === 'fulfilled'
              ? 'completed'
              : commandsResult.reason instanceof ApiClientError && [401, 403].includes(commandsResult.reason.status)
                ? 'unauthorized'
                : 'offline',
            commandCapabilitiesAvailability: capabilitiesResult.status === 'fulfilled'
              ? 'completed'
              : capabilitiesResult.reason instanceof ApiClientError && [401, 403].includes(capabilitiesResult.reason.status)
                ? 'unauthorized'
                : 'offline',
            commandError,
          });
        })().finally(() => {
          commandsRefreshInFlight = null;
        });
        return commandsRefreshInFlight;
      },

      refreshProviders: async () => {
        const token = getAuthToken();
        if (!token) {
          get().setProviders([], { total: 0, connected: 0, disconnected: 0 }, 'unauthorized');
          return;
        }
        try {
          const res = await fetch(`${API_ENDPOINTS.integrations.providers}?probe=false`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (res.ok) {
            const data = await res.json();
            const { providers, summary } = normaliseProviders(data);
            get().setProviders(providers, summary);
          } else {
            const availability: ResourceStatus = res.status === 401 || res.status === 403
              ? 'unauthorized'
              : res.status >= 500 ? 'offline' : 'degraded';
            get().setProviders([], { total: 0, connected: 0, disconnected: 0 }, availability);
          }
        } catch {
          get().setProviders([], { total: 0, connected: 0, disconnected: 0 }, 'offline');
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
          get().refreshCommands(),
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
          const data = event.data;
          if (event.type === 'monitoring_update' && isRecord(data) && 'metrics' in data) {
            get().setSystem(normaliseSystemUsage(data.metrics));
          }
          if (event.type === 'health_update') {
            get().setSystem(normaliseSystemUsage(data));
          }
          if (event.type === 'activity') {
            const activity = parseActivity(data);
            if (activity) get().addActivity(activity);
            else console.warn('[Platform] Ignored malformed activity event.');
          }
          if (event.type === 'notification') {
            if (
              isRecord(data)
              && typeof data.title === 'string'
              && typeof data.detail === 'string'
              && typeof data.severity === 'string'
              && SEVERITIES.has(data.severity as SeverityLevel)
              && typeof data.domain === 'string'
              && ACTIVITY_DOMAINS.has(data.domain as ActivityEvent['domain'])
            ) {
              get().addNotification({
                title: data.title,
                detail: data.detail,
                severity: data.severity as SeverityLevel,
                domain: data.domain as ActivityEvent['domain'],
              });
            } else {
              console.warn('[Platform] Ignored malformed notification event.');
            }
          }
          if (event.type === 'status_update') {
            if (isRecord(data) && typeof data.status === 'string' && RESOURCE_STATUSES.has(data.status as ResourceStatus)) {
              get().setBackend({
                connected: typeof data.connected === 'boolean' ? data.connected : get().backend.connected,
                status: data.status as ResourceStatus,
                lastChecked: new Date(),
              });
            } else {
              console.warn('[Platform] Ignored malformed backend status event.');
            }
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
export const useProviders = () => usePlatformStore((s) => ({
  providers: s.providers,
  summary: s.providerSummary,
  status: s.providerAvailability,
}));
export const useActivity = () => usePlatformStore((s) => s.activity);
export const useNotifications = () => usePlatformStore((s) => s.notifications);
export const useWorkspace = () => usePlatformStore((s) => s.workspace);
export const useSilverwing = () => usePlatformStore((s) => s.silverwing);
export const useUser = () => usePlatformStore((s) => s.user);
export const useNavigationContext = (path: string) => usePlatformStore((s) => s.navigationHistory.filter((h) => h.path === path).sort((a, b) => b.timestamp - a.timestamp)[0]?.context ?? null);

export default usePlatformStore;
