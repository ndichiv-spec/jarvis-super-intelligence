'use client';

import React, { useEffect, useState } from 'react';
import { jarvisAPI, type SystemDashboard, type PlatformIdentity } from '@/lib/api';
import { type SystemCapabilities, type SystemCapability } from '@/types';
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle,
  Database,
  ExternalLink,
  Gauge,
  Globe,
  HardDrive,
  MemoryStick,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  Server,
  Shield,
  Tag,
  Terminal,
  Users,
  Wifi,
  XCircle,
} from 'lucide-react';

type LaunchEvent = {
  ts?: string;
  kind?: string;
  status?: string;
  app?: string;
  args?: string;
  error?: string;
};

const STATUS_ICONS: Record<string, React.ElementType> = {
  online: CheckCircle,
  active: CheckCircle,
  idle: PauseCircle,
  running: PlayCircle,
  offline: XCircle,
  degraded: AlertTriangle,
};

function StatusChip({ label, ok }: { label: string; ok: boolean }) {
  const Icon = ok ? CheckCircle : XCircle;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-[9px] font-medium tracking-wider hud-readout ${
        ok
          ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
          : 'text-rose-400 bg-rose-500/10 border-rose-500/20'
      } border`}
    >
      <Icon className="w-3 h-3" />
      {label}
    </span>
  );
}

function CapabilityChip({ c }: { c: SystemCapability }) {
  const ok = c.availability === 'available';
  const Icon = ok ? CheckCircle : XCircle;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[9px] font-medium tracking-wider hud-readout border ${
        ok
          ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
          : 'text-rose-400 bg-rose-500/10 border-rose-500/20'
      }`}
      title={`${c.category} · tool: ${c.tool} · ${c.provider || 'n/a'}`}
    >
      <Icon className="w-3 h-3" />
      {c.capability}
    </span>
  );
}

