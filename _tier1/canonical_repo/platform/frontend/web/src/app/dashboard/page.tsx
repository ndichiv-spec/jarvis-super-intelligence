'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Activity,
  AlertCircle,
  ArrowUpRight,
  Bot,
  Boxes,
  ChevronDown,
  Globe2,
  Image,
  Loader2,
  Map,
  Mic,
  RefreshCw,
  Shield,
  Wrench,
} from 'lucide-react';
import { ChatWindow } from '@/components/chat/chat-window';
import { Badge } from '@/components/ui/badge';
import { usePlatformStore } from '@/stores/platform-store';
import type { RuntimeCapability } from '@/lib/types/runtime';
import type { ResourceStatus } from '@/lib/types/platform';

type RuntimeHealth = 'checking' | 'operational' | 'degraded' | 'unavailable' | 'unknown';

interface RuntimeHealthView {
  state: RuntimeHealth;
  readiness: string | null;
  checkedAt: Date | null;
  checking: boolean;
}

interface StatusResponse {
  status?: unknown;
  service_readiness?: unknown;
  runtime?: {
    status?: unknown;
    service_readiness?: unknown;
  };
}

const STATUS_POLL_INTERVAL = 30_000;

function getRuntimeHealth(response: StatusResponse): RuntimeHealth {
  const rawStatus = typeof response.status === 'string'
    ? response.status
    : typeof response.runtime?.status === 'string'
      ? response.runtime.status
      : '';

  switch (rawStatus.toUpperCase()) {
    case 'OPERATIONAL':
      return 'operational';
    case 'DEGRADED':
      return 'degraded';
    case 'UNAVAILABLE':
      return 'unavailable';
    default:
      return 'unknown';
  }
}

function healthStyles(state: RuntimeHealth): { label: string; classes: string; dot: string } {
  switch (state) {
    case 'operational':
      return {
        label: 'Operational',
        classes: 'border-emerald-300/20 bg-emerald-300/[0.07] text-emerald-200',
        dot: 'bg-emerald-300',
      };
    case 'degraded':
      return {
        label: 'Degraded',
        classes: 'border-amber-300/20 bg-amber-300/[0.07] text-amber-100',
        dot: 'bg-amber-300',
      };
    case 'unavailable':
      return {
        label: 'Unavailable',
        classes: 'border-rose-300/20 bg-rose-300/[0.07] text-rose-200',
        dot: 'bg-rose-300',
      };
    case 'checking':
      return {
        label: 'Checking',
        classes: 'border-cyan-200/15 bg-cyan-200/[0.05] text-cyan-100',
        dot: 'bg-cyan-200',
      };
    default:
      return {
        label: 'Unverified',
        classes: 'border-white/10 bg-white/[0.04] text-slate-300',
        dot: 'bg-slate-400',
      };
  }
}

function capabilityStateStyles(availability: string): string {
  switch (availability.toUpperCase()) {
    case 'AVAILABLE':
      return 'border-emerald-300/20 bg-emerald-300/[0.06] text-emerald-200';
    case 'UNAVAILABLE':
    case 'BLOCKED':
      return 'border-rose-300/20 bg-rose-300/[0.06] text-rose-200';
    case 'DEGRADED':
    case 'CONFIGURED':
      return 'border-amber-300/20 bg-amber-300/[0.06] text-amber-100';
    default:
      return 'border-white/10 bg-white/[0.04] text-slate-300';
  }
}

function capabilityLoadingMessage(status: ResourceStatus): string {
  switch (status) {
    case 'unauthorized':
      return 'Registry access denied. This session is not authorized to view owner-scoped capabilities.';
    case 'offline':
      return 'The backend is unavailable, so the capability registry could not be reached. The shell will retry automatically.';
    case 'failed':
      return 'The capability registry request failed. The shell will retry automatically.';
    case 'degraded':
      return 'The capability registry is degraded and capability data is not available yet.';
    case 'rate_limited':
      return 'The capability registry is temporarily rate-limited. The shell will retry automatically.';
    case 'cancelled':
      return 'The capability registry request was cancelled.';
    default:
      return 'Checking the backend capability registry…';
  }
}

