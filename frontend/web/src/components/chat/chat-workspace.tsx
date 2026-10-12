'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  Activity,
  BookOpen,
  Brain,
  ChevronRight,
  Gauge,
  Image,
  MapPin,
  Mic,
  Menu,
  Settings,
  Share2,
  Users,
  X,
  type LucideIcon,
} from 'lucide-react';
import { ChatWindow } from './chat-window';
import { WorldTaskPanel } from './world-task-panel';
import { SessionList } from './session-list';
import { useChatStore } from '@/features/chat/store';
import { useSystemStore } from '@/features/system/store';
import { usePlatformStore } from '@/stores/platform-store';
import { useAuthStore } from '@/stores/authStore';
import { ENVIRONMENTS, availabilityLabel, getEnvironment, type EnvironmentId } from '@/features/runtime/environment-registry';
import { useJarvisRuntime } from '@/features/runtime/store';

const environmentIcons: Record<EnvironmentId, LucideIcon> = {
  conversation: Activity,
  world: MapPin,
  visual: Image,
  voice: Mic,
  tasks: Users,
  knowledge: BookOpen,
  operations: Gauge,
  communications: Settings,
  devices: Settings,
  learning: Brain,
};

const navigableEnvironments = ENVIRONMENTS.filter((environment) =>
  environment.route && environment.id !== 'conversation',
);

function backendStatusLabel(connected: boolean, status: string) {
  if (connected) return 'Connected';
  if (status === 'idle' || status === 'loading') return 'Checking';
  if (status === 'degraded') return 'Degraded';
  if (status === 'offline') return 'Offline';
  return 'Unknown';
}

