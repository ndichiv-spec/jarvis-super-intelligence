'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Activity, AlertTriangle, ArrowUpRight, CheckCircle2, Clock3,
  Cpu, Database, GitBranch, RefreshCw, Shield, Workflow,
} from 'lucide-react';
import { ApiClientError, AuthError, apiClient } from '@/lib/api-client';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

interface CommandRecord {
  command_id: string;
  goal: string;
  status: string;
  created_at: number;
}

interface CommandMetrics {
  generated_at: string;
  total_commands: number;
  by_status: Record<string, number>;
}

interface HostMetrics {
  timestamp?: string;
  cpu_percent?: number;
  memory?: { percent?: number; used?: number; total?: number };
  disk?: number;
  processes?: number;
}

interface ServiceConnection {
  id: string;
  provider: string;
  connected: boolean;
  status: string;
  account: string | null;
  capabilities: string[];
  health: string;
}

interface DashboardData {
  commands: CommandRecord[];
  commandMetrics: CommandMetrics;
  hostMetrics: HostMetrics;
  connections: ServiceConnection[];
}

const unavailableModules = [
  { label: 'Organizations & workspaces', icon: GitBranch },
  { label: 'Security audit & policy', icon: Shield },
  { label: 'Workflow history', icon: Workflow },
  { label: 'Backup & deployment control', icon: Database },
];

function formatTime(value: string | number | undefined): string {
  if (value === undefined) return 'Not reported';
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
  return Number.isNaN(date.getTime()) ? 'Not reported' : date.toLocaleString();
}

function readableError(error: unknown): string {
  if (error instanceof ApiClientError) return error.message;
  return error instanceof Error ? error.message : 'Request failed';
}