function AgentRow({ a }: { a: NonNullable<SystemDashboard['agents']>['entries'][number] }) {
  const Icon = STATUS_ICONS[a.status] || Activity;
  const roleColor =
    a.status === 'active'
      ? 'text-cyan-400'
      : a.status === 'idle'
      ? 'text-sky-400/60'
      : 'text-muted-foreground';
  return (
    <div className="grid grid-cols-12 gap-2 items-center py-1.5 border-b border-cyan-500/10 last:border-0">
      <div className="col-span-4 flex items-center gap-2">
        <Bot className="w-3.5 h-3.5 text-cyan-400/60" />
        <span className={`hud-readout text-xs ${roleColor}`}>{a.name || a.id}</span>
      </div>
      <div className="col-span-3 text-[9px] text-cyan-300/50 hud-readout uppercase">{a.role}</div>
      <div className="col-span-2">
        <span
          className={`inline-flex items-center gap-1 text-[9px] hud-readout ${
            a.status === 'active' ? 'text-emerald-400' : 'text-cyan-300/50'
          }`}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              a.status === 'active' ? 'bg-emerald-400 shadow-[0_0_6px_#00ff88]' : 'bg-cyan-300/40'
            }`}
          />
          {a.status}
        </span>
      </div>
      <div className="col-span-3 text-[9px] text-cyan-300/40 hud-readout truncate">
        {(a.capabilities || []).slice(0, 4).join(', ') || '—'}
      </div>
    </div>
  );
}

export default function SystemMonitor() {
  const [data, setData] = useState<SystemDashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await jarvisAPI.getSystemDashboard();
      setData(d);
    } catch (e: any) {
      setError(e?.message || 'Failed to load JARVIS system state');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [caps, setCaps] = useState<SystemCapabilities | null>(null);
  const loadCapabilities = async () => {
    try {
      setCaps(await jarvisAPI.getCapabilities());
    } catch {
      // best-effort: the dashboard already surfaces provider availability
    }
  };
  useEffect(() => {
    loadCapabilities();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [identity, setIdentity] = useState<PlatformIdentity | null>(null);
  useEffect(() => {
    jarvisAPI.getIdentity().then(setIdentity).catch(() => setIdentity(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ai = data?.providers.ai_enabled ?? false;
  const configured = data?.providers.configured ?? [];

  return (
    <div className="flex flex-col h-full" style={{ background: 'rgba(3, 7, 18, 0.85)' }}>
      {/* HEADER */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-cyan-500/20 holo-titlebar">
        <div className="flex items-center gap-2.5">
          <Gauge className="w-4 h-4 text-cyan-400 drop-shadow-[0_0_6px_rgba(0,212,255,0.5)]" />
          <span className="text-xs font-medium tracking-wider text-holo">JARVIS SYSTEM MONITOR</span>
          <Shield className="w-3 h-3 text-emerald-400/50" />
          <span className="text-[8px] text-emerald-400/50 tracking-wider hud-readout">
            {ai ? 'AI ENABLED' : 'AI OFFLINE'}
          </span>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="flex items-center gap-1.5 text-[10px] text-cyan-300/40 hover:text-cyan-300 transition-colors px-2 py-1 rounded-lg hover:bg-cyan-500/10 tracking-wider hud-readout"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          REFRESH
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar space-y-4">
        {error ? (
          <div className="p-3 rounded-lg hud-panel text-rose-300 text-xs hud-readout">
            {error}
          </div>
        ) : null}

        {/* PLATFORM */}
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 rounded-lg hud-panel">
            <div className="flex items-center gap-1.5 mb-1">
              <Server className="w-3.5 h-3.5 text-cyan-400/50" />
              <span className="text-[9px] text-cyan-300/50 tracking-wider hud-readout">PLATFORM</span>
            </div>
            <div className="text-sm font-medium text-cyan-400 hud-readout flex items-center gap-1.5">
              {data?.platform?.name || 'JARVIS'}
              {identity ? (
                <span
                  className={`inline-flex items-center gap-1 text-[8px] hud-readout ${
                    identity.verification_status === 'verified'
                      ? 'text-emerald-400'
                      : 'text-amber-400'
                  }`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      identity.verification_status === 'verified'
                        ? 'bg-emerald-400 shadow-[0_0_4px_#00ff88]'
                        : 'bg-amber-400/40'
                    }`}
                  />
                  {identity.verification_status.toUpperCase()}
                </span>
              ) : null}
            </div>
            <div className="text-[9px] text-cyan-300/40 hud-readout">
              v{data?.platform?.version} · {data?.platform?.instance_id}
              {identity?.developer_identity ? ` · dev: ${identity.developer_identity}` : ''}
            </div>
          </div>
          <div className="p-3 rounded-lg hud-panel">
            <div className="flex items-center gap-1.5 mb-1">
              <Wifi className="w-3.5 h-3.5 text-cyan-400/50" />
              <span className="text-[9px] text-cyan-300/50 tracking-wider hud-readout">PROVIDERS</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {configured.length === 0 ? (
                <span className="text-[9px] text-cyan-300/40 hud-readout">none configured</span>
              ) : (
                configured.map((p) => (
                  <Tag key={p} className="text-[9px] text-cyan-300/60 hud-readout">
                    {p}
                  </Tag>
                ))
              )}
            </div>
          </div>
        </div>

        {/* SERVICES */}
        <div className="p-3 rounded-lg hud-panel">
          <div className="flex items-center gap-1.5 mb-2">
            <Globe className="w-3.5 h-3.5 text-cyan-400/50" />
            <span className="text-[9px] text-cyan-300/50 tracking-wider hud-readout">
              SERVICES ({(data?.services || []).length})
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {(data?.services || []).map((s) => (
              <StatusChip key={s} label={s} ok={true} />
            ))}
          </div>
        </div>

        {/* AGENTS */}
        <div className="p-3 rounded-lg hud-panel">
          <div className="flex items-center justify-between gap-1.5 mb-2">
            <div className="flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5 text-cyan-400/50" />
              <span className="text-[9px] text-cyan-300/50 tracking-wider hud-readout">AGENTS</span>
            </div>
            <span className="text-[9px] text-cyan-300/40 hud-readout">
              {data?.agents?.total ?? 0} total · {data?.agents?.active ?? 0} active ·{' '}
              {data?.agents?.idle ?? 0} idle
            </span>
          </div>
          <div className="space-y-0 text-sm">
            {(data?.agents?.entries || []).length === 0 ? (
              <span className="text-[9px] text-cyan-300/40 hud-readout">no agents registered</span>
            ) : (
              (data?.agents?.entries || []).map((a) => <AgentRow key={a.id} a={a} />)
            )}
          </div>
        </div>

        {/* AUTOMATION + CAPABILITIES */}
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 rounded-lg hud-panel">
            <div className="flex items-center gap-1.5 mb-2">
              <Terminal className="w-3.5 h-3.5 text-cyan-400/50" />
              <span className="text-[9px] text-cyan-300/50 tracking-wider hud-readout">AUTOMATION</span>
            </div>
            <div className="text-sm font-medium text-cyan-400 hud-readout">
              {data?.automation?.tasks ?? 0} tasks
            </div>
            <div className="text-[9px] text-cyan-300/40 hud-readout">
              engine: {data?.automation?.engine || '—'}{' '}
              · scheduler {data?.automation?.scheduler_running ? 'running' : 'idle'}
            </div>
          </div>
          <div className="p-3 rounded-lg hud-panel">
            <div className="flex items-center justify-between gap-1.5 mb-2">
              <div className="flex items-center gap-1.5">
                <Database className="w-3.5 h-3.5 text-cyan-400/50" />
                <span className="text-[9px] text-cyan-300/50 tracking-wider hud-readout">CAPABILITIES</span>
              </div>
              {caps ? (
                <span className="text-[9px] text-cyan-300/40 hud-readout">
                  {(caps.registry || []).filter((c) => c.availability === 'available').length}/{(caps.registry || []).length} online
                </span>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {caps === null ? (
                <span className="text-[9px] text-cyan-300/40 hud-readout">discovering…</span>
              ) : !(caps?.registry && caps.registry.length) ? (
                <span className="text-[9px] text-cyan-300/40 hud-readout">no registry</span>
              ) : (
                (caps.registry || []).map((c) => <CapabilityChip key={c.capability} c={c} />)
              )}
            </div>
          </div>
        </div>

        {/* RESOURCE PRESSURE */}
        <div className="p-3 rounded-lg hud-panel">
          <div className="flex items-center gap-1.5 mb-1">
            <MemoryStick className="w-3.5 h-3.5 text-cyan-400/50" />
            <span className="text-[9px] text-cyan-300/50 tracking-wider hud-readout">RESOURCE PRESSURE</span>
          </div>
          <div className="text-sm font-medium text-cyan-400 hud-readout">
            {(data?.resource_pressure || 'unknown').toUpperCase()}
          </div>
          <div className="text-[9px] text-cyan-300/40 hud-readout">
            Platform-managed — host metrics are intentionally not surfaced here.
          </div>
        </div>

        {/* RECENT SYSTEM ACTIONS (audit trail incl. launch denials) */}
        <div className="p-3 rounded-lg hud-panel">
          <div className="flex items-center gap-1.5 mb-2">
            <HardDrive className="w-3.5 h-3.5 text-cyan-400/50" />
            <span className="text-[9px] text-cyan-300/50 tracking-wider hud-readout">
              RECENT SYSTEM ACTIONS (spec §27 audit)
            </span>
          </div>
          {(data?.recent_actions || []).length === 0 ? (
            <span className="text-[9px] text-cyan-300/40 hud-readout">no recent actions</span>
          ) : (
            <div className="space-y-1">
              {(data?.recent_actions || []).map((e: LaunchEvent, i) => (
                <div
                  key={`${e.ts}-${i}`}
                  className="grid grid-cols-12 gap-2 text-[9px] text-cyan-300/50 hud-readout"
                >
                  <span className="col-span-3 text-cyan-300/40">{e.ts || '—'}</span>
                  <span
                    className={`col-span-2 font-medium ${
                      e.status === 'denied'
                        ? 'text-rose-400'
                        : e.status === 'error'
                        ? 'text-amber-400'
                        : 'text-emerald-400'
                    }`}
                  >
                    {e.status || '—'}
                  </span>
                  <span className="col-span-4 truncate">{(e.app || '') + (e.args ? ' ' + e.args : '')}</span>
                  {e.error ? (
                    <span className="col-span-3 text-rose-400/70 truncate" title={e.error}>
                      {e.error}
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between px-3 py-1.5 border-t border-cyan-500/20 holo-titlebar">
        <span className="text-[8px] text-cyan-300/30 hud-readout">
          updated {data?.timestamp ? new Date(data.timestamp).toLocaleTimeString() : '—'}
        </span>
        <ExternalLink className="w-3 h-3 text-cyan-300/20" />
      </div>
    </div>
  );
}
