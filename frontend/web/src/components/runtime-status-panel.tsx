"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Check, Clock3, Cpu, Database, Loader2, RefreshCw, Sparkles, Wifi } from "lucide-react";
import apiClient, { AuthError } from "@/lib/api-client";
import { API_ENDPOINTS } from "@/config/api";

interface RuntimeStatusState {
  version: string;
  timestamp: string;
  platform: {
    status: string;
    uptime_seconds: number;
    environment: string;
  };
  system_health: {
    backend: string;
    database: string;
    queue: string;
  };
  deployment: {
    git_sha: string;
    build_time: string;
    environment: string;
    deployment_id: string;
  };
  ai: {
    enabled: boolean;
    provider: string;
    capabilities: string[];
    silverwing: {
      configured: boolean;
      reachable: boolean;
      healthy: boolean;
      status: string;
      last_checked: string | null;
      errors: string | null;
      model: string;
    };
  };
}

function formatUptime(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return "Not reported";
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);
  return days > 0 ? `${days}d ${hours}h ${minutes}m` : `${hours}h ${minutes}m`;
}

function formatTime(value?: string | null) {
  if (!value) return "Not reported";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not reported" : date.toLocaleString();
}

function isHealthy(value?: string | null) {
  return ["healthy", "ok", "online", "connected", "ready", "operational", "up"].includes((value || "").toLowerCase());
}

function StatusValue({ label, value, healthy }: { label: string; value: string; healthy: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-white/10 py-3 last:border-b-0">
      <dt className="text-sm text-slate-400">{label}</dt>
      <dd className={`flex items-center gap-2 text-right text-sm font-medium ${healthy ? "text-emerald-300" : "text-amber-200"}`}>
        <span className={`h-1.5 w-1.5 rounded-full ${healthy ? "bg-emerald-300" : "bg-amber-300"}`} aria-hidden="true" />
        {value || "Unknown"}
      </dd>
    </div>
  );
}