function CapabilityItem({ capability }: { capability: RuntimeCapability }) {
  return (
    <li className="rounded-lg border border-white/[0.07] bg-black/10 px-3 py-2.5">
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-slate-100" title={capability.name}>
            {capability.name}
          </p>
          <p className="mt-1 truncate text-xs text-slate-400">
            {capability.domain}
            <span aria-hidden="true" className="px-1.5 text-slate-700">·</span>
            Risk: {capability.risk_level}
          </p>
        </div>
        <Badge className={`shrink-0 px-2 py-0.5 text-xs uppercase tracking-wide ${capabilityStateStyles(capability.availability)}`}>
          {capability.availability}
        </Badge>
      </div>
      {capability.availability_reason && (
        <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-slate-400">
          {capability.availability_reason}
        </p>
      )}
    </li>
  );
}

function RuntimeCapabilities({
  capabilities,
  availability,
  refreshing,
}: {
  capabilities: RuntimeCapability[];
  availability: ResourceStatus;
  refreshing: boolean;
}) {
  const [expanded, setExpanded] = useState(true);
  const hasRegistry = availability === 'completed';
  const availableCount = hasRegistry
    ? capabilities.filter((capability) => capability.availability === 'AVAILABLE').length
    : null;
  const registryLoading = availability === 'idle' || availability === 'loading';
  const registryUnavailable = availability === 'offline' || availability === 'failed';

  return (
    <section
      aria-labelledby="runtime-capabilities-heading"
      className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-white/[0.09] bg-[#0b111b]"
    >
      <div className="flex items-start justify-between gap-3 border-b border-white/[0.07] px-4 py-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-cyan-200/10 bg-cyan-200/[0.04] text-cyan-100/80">
            <Boxes aria-hidden="true" className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <h2 id="runtime-capabilities-heading" className="text-sm font-semibold text-slate-100">
              Runtime capabilities
            </h2>
            <p className="mt-1 text-xs leading-relaxed text-slate-400">
              Registered by the backend; availability is reported by the runtime.
            </p>
          </div>
        </div>
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls="runtime-capabilities-content"
          aria-label={expanded ? 'Collapse runtime capabilities' : 'Expand runtime capabilities'}
          onClick={() => setExpanded((value) => !value)}
          className="mt-0.5 rounded-md p-1 text-slate-500 transition-colors hover:bg-white/[0.05] hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200/50"
        >
          <ChevronDown className={`h-4 w-4 transition-transform ${expanded ? '' : '-rotate-90'}`} />
        </button>
      </div>

      {expanded && (
        <div id="runtime-capabilities-content" className="flex min-h-0 flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
            <p className="text-xs text-slate-400">
              {hasRegistry
                ? `${availableCount} available · ${capabilities.length} registered`
                : refreshing
                  ? 'Refreshing registry…'
                  : 'Registry status'}
            </p>
            {refreshing && (
              <Loader2 aria-label="Refreshing capabilities" className="h-3.5 w-3.5 animate-spin text-cyan-200/70 motion-reduce:animate-none" />
            )}
          </div>

          {hasRegistry && capabilities.length > 0 ? (
            <ul className="min-h-0 space-y-2 overflow-y-auto p-3" aria-live="polite">
              {capabilities.map((capability) => (
                <CapabilityItem key={capability.id} capability={capability} />
              ))}
            </ul>
          ) : hasRegistry ? (
            <div role="status" className="m-3 rounded-lg border border-dashed border-white/10 px-4 py-5 text-center">
              <Boxes aria-hidden="true" className="mx-auto h-5 w-5 text-slate-500" />
              <p className="mt-2 text-xs font-medium text-slate-300">No capabilities registered</p>
              <p className="mt-1 text-xs text-slate-400">The backend returned an empty capability registry.</p>
            </div>
          ) : (
            <div role={registryUnavailable ? 'alert' : 'status'} className="m-3 rounded-lg border border-dashed border-white/10 px-4 py-5 text-center">
              {registryLoading ? (
                <Loader2 aria-hidden="true" className="mx-auto h-5 w-5 animate-spin text-cyan-200/70 motion-reduce:animate-none" />
              ) : availability === 'unauthorized' ? (
                <Shield aria-hidden="true" className="mx-auto h-5 w-5 text-amber-200/80" />
              ) : (
                <AlertCircle aria-hidden="true" className="mx-auto h-5 w-5 text-rose-200/70" />
              )}
              <p className="mt-2 text-xs leading-relaxed text-slate-300">
                {capabilityLoadingMessage(availability)}
              </p>
            </div>
          )}

          <nav aria-label="Runtime destinations" className="mt-auto space-y-1 border-t border-white/[0.07] p-3">
            <RuntimeLink
              href="/dashboard/commands"
              icon={Wrench}
              label="Command center"
              detail="Submit goals and inspect execution traces"
            />
            <RuntimeLink
              href="/dashboard/agents"
              icon={Bot}
              label="Agents"
              detail="Review registered agents and orchestration"
            />
            <RuntimeLink
              href="/dashboard/connections"
              icon={Shield}
              label="Connections"
              detail="Inspect providers and integrations"
            />
          </nav>
        </div>
      )}
    </section>
  );
}

function RuntimeLink({
  href,
  icon: Icon,
  label,
  detail,
}: {
  href: string;
  icon: typeof Wrench;
  label: string;
  detail: string;
}) {
  return (
    <Link
      href={href}
      className="group flex items-center gap-3 rounded-lg px-2.5 py-2 transition-colors hover:bg-white/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200/50"
    >
      <Icon aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-500 transition-colors group-hover:text-cyan-100/80" />
      <span className="min-w-0 flex-1">
        <span className="block text-xs font-medium text-slate-200">{label}</span>
        <span className="mt-0.5 block truncate text-xs text-slate-400">{detail}</span>
      </span>
      <ArrowUpRight aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-slate-600 transition-colors group-hover:text-cyan-100/70" />
    </Link>
  );
}

const WORKSPACE_LINKS = [
  {
    href: '/dashboard/embedded-browser',
    icon: Globe2,
    label: 'Browser',
    detail: 'Fetch, extract & preview',
  },
  {
    href: '/locations',
    icon: Map,
    label: 'Locations',
    detail: 'Maps & public geography',
  },
  {
    href: '/image-generation',
    icon: Image,
    label: 'Image',
    detail: 'Create with configured providers',
  },
  {
    href: '/voice',
    icon: Mic,
    label: 'Voice',
    detail: 'Speak or type to JARVIS',
  },
];

export default function DashboardPage() {
  const [health, setHealth] = useState<RuntimeHealthView>({
    state: 'checking',
    readiness: null,
    checkedAt: null,
    checking: true,
  });
  const [refreshToken, setRefreshToken] = useState(0);
  const capabilities = usePlatformStore((state) => state.commandCapabilities);
  const capabilityAvailability = usePlatformStore((state) => state.commandCapabilitiesAvailability);
  const refreshCommands = usePlatformStore((state) => state.refreshCommands);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;

    const checkStatus = async () => {
      controller = new AbortController();
      setHealth((current) => ({
        ...current,
        state: current.checkedAt ? current.state : 'checking',
        checking: true,
      }));

      try {
        const response = await fetch('/api/v1/status', {
          headers: { Accept: 'application/json' },
          cache: 'no-store',
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const payload = await response.json() as StatusResponse;
        if (
          typeof payload.status !== 'string'
          && typeof payload.runtime?.status !== 'string'
        ) {
          setHealth({
            state: 'unknown',
            readiness: null,
            checkedAt: new Date(),
            checking: false,
          });
        } else {
          const readiness = typeof payload.service_readiness === 'string'
            ? payload.service_readiness
            : typeof payload.runtime?.service_readiness === 'string'
              ? payload.runtime.service_readiness
              : null;
          setHealth({
            state: getRuntimeHealth(payload),
            readiness,
            checkedAt: new Date(),
            checking: false,
          });
        }
      } catch (error) {
        if (cancelled || (error instanceof Error && error.name === 'AbortError')) return;
        setHealth({
          state: 'unavailable',
          readiness: null,
          checkedAt: new Date(),
          checking: false,
        });
      } finally {
        if (!cancelled) timer = setTimeout(checkStatus, STATUS_POLL_INTERVAL);
      }
    };

    void checkStatus();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      controller?.abort();
    };
  }, [refreshToken]);

  useEffect(() => {
    void refreshCommands();
  }, [refreshCommands]);

  const status = healthStyles(health.state);
  const capabilityRefreshing = capabilityAvailability === 'idle'
    || capabilityAvailability === 'loading';

  return (
    <main className="mx-auto flex min-h-[calc(100dvh-4rem)] w-full min-w-0 max-w-[1680px] flex-col gap-4 px-4 py-4 md:gap-5 md:px-6 md:py-5">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-4 border-b border-white/[0.07] pb-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-cyan-200/15 bg-cyan-200/[0.05] text-cyan-100">
            <Activity aria-hidden="true" className="h-[18px] w-[18px]" />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-100/70">JARVIS · Operator workbench</p>
            <h1 className="mt-0.5 text-lg font-semibold tracking-tight text-slate-100 md:text-xl">Start with a conversation</h1>
            <p className="mt-1 text-xs leading-relaxed text-slate-400">Chat, inspect registered capabilities, and move into runtime operations.</p>
          </div>
        </div>

        <div className="flex w-full items-center justify-between gap-2 sm:w-auto sm:justify-end">
          <div className={`inline-flex items-center gap-2 whitespace-nowrap rounded-full border px-2.5 py-1.5 text-xs font-medium sm:px-3 ${status.classes}`} role="status" aria-live="polite">
            {health.checking
              ? <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
              : <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${status.dot}`} />}
            <span>Runtime {status.label}</span>
          </div>
          <button
            type="button"
            onClick={() => setRefreshToken((value) => value + 1)}
            disabled={health.checking}
            aria-label="Refresh runtime status"
            title="Refresh runtime status"
            className="rounded-lg border border-white/[0.09] bg-white/[0.025] p-2 text-slate-400 transition-colors hover:bg-white/[0.06] hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200/50 disabled:cursor-wait disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${health.checking ? 'animate-spin motion-reduce:animate-none' : ''}`} />
          </button>
        </div>
        <p className="basis-full -mt-2 break-words text-xs text-slate-400 sm:pl-[52px]">
          {health.checking && !health.checkedAt
            ? 'Checking the backend status endpoint…'
            : health.readiness
              ? `Service readiness: ${health.readiness}${health.checkedAt ? ` · Checked ${health.checkedAt.toLocaleTimeString()}` : ''}`
              : health.state === 'unavailable'
                ? 'The backend status endpoint could not be reached.'
                : health.state === 'unknown'
                  ? 'The backend returned an unrecognized runtime status.'
                  : health.checkedAt
                    ? `Last checked ${health.checkedAt.toLocaleTimeString()}`
                    : 'Runtime status has not been verified.'}
        </p>
      </header>

      <nav aria-label="Capability workspaces" className="grid shrink-0 grid-cols-2 gap-2 sm:grid-cols-4">
        {WORKSPACE_LINKS.map(({ href, icon: Icon, label, detail }) => (
          <Link
            key={href}
            href={href}
            className="group flex min-w-0 items-center gap-2.5 rounded-lg border border-white/[0.07] bg-[#0b111b] px-3 py-2.5 transition-colors hover:border-cyan-200/20 hover:bg-white/[0.035] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200/50"
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-white/[0.07] bg-white/[0.025] text-slate-400 transition-colors group-hover:text-cyan-100">
              <Icon aria-hidden="true" className="h-4 w-4" />
            </span>
            <span className="min-w-0">
              <span className="block text-xs font-medium text-slate-100">{label}</span>
              <span className="mt-0.5 block truncate text-[11px] text-slate-400">{detail}</span>
            </span>
            <ArrowUpRight aria-hidden="true" className="ml-auto h-3.5 w-3.5 shrink-0 text-slate-600 transition-colors group-hover:text-cyan-100/70" />
          </Link>
        ))}
      </nav>

      <div className="grid min-h-0 min-w-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <section
          aria-label="JARVIS conversation"
          className="h-[min(68vh,760px)] min-h-[520px] min-w-0 overflow-hidden rounded-xl border border-white/[0.09] bg-[#0b111b] xl:h-[calc(100dvh-11rem)] xl:min-h-[560px]"
        >
          <ChatWindow className="min-h-0" />
        </section>
        <RuntimeCapabilities
          capabilities={capabilities}
          availability={capabilityAvailability}
          refreshing={capabilityRefreshing}
        />
      </div>
    </main>
  );
}