function metric(value: number | undefined, suffix = ''): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(1)}${suffix}` : 'Unavailable';
}

export default function Tier4Page() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshedAt, setRefreshedAt] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    const results = await Promise.allSettled([
      apiClient.get<{ commands: CommandRecord[] }>('/api/v1/commands?limit=100'),
      apiClient.get<CommandMetrics>('/api/v1/commands/metrics'),
      apiClient.get<HostMetrics>('/api/v1/monitoring/metrics'),
      apiClient.get<{ connections: ServiceConnection[] }>('/api/v1/extensions/connections'),
    ]);
    const failures: string[] = [];
    const [commandResult, commandMetricsResult, hostMetricsResult, connectionResult] = results;

    if (results.some((result) => result.status === 'rejected' && result.reason instanceof AuthError)) {
      setErrors(['Authentication is required to load this dashboard.']);
      setLoading(false);
      return;
    }

    const commands = commandResult.status === 'fulfilled'
      ? commandResult.value.commands ?? []
      : (failures.push(`Command history: ${readableError(commandResult.reason)}`), undefined);
    const commandMetrics = commandMetricsResult.status === 'fulfilled'
      ? commandMetricsResult.value
      : (failures.push(`Command metrics: ${readableError(commandMetricsResult.reason)}`), undefined);
    const hostMetrics = hostMetricsResult.status === 'fulfilled'
      ? hostMetricsResult.value
      : (failures.push(`Host metrics: ${readableError(hostMetricsResult.reason)}`), undefined);
    const connections = connectionResult.status === 'fulfilled'
      ? connectionResult.value.connections ?? []
      : (failures.push(`Connections: ${readableError(connectionResult.reason)}`), undefined);

    if (commandMetrics && hostMetrics) {
      setData((current) => ({
        commands: commands ?? current?.commands ?? [],
        commandMetrics,
        hostMetrics,
        connections: connections ?? current?.connections ?? [],
      }));
      if (failures.length === 0) setRefreshedAt(new Date().toISOString());
    }
    setErrors(failures);
    setLoading(false);
  }, []);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => void refresh());
    const timer = window.setInterval(() => void refresh(), 15_000);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearInterval(timer);
    };
  }, [refresh]);

  const counts = data?.commandMetrics.by_status ?? {};
  const activeCommands = Object.entries(counts)
    .filter(([status]) => ['RECEIVED', 'UNDERSTANDING', 'PLANNING', 'AWAITING_AUTHORIZATION', 'READY', 'EXECUTING', 'WAITING', 'VERIFYING', 'RECOVERING', 'REPLANNING'].includes(status))
    .reduce((sum, [, count]) => sum + count, 0);
  const connectedCount = data?.connections.filter((connection) => connection.connected).length ?? 0;

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6 p-4 sm:p-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-300">JARVIS / Operations</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">Runtime overview</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Live command, host, and authorized-connection state. Values are shown only when returned by the backend.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            {refreshedAt ? `Updated ${formatTime(refreshedAt)}` : 'Waiting for backend'}
          </span>
          <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={loading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </header>

      {errors.length > 0 && (
        <div role="alert" className="flex gap-3 rounded-lg border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-100">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium">Some runtime data could not be refreshed.</p>
            {errors.map((error) => <p key={error} className="mt-1 text-amber-100/75">{error}</p>)}
            {data && <p className="mt-2 text-xs text-amber-100/60">Previously loaded values remain visible with their last update time.</p>}
          </div>
        </div>
      )}

      <section aria-label="Runtime metrics" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Commands" value={data ? String(data.commandMetrics.total_commands) : '—'} detail="Persisted commands for your account" icon={Activity} />
        <MetricCard label="Active commands" value={data ? String(activeCommands) : '—'} detail="Includes running, waiting, and authorization states" icon={Clock3} />
        <MetricCard label="Connected services" value={data ? `${connectedCount} / ${data.connections.length}` : '—'} detail="Account-scoped authorization metadata" icon={GitBranch} />
        <MetricCard label="CPU" value={data ? metric(data.hostMetrics.cpu_percent, '%') : '—'} detail="Current host sample" icon={Cpu} />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <Card className="border-white/10 bg-card/70">
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div>
              <CardTitle>Recent commands</CardTitle>
              <CardDescription>Persistent runtime records; open the command center to inspect events and decisions.</CardDescription>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link href="/dashboard/commands">Command center <ArrowUpRight className="ml-2 h-4 w-4" /></Link>
            </Button>
          </CardHeader>
          <CardContent>
            {!data && loading ? (
              <p className="py-8 text-center text-sm text-muted-foreground">Loading command state…</p>
            ) : !data || data.commands.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">No persisted commands are available.</p>
            ) : (
              <div className="divide-y divide-white/5">
                {data.commands.slice(0, 6).map((command) => (
                  <div key={command.command_id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{command.goal}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{formatTime(command.created_at)}</p>
                    </div>
                    <Badge variant="outline" className="w-fit">{command.status}</Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-white/10 bg-card/70">
          <CardHeader>
            <CardTitle>Host resources</CardTitle>
            <CardDescription>Most recent sample reported by the monitoring API.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <ResourceRow label="Memory" value={metric(data?.hostMetrics.memory?.percent, '%')} />
            <ResourceRow label="Disk" value={metric(data?.hostMetrics.disk, '%')} />
            <ResourceRow label="Processes" value={typeof data?.hostMetrics.processes === 'number' ? String(data.hostMetrics.processes) : 'Unavailable'} />
            <p className="border-t border-white/5 pt-3 text-xs text-muted-foreground">
              Sample time: {formatTime(data?.hostMetrics.timestamp)}
            </p>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <Card className="border-white/10 bg-card/70">
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div>
              <CardTitle>Service connections</CardTitle>
              <CardDescription>Only safe connection metadata is displayed; credentials remain server-side.</CardDescription>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link href="/dashboard/connections">Manage <ArrowUpRight className="ml-2 h-4 w-4" /></Link>
            </Button>
          </CardHeader>
          <CardContent>
            {!data && loading ? (
              <p className="py-6 text-sm text-muted-foreground">Loading connection state…</p>
            ) : data?.connections.length ? (
              <div className="space-y-3">
                {data.connections.map((connection) => (
                  <div key={connection.id} className="flex items-center justify-between gap-3 rounded-lg border border-white/5 p-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{connection.provider}</p>
                      <p className="mt-1 truncate text-xs text-muted-foreground">
                        {connection.account ?? connection.status} · {connection.capabilities.length} advertised capabilities
                      </p>
                    </div>
                    <Badge variant="outline" className={connection.connected ? 'border-emerald-400/30 text-emerald-200' : ''}>
                      {connection.connected ? <CheckCircle2 className="mr-1 h-3 w-3" /> : null}
                      {connection.connected ? connection.health : connection.status}
                    </Badge>
                  </div>
                ))}
              </div>
            ) : (
              <p className="py-6 text-sm text-muted-foreground">No configured service connections were returned.</p>
            )}
          </CardContent>
        </Card>

        <Card className="border-dashed border-white/15 bg-transparent">
          <CardHeader>
            <CardTitle>Enterprise controls not connected</CardTitle>
            <CardDescription>
              These modules are not represented as operational because this deployment does not expose authoritative APIs for them.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            {unavailableModules.map(({ label, icon: Icon }) => (
              <div key={label} className="flex items-center gap-3 rounded-lg border border-white/5 p-3 text-sm text-muted-foreground">
                <Icon className="h-4 w-4 shrink-0" />
                <span>{label}</span>
                <Badge variant="outline" className="ml-auto">Unavailable</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>
    </main>
  );
}

function MetricCard({ label, value, detail, icon: Icon }: {
  label: string;
  value: string;
  detail: string;
  icon: typeof Activity;
}) {
  return (
    <Card className="border-white/10 bg-card/70">
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm text-muted-foreground">{label}</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums">{value}</p>
          </div>
          <Icon aria-hidden="true" className="h-5 w-5 text-cyan-300" />
        </div>
        <p className="mt-3 text-xs text-muted-foreground">{detail}</p>
      </CardContent>
    </Card>
  );
}

function ResourceRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-white/5 pb-3 text-sm last:border-0 last:pb-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono tabular-nums">{value}</span>
    </div>
  );
}