export function RuntimeStatusPanel() {
  const [state, setState] = useState<RuntimeStatusState | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const refresh = useCallback(async (background = false) => {
    if (background) setRefreshing(true);
    else setLoading(true);
    try {
      const result = await apiClient.get<RuntimeStatusState>(API_ENDPOINTS.holographic.state);
      setState(result);
      setLastUpdated(new Date().toISOString());
      setError(null);
    } catch (cause) {
      if (!(cause instanceof AuthError)) {
        setError(cause instanceof Error ? cause.message : "Unable to retrieve system state.");
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const initialRefresh = window.setTimeout(() => void refresh(), 0);
    const interval = window.setInterval(() => void refresh(true), 30_000);
    return () => {
      window.clearTimeout(initialRefresh);
      window.clearInterval(interval);
    };
  }, [refresh]);

  const silverwing = state?.ai.silverwing ?? {
    configured: false,
    reachable: false,
    healthy: false,
    status: "Unknown",
    last_checked: null,
    errors: null,
    model: "",
  };

  const statusCount = state
    ? [state.platform.status, state.system_health.backend, state.system_health.database, state.system_health.queue, state.ai.enabled ? "online" : "offline"].filter(isHealthy).length
    : 0;
  const statusTotal = state ? 5 : 0;

  return (
    <main className="min-h-full bg-[#080d12] px-4 py-8 text-slate-100 sm:px-7 lg:px-10">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 flex flex-col justify-between gap-5 border-b border-white/10 pb-6 sm:flex-row sm:items-end">
          <div>
            <div className="mb-4 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.22em] text-cyan-300">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              JARVIS / Runtime status
            </div>
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Runtime status</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
              Real-time platform health, AI availability, and connected service readiness across the JARVIS environment.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void refresh(Boolean(state))}
            disabled={loading || refreshing}
            className="inline-flex min-h-10 items-center justify-center gap-2 self-start border border-white/15 px-4 text-sm text-slate-200 transition-colors hover:border-cyan-300/50 hover:text-cyan-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 disabled:cursor-wait disabled:opacity-60 sm:self-auto"
          >
            {loading || refreshing ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
            )}
            Refresh status
          </button>
        </header>

        {error && (
          <div role="alert" className="mb-6 flex items-start gap-3 border border-rose-400/30 bg-rose-950/20 p-4 text-sm text-rose-200">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <div>
              <p className="font-medium">{state ? "Could not refresh system state" : "System state is unavailable"}</p>
              <p className="mt-1 text-rose-200/75">{error}</p>
              {state && <p className="mt-2 text-xs text-rose-200/60">Displayed values are from the last successful response.</p>}
            </div>
          </div>
        )}

        {loading && !state ? (
          <div className="flex min-h-64 items-center justify-center border border-white/10 bg-[#0b1218]" role="status">
            <span className="flex items-center gap-3 text-sm text-slate-400">
              <Loader2 className="h-4 w-4 animate-spin text-cyan-300" aria-hidden="true" />
              Requesting live system state…
            </span>
          </div>
        ) : !state ? (
          <div className="border border-dashed border-white/10 px-6 py-14 text-center">
            <Wifi className="mx-auto h-6 w-6 text-slate-600" aria-hidden="true" />
            <h2 className="mt-4 text-sm font-medium text-slate-200">No live status available</h2>
            <p className="mt-2 text-xs text-slate-500">The system-state endpoint did not return data. Retry when the service is reachable.</p>
            <button
              type="button"
              onClick={() => void refresh()}
              className="mt-5 min-h-10 border border-white/15 px-4 text-sm text-slate-200 hover:border-cyan-300/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
            >
              Try again
            </button>
          </div>
        ) : (
          <>
            <section aria-label="System summary" className="grid gap-px border border-white/10 bg-white/10 sm:grid-cols-3">
              <div className="bg-[#0b1218] p-5">
                <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-slate-500">
                  <Wifi className="h-3.5 w-3.5 text-cyan-300" aria-hidden="true" /> Platform
                </div>
                <p className={`mt-3 text-2xl font-semibold ${isHealthy(state.platform.status) ? "text-emerald-300" : "text-amber-200"}`}>
                  {state.platform.status || "Unknown"}
                </p>
                <p className="mt-2 text-xs text-slate-500">{state.platform.environment || "Environment not reported"}</p>
              </div>
              <div className="bg-[#0b1218] p-5">
                <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-slate-500">
                  <Check className="h-3.5 w-3.5 text-cyan-300" aria-hidden="true" /> Health checks
                </div>
                <p className="mt-3 text-2xl font-semibold text-slate-100">
                  {statusCount}<span className="ml-1 text-base font-normal text-slate-500">/ {statusTotal}</span>
                </p>
                <p className="mt-2 text-xs text-slate-500">Reported platform, backend, database and AI status</p>
              </div>
              <div className="bg-[#0b1218] p-5">
                <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-slate-500">
                  <Clock3 className="h-3.5 w-3.5 text-cyan-300" aria-hidden="true" /> Uptime
                </div>
                <p className="mt-3 text-2xl font-semibold text-slate-100">{formatUptime(state.platform.uptime_seconds)}</p>
                <p className="mt-2 text-xs text-slate-500">Since platform start</p>
              </div>
            </section>

            <section className="mt-8 grid gap-5 lg:grid-cols-2" aria-label="Service details">
              <article className="border border-white/10 bg-[#0b1218] p-5 sm:p-6">
                <div className="mb-4 flex items-start gap-3">
                  <span className="flex h-9 w-9 items-center justify-center border border-cyan-300/20 bg-cyan-300/5 text-cyan-200">
                    <Database className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <div>
                    <h2 className="text-sm font-semibold text-slate-100">Platform services</h2>
                    <p className="mt-1 text-xs text-slate-500">Availability returned by the backend health report.</p>
                  </div>
                </div>
                <dl>
                  <StatusValue label="Backend" value={state.system_health.backend} healthy={isHealthy(state.system_health.backend)} />
                  <StatusValue label="Database" value={state.system_health.database} healthy={isHealthy(state.system_health.database)} />
                  <StatusValue label="Queue and worker" value={state.system_health.queue} healthy={isHealthy(state.system_health.queue)} />
                </dl>
              </article>

              <article className="border border-white/10 bg-[#0b1218] p-5 sm:p-6">
                <div className="mb-4 flex items-start gap-3">
                  <span className="flex h-9 w-9 items-center justify-center border border-cyan-300/20 bg-cyan-300/5 text-cyan-200">
                    <Cpu className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <div>
                    <h2 className="text-sm font-semibold text-slate-100">AI runtime</h2>
                    <p className="mt-1 text-xs text-slate-500">Provider and capabilities reported by the system.</p>
                  </div>
                </div>
                <dl>
                  <StatusValue label="Runtime" value={state.ai.enabled ? "Enabled" : "Disabled"} healthy={state.ai.enabled} />
                  <div className="flex items-start justify-between gap-4 border-b border-white/10 py-3">
                    <dt className="text-sm text-slate-400">Provider</dt>
                    <dd className="max-w-[65%] truncate text-right text-sm font-medium text-slate-200">{state.ai.provider || "Not reported"}</dd>
                  </div>
                  <div className="border-b border-white/10 py-3">
                    <dt className="mb-2 text-sm text-slate-400">Capabilities</dt>
                    {state.ai.capabilities.length > 0 ? (
                      <dd className="flex flex-wrap gap-2">
                        {state.ai.capabilities.map((capability) => (
                          <span key={capability} className="border border-white/10 px-2 py-1 font-mono text-[10px] text-slate-300">{capability}</span>
                        ))}
                      </dd>
                    ) : (
                      <dd className="text-xs text-slate-500">No capabilities reported</dd>
                    )}
                  </div>
                  <StatusValue label="Silverwing" value={silverwing.status || "Unknown"} healthy={silverwing.healthy} />
                  <div className="flex items-start justify-between gap-4 py-3">
                    <dt className="text-sm text-slate-400">Model</dt>
                    <dd className="max-w-[65%] truncate text-right text-sm font-medium text-slate-200">{silverwing.model || "Not reported"}</dd>
                  </div>
                </dl>
                {silverwing.errors && (
                  <p className="mt-2 border-l-2 border-amber-300/50 pl-3 text-xs leading-5 text-amber-100/75">
                    {silverwing.errors}
                  </p>
                )}
              </article>
            </section>

            <section aria-label="Deployed version" className="mt-8 border border-white/10 bg-[#0b1218] p-5">
              <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-slate-500">Deployment metadata</h2>
              <dl className="mt-3 grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
                <div><dt className="text-slate-500">Version</dt><dd className="mt-1 text-slate-200">{state.version || "Unknown"}</dd></div>
                <div><dt className="text-slate-500">Git SHA</dt><dd className="mt-1 truncate text-slate-200">{state.deployment.git_sha || "Unknown"}</dd></div>
                <div><dt className="text-slate-500">Build time</dt><dd className="mt-1 text-slate-200">{formatTime(state.deployment.build_time)}</dd></div>
                <div><dt className="text-slate-500">Deployment ID</dt><dd className="mt-1 truncate text-slate-200">{state.deployment.deployment_id || "Unknown"}</dd></div>
              </dl>
            </section>

            <footer className="mt-6 flex flex-wrap items-center justify-between gap-2 border-t border-white/10 pt-4 font-mono text-[10px] uppercase tracking-wider text-slate-500">
              <span>Source timestamp: {formatTime(state.timestamp)}</span>
              <span aria-live="polite">{refreshing ? "Refreshing…" : `Last received: ${formatTime(lastUpdated)}`}</span>
            </footer>
          </>
        )}
      </div>
    </main>
  );
}