export function ChatWorkspace() {
  const sessions = useChatStore((state) => state.sessions);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const loadSession = useChatStore((state) => state.loadSession);
  const deleteSession = useChatStore((state) => state.deleteSession);
  const newSession = useChatStore((state) => state.newSession);
  const backend = usePlatformStore((state) => state.backend);
  const providerSummary = usePlatformStore((state) => state.providerSummary);
  const refreshBackend = usePlatformStore((state) => state.refreshBackend);
  const authStatus = useAuthStore((state) => state.authStatus);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const retrySessionCheck = useAuthStore((state) => state.retrySessionCheck);
  const systemStatus = useSystemStore((state) => state.status);
  const loadStatus = useSystemStore((state) => state.loadStatus);
  const isLoading = useChatStore((state) => state.isLoading);
  const isStreaming = useChatStore((state) => state.isStreaming);
  const activities = useJarvisRuntime((state) => state.activities);
  const currentEnvironment = useJarvisRuntime((state) => state.currentEnvironment);
  const currentTask = useJarvisRuntime((state) => state.currentTask);
  const voiceState = useJarvisRuntime((state) => state.voiceState);
  const capabilities = useJarvisRuntime((state) => state.capabilities);
  const integrations = useJarvisRuntime((state) => state.integrations);
  const capabilityRegistryReported = useJarvisRuntime((state) => state.capabilityRegistryReported);
  const rendererNegotiation = useJarvisRuntime((state) => state.rendererNegotiation);
  const rendererNegotiationError = useJarvisRuntime((state) => state.rendererNegotiationError);
  const currentPresentation = useJarvisRuntime((state) => state.currentPresentation);
  const runtimeState = useJarvisRuntime((state) => state.runtimeState);
  const endpointStatus = useJarvisRuntime((state) => state.endpointStatus);
  const endpointError = useJarvisRuntime((state) => state.endpointError);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    void refreshBackend();
    void loadStatus();
  }, [loadStatus, refreshBackend]);

  useEffect(() => {
    if (!mobileNavOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileNavOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [mobileNavOpen]);

  const [showEvents, setShowEvents] = useState(false);
  const [showEnvironments, setShowEnvironments] = useState(false);
  const [showCapabilities, setShowCapabilities] = useState(false);
  const [showTaskPanel, setShowTaskPanel] = useState(false);

  const serviceStatus = systemStatus?.status?.toLowerCase();
  const hasServiceStatus = ['online', 'degraded', 'offline'].includes(serviceStatus ?? '');
  const backendConnected = hasServiceStatus
    ? serviceStatus === 'online'
    : backend.connected;
  const backendLabel = backendStatusLabel(
    backendConnected,
    hasServiceStatus ? serviceStatus! : backend.status,
  );
  const readyCapabilities = capabilities.filter(
    (capability) => capability.availability === 'available' && capability.health === 'ok',
  ).length;
  const capabilityReadiness = capabilityRegistryReported
    ? `${readyCapabilities} of ${capabilities.length} ready`
    : 'Not reported';
  const runtimeActivity: Record<string, string> = {
    listening: 'Listening',
    thinking: 'Thinking',
    planning: 'Planning',
    executing: 'Working',
    searching: 'Searching',
    browsing: 'Browsing',
    observing: 'Observing',
    navigating: 'Navigating',
    generating: 'Generating',
    speaking: 'Speaking',
    explaining: 'Explaining',
    working: 'Working',
    learning: 'Learning',
    waiting: 'Waiting',
    completed: 'Completed',
    failed: 'Request failed',
    cancelled: 'Cancelled',
    offline: 'Offline',
  };
  let assistantActivity = 'Available';
  if (!isAuthenticated || authStatus === 'checking') assistantActivity = 'Starting';
  else if (hasServiceStatus && serviceStatus === 'offline') assistantActivity = 'Offline';
  else if (hasServiceStatus && serviceStatus === 'degraded') assistantActivity = 'Degraded';
  else if (!hasServiceStatus && !backendConnected) assistantActivity = 'Offline';
  else if (voiceState === 'listening') assistantActivity = 'Listening';
  else if (voiceState === 'speaking') assistantActivity = 'Speaking';
  else if (voiceState === 'processing') assistantActivity = 'Processing voice';
  else if (voiceState === 'error') assistantActivity = 'Voice error';
  else if (voiceState === 'unavailable') assistantActivity = 'Voice unavailable';
  else if (runtimeState !== 'idle') {
    assistantActivity = runtimeActivity[runtimeState] || 'Processing request';
  } else if (isStreaming) assistantActivity = 'Responding';
  else if (isLoading) assistantActivity = 'Processing request';
  const endpointActivity = endpointStatus.replaceAll('_', ' ');
  const presentationEnvironment = currentPresentation?.intent.environment.title
    || currentPresentation?.intent.environment.type.replaceAll('_', ' ');

  const router = useRouter();

  const openEnvironment = (environmentId: EnvironmentId, route: string | null) => {
    if (!route) return;
    useJarvisRuntime.getState().transitionEnvironment(environmentId);
    setShowEnvironments(false);
    setMobileNavOpen(false);
    router.push(route);
  };

  const selectSession = (sessionId: string) => {
    loadSession(sessionId);
    setMobileNavOpen(false);
  };
  const startNewSession = () => {
    newSession();
    setMobileNavOpen(false);
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#090e16] text-foreground">
      <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-white/[0.07] bg-[#090e16] px-3 sm:px-5">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            aria-label="Open conversation navigation"
            aria-controls="conversation-navigation"
            aria-expanded={mobileNavOpen}
            onClick={() => setMobileNavOpen(true)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 text-slate-300 transition hover:bg-white/[0.06] focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-300 lg:hidden"
          >
            <Menu aria-hidden="true" className="h-4 w-4" />
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span aria-hidden="true" className="flex h-6 w-6 items-center justify-center rounded-md border border-indigo-300/20 bg-indigo-400/[0.08] text-indigo-200">
                <Activity className="h-3.5 w-3.5" />
              </span>
              <h1 className="truncate text-sm font-semibold tracking-[0.14em] text-slate-100">JARVIS</h1>
            </div>
            <p className="mt-0.5 text-[10px] font-medium uppercase tracking-[0.18em] text-slate-500">
              {presentationEnvironment ? `JARVIS · ${presentationEnvironment}` : 'JARVIS runtime'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div
            role="img"
            aria-label={`JARVIS presence: ${assistantActivity}`}
            className={`inline-flex h-9 w-9 items-center justify-center rounded-full border border-cyan-200/20 bg-[radial-gradient(circle_at_50%_40%,rgba(103,232,249,0.35),rgba(49,46,129,0.35)_52%,rgba(15,23,42,0.8))] text-cyan-50 shadow-[0_0_20px_rgba(34,211,238,0.12)] ${isStreaming || isLoading ? 'ring-2 ring-cyan-300/30' : ''}`}
            title={`Presence reflects chat runtime state: ${assistantActivity}`}
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden>
              <circle cx="12" cy="8" r="3" fill="currentColor" opacity="0.92" />
              <path d="M5 20c1.5-3 6-4 7-4s5.5 1 7 4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" opacity="0.9" />
            </svg>
          </div>

          <div className="hidden sm:flex sm:flex-col sm:items-start">
            <span className="text-xs font-medium text-slate-100">{assistantActivity}</span>
            <span className="max-w-48 truncate text-[11px] text-slate-400">
              {endpointError || (currentTask
                ? `${currentTask.status} · ${currentTask.title}`
                : `Endpoint ${endpointActivity}`)}
            </span>
          </div>

          <button
            type="button"
            aria-label="Open voice environment"
            onClick={() => openEnvironment('voice', getEnvironment('voice').route)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 text-slate-200 hover:bg-white/[0.04]"
            title="Open JARVIS Voice"
          >
            <Mic aria-hidden="true" className="h-4 w-4" />
          </button>

          <button
            type="button"
            aria-label="Open environments"
            onClick={() => setShowEnvironments((s) => !s)}
            className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] text-slate-200 hover:bg-white/[0.04]"
            title="Open JARVIS environments"
          >
            <span className="font-mono text-[11px]">Environments</span>
          </button>

          <button
            type="button"
            aria-label="Show available capabilities"
            aria-expanded={showCapabilities}
            onClick={() => setShowCapabilities((visible) => !visible)}
            className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] text-slate-200 hover:bg-white/[0.04]"
            title="Inspect backend-reported capabilities and providers"
          >
            <Share2 aria-hidden="true" className="h-3.5 w-3.5" />
            <span className="font-mono text-[11px]">Capabilities</span>
          </button>

          <button
            type="button"
            aria-label="Show runtime events"
            onClick={() => setShowEvents((s) => !s)}
            className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] text-slate-200 hover:bg-white/[0.04]"
            title="Show recent runtime events"
          >
            <span className="font-mono text-[11px]">Events</span>
            <span className="ml-1 inline-flex h-5 w-5 items-center justify-center rounded-full bg-slate-700 text-xs font-semibold text-slate-100">{activities.length}</span>
          </button>

          <div
            role="status"
            aria-label={`Backend status: ${backendLabel}`}
            title={backend.error || (systemStatus ? `Runtime status: ${systemStatus.status}` : 'Checking backend status')}
            className="flex shrink-0 items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.025] px-3 py-1.5"
          >
            <span
              aria-hidden="true"
              className={`h-1.5 w-1.5 rounded-full ${
                backendConnected
                  ? 'bg-emerald-400'
                  : backendLabel === 'Offline'
                    ? 'bg-rose-400'
                    : backendLabel === 'Degraded'
                      ? 'bg-amber-300'
                      : 'bg-slate-500'
              }`}
            />
            <span className="text-[11px] text-slate-300">{backendLabel}</span>
          </div>
        </div>
      </header>

      {showEvents && (
        <div className="absolute right-4 top-14 z-50 w-[28rem] max-w-[92vw] rounded-md border border-white/[0.06] bg-[#061018] p-3 shadow-lg">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-slate-100">Runtime events</h3>
            <button onClick={() => setShowEvents(false)} className="text-slate-400">Close</button>
          </div>
          <div className="max-h-64 overflow-auto space-y-2">
            {activities.length === 0 ? <div className="text-sm text-slate-400">No runtime activity has been reported.</div> : activities.map((activity) => (
              <div key={activity.id} className="rounded-md border border-white/[0.03] bg-white/[0.02] p-2">
                <div className="flex items-center justify-between">
                  <div className="text-[12px] font-medium text-slate-100">{activity.summary}</div>
                  <div className="text-[11px] text-slate-400">{new Date(activity.occurredAt).toLocaleTimeString()}</div>
                </div>
                {activity.detail && <div className="mt-1 text-[11px] text-slate-400">{activity.detail}</div>}
                <div className="mt-1 text-[10px] uppercase tracking-wide text-slate-600">{activity.source}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {showCapabilities && (
        <section
          aria-label="Backend-reported capability graph"
          className="absolute right-4 top-14 z-50 max-h-[80vh] w-[34rem] max-w-[92vw] overflow-auto rounded-md border border-white/[0.06] bg-[#061018] p-3 shadow-lg"
        >
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-100">Capability graph</h3>
              <p className="mt-1 text-[11px] text-slate-400">
                Availability and permissions reported by the connected JARVIS runtime.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowCapabilities(false)}
              className="text-xs text-slate-400 hover:text-slate-100"
            >
              Close
            </button>
          </div>
          {!capabilityRegistryReported ? (
            <p className="rounded-md border border-white/[0.05] p-3 text-sm text-slate-400">
              Capability registry has not been reported by the backend.
            </p>
          ) : capabilities.length === 0 ? (
            <p className="rounded-md border border-white/[0.05] p-3 text-sm text-slate-400">
              The backend reported no registered capabilities.
            </p>
          ) : (
            <ul className="space-y-2">
              {capabilities.map((capability) => (
                <li key={capability.id} className="rounded-md border border-white/[0.05] bg-white/[0.02] p-2.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0">
                      <h4 className="truncate text-xs font-medium text-slate-100">{capability.id}</h4>
                      <p className="mt-0.5 text-[11px] text-slate-400">
                        {capability.category} · {capability.tool}
                      </p>
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] ${
                      capability.availability === 'available' && capability.health === 'ok'
                        ? 'bg-emerald-300/10 text-emerald-200'
                        : capability.availability === 'unavailable' || capability.health === 'offline'
                          ? 'bg-rose-300/10 text-rose-200'
                          : 'bg-amber-300/10 text-amber-200'
                    }`}>
                      {capability.availability.replaceAll('_', ' ')} · {capability.health}
                    </span>
                  </div>
                  <div className="mt-1.5 text-[10px] text-slate-500">
                    {[
                      capability.provider ? `Provider: ${capability.provider}` : null,
                      capability.model ? `Model: ${capability.model}` : null,
                      capability.permissions.length ? `Permissions: ${capability.permissions.join(', ')}` : null,
                      capability.aiBacked ? 'AI-backed' : null,
                    ].filter(Boolean).join(' · ') || 'No additional provider or permission metadata reported'}
                  </div>
                </li>
              ))}
            </ul>
          )}
          {currentPresentation && (
            <div className="mt-4 border-t border-white/[0.07] pt-3">
              <h4 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                Current presentation intent
              </h4>
              <p className="mt-2 text-xs text-slate-200">
                {currentPresentation.intent.environment.title || currentPresentation.intent.environment.type}
                <span className="text-slate-400"> · {currentPresentation.intent.mode || 'focused'}</span>
              </p>
              <p className="mt-1 text-[11px] text-slate-500">
                Semantic intent from JARVIS Core; rendering remains subject to negotiated client support.
              </p>
            </div>
          )}
          <div className="mt-4 border-t border-white/[0.07] pt-3">
            <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
              This client&apos;s render support
            </h4>
            {rendererNegotiationError ? (
              <p role="status" className="text-xs text-amber-200">
                Capability negotiation unavailable: {rendererNegotiationError}
              </p>
            ) : rendererNegotiation ? (
              <>
                <ul className="flex flex-wrap gap-1.5">
                  {rendererNegotiation.renderers.map((renderer) => (
                    <li key={renderer.type} className="rounded-full bg-cyan-300/10 px-2 py-1 text-[10px] text-cyan-100">
                      {renderer.type}
                    </li>
                  ))}
                </ul>
                {rendererNegotiation.fallbacks.map((fallback) => (
                  <p key={fallback.requested} className="mt-2 text-[11px] text-slate-400">
                    {fallback.requested} unavailable; {fallback.selected} selected. {fallback.reason}
                  </p>
                ))}
              </>
            ) : (
              <p className="text-xs text-slate-500">Renderer negotiation has not completed.</p>
            )}
          </div>
          <div className="mt-4 border-t border-white/[0.07] pt-3">
            <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
              Providers and services
            </h4>
            {integrations.length ? (
              <ul className="space-y-1.5">
                {integrations.map((integration) => (
                  <li key={integration.id} className="flex items-center justify-between gap-3 text-xs">
                    <span className="truncate text-slate-200">{integration.name}</span>
                    <span className={integration.connected ? 'shrink-0 text-emerald-200' : 'shrink-0 text-slate-400'}>
                      {integration.connected ? 'Connected' : integration.configured ? 'Configured · offline' : 'Not configured'}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-slate-500">Provider state has not been reported.</p>
            )}
          </div>
        </section>
      )}

      {showEnvironments && (
        <div className="absolute right-4 top-14 z-50 w-[28rem] max-w-[92vw] rounded-md border border-white/[0.06] bg-[#04121a] p-3 shadow-lg">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-slate-100">JARVIS environments</h3>
            <button onClick={() => setShowEnvironments(false)} className="text-slate-400">Close</button>
          </div>
          <div className="grid gap-2">
            {ENVIRONMENTS.map((environment) => (
              <button
                key={environment.id}
                type="button"
                onClick={() => openEnvironment(environment.id, environment.route)}
                disabled={!environment.route}
                aria-current={currentEnvironment === environment.id ? 'page' : undefined}
                className="text-left rounded-md border border-white/[0.04] bg-white/[0.02] px-3 py-2 enabled:hover:bg-white/[0.05] disabled:cursor-not-allowed disabled:opacity-55"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium text-slate-100">{environment.name}</div>
                    <div className="text-[11px] text-slate-400">{environment.description}</div>
                    <div className="mt-1 text-[10px] text-cyan-100/60">{environment.capabilities.join(' · ')}</div>
                  </div>
                  <div className="ml-3 shrink-0 text-right text-[10px] text-slate-400">
                    <div>{currentEnvironment === environment.id ? 'Here' : availabilityLabel(environment.availability)}</div>
                    {environment.requirement && <div className="mt-1 max-w-36 text-slate-500">{environment.requirement}</div>}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <div
          className={`${mobileNavOpen ? 'fixed inset-0 z-50' : 'hidden'} lg:relative lg:inset-auto lg:z-auto lg:block`}
        >
          {mobileNavOpen && (
            <button
              type="button"
              aria-label="Close conversation navigation"
              onClick={() => setMobileNavOpen(false)}
              className="fixed inset-0 bg-black/65 lg:hidden"
            />
          )}
          <aside
            id="conversation-navigation"
            aria-label="Conversation navigation"
            className="relative z-[51] flex h-full w-[min(86vw,18rem)] flex-col border-r border-white/[0.07] bg-[#0b111b] lg:w-64"
          >
            <div className="flex h-12 shrink-0 items-center justify-between border-b border-white/[0.06] px-4">
              <span className="text-xs font-medium text-slate-400">Your workspace</span>
              <button
                type="button"
                aria-label="Close conversation navigation"
                onClick={() => setMobileNavOpen(false)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-white/[0.06] hover:text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-300 lg:hidden"
              >
                <X aria-hidden="true" className="h-4 w-4" />
              </button>
            </div>

            <div className="min-h-0 flex-1 px-3 py-3">
              <SessionList
                sessions={sessions}
                currentSessionId={currentSessionId}
                onSelect={selectSession}
                onDelete={deleteSession}
                onNew={startNewSession}
              />
            </div>

            <nav aria-label="Platform sections" className="shrink-0 border-t border-white/[0.07] px-3 py-3">
              <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                Environments
              </p>
              <ul className="space-y-0.5">
                {navigableEnvironments.map((environment) => {
                  const Icon = environmentIcons[environment.id];
                  const label = environment.id === 'tasks' ? 'Agents & tasks' : environment.name;
                  return (
                  <li key={environment.id}>
                    <Link
                      href={environment.route!}
                      onClick={() => setMobileNavOpen(false)}
                      aria-current={currentEnvironment === environment.id ? 'page' : undefined}
                      className="group flex min-h-9 items-center gap-2.5 rounded-lg px-2 text-xs text-slate-400 transition hover:bg-white/[0.05] hover:text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-300"
                    >
                      <Icon aria-hidden="true" className="h-3.5 w-3.5 text-slate-500 group-hover:text-cyan-200" />
                      <span className="flex-1">{label}</span>
                      <ChevronRight aria-hidden="true" className="h-3 w-3 opacity-0 transition group-hover:opacity-60" />
                    </Link>
                  </li>
                )})}
              </ul>
            </nav>

            <section aria-label="Runtime readiness" className="shrink-0 border-t border-white/[0.07] px-4 py-3">
              <div className="mb-2 flex items-center gap-2">
                <Activity aria-hidden="true" className="h-3.5 w-3.5 text-slate-400" />
                <h2 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">
                  Runtime
                </h2>
              </div>
              <dl className="space-y-1.5 text-[11px]">
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-slate-400">Backend</dt>
                  <dd className={backendConnected ? 'font-medium text-emerald-300' : 'font-medium text-slate-200'}>
                    {backendLabel}
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-slate-400">Providers</dt>
                  <dd className="font-medium text-slate-200">
                    {providerSummary.total > 0
                      ? `${providerSummary.connected} of ${providerSummary.total} connected`
                      : 'Not reported'}
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-slate-400">Capabilities</dt>
                  <dd className="font-medium text-slate-200">{capabilityReadiness}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-slate-400">Session</dt>
                  <dd className="font-medium text-slate-200">
                    {authStatus === 'unavailable' && isAuthenticated ? (
                      <button
                        type="button"
                        onClick={() => void retrySessionCheck()}
                        className="rounded text-amber-200 underline decoration-amber-200/40 underline-offset-2 hover:text-amber-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-300"
                      >
                        Check unavailable · Retry
                      </button>
                    ) : authStatus === 'authenticated' ? (
                      'Signed in'
                    ) : authStatus === 'unauthenticated' ? (
                      'Not signed in'
                    ) : (
                      'Checking'
                    )}
                  </dd>
                </div>
              </dl>
            </section>
          </aside>
        </div>

        <main className="min-h-0 min-w-0 flex-1 overflow-hidden">
          <div className="flex h-full min-h-0 flex-col">
            <section
              aria-label="JARVIS command environment"
              className="relative flex shrink-0 flex-wrap items-center justify-between gap-x-6 gap-y-3 overflow-hidden border-b border-white/[0.07] bg-[radial-gradient(ellipse_at_14%_50%,rgba(70,97,180,0.13),transparent_38%),linear-gradient(100deg,#0b121d,#0a1019_60%,#0b111a)] px-4 py-3.5 sm:px-7"
            >
              <div aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-0 w-px bg-gradient-to-b from-transparent via-cyan-300/40 to-transparent" />
              <div className="min-w-0">
                <p className="text-[9px] font-semibold uppercase tracking-[0.24em] text-cyan-100/55">
                  JARVIS <span className="mx-1 text-slate-600">/</span> {getEnvironment(currentEnvironment).name}
                </p>
                <h2 className="mt-1 truncate text-lg font-medium tracking-[-0.025em] text-slate-100 sm:text-xl">
                  Tell JARVIS what you need.
                </h2>
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  aria-expanded={showTaskPanel}
                  aria-controls="world-task-panel"
                  onClick={() => setShowTaskPanel((visible) => !visible)}
                  className="rounded-lg border border-cyan-200/20 bg-cyan-300/[0.06] px-3 py-2 text-xs font-medium text-cyan-100 hover:bg-cyan-300/10"
                >
                  {showTaskPanel ? 'Close task workspace' : 'Submit a task'}
                </button>
                <span className="hidden h-8 w-px bg-white/[0.08] sm:block" aria-hidden="true" />
                <div className="min-w-[112px]">
                  <p className="text-[9px] font-medium uppercase tracking-[0.18em] text-slate-500">Assistant activity</p>
                  <p className="mt-1 flex items-center gap-2 text-xs font-medium text-slate-200">
                    <span
                      aria-hidden="true"
                      className={`h-1.5 w-1.5 rounded-full ${
                        isStreaming || isLoading ? 'animate-pulse bg-cyan-300' : 'bg-slate-500'
                      }`}
                    />
                    {assistantActivity}
                  </p>
                </div>
              </div>
            </section>
            {showTaskPanel && (
              <div id="world-task-panel">
                <WorldTaskPanel conversationId={currentSessionId} authenticated={isAuthenticated} />
              </div>
            )}
            <ChatWindow showSidebar={false} className="min-h-0 flex-1" />
          </div>
        </main>
      </div>
    </div>
  );
}
