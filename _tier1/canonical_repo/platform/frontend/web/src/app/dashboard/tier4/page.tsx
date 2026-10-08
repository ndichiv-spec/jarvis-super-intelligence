'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Activity, AlertTriangle, ArrowUpRight, Clock3,
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

interface HostMetrics {
  available?: boolean;
  reason?: string;
  timestamp?: string;
  cpu_percent?: number;
  memory?: { percent?: number; used?: number; total?: number };
  disk?: number;
  processes?: number;
}

interface DashboardData {
  commands: CommandRecord[];
  hostMetrics: HostMetrics;
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
      apiClient.get<HostMetrics>('/api/v1/monitoring/metrics'),
    ]);
    const failures: string[] = [];
    const [commandResult, hostMetricsResult] = results;

    if (results.some((result) => result.status === 'rejected' && result.reason instanceof AuthError)) {
      setErrors(['Authentication is required to load this dashboard.']);
      setLoading(false);
      return;
    }

    const commands = commandResult.status === 'fulfilled'
      ? commandResult.value.commands ?? []
      : (failures.push(`Command history: ${readableError(commandResult.reason)}`), undefined);
    const hostMetrics = hostMetricsResult.status === 'fulfilled'
      ? hostMetricsResult.value
      : (failures.push(`Host metrics: ${readableError(hostMetricsResult.reason)}`), undefined);

    if (commands && hostMetrics) {
      setData({ commands, hostMetrics });
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

  const activeCommands = data?.commands.filter((command) => (
    ['RECEIVED', 'UNDERSTANDING', 'PLANNING', 'AWAITING_AUTHORIZATION', 'READY', 'EXECUTING', 'WAITING', 'VERIFYING', 'RECOVERING', 'REPLANNING']
      .includes(command.status)
  )).length ?? 0;

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
        <MetricCard label="Recent commands" value={data ? String(data.commands.length) : '—'} detail="Most recent persisted records (up to 100)" icon={Activity} />
        <MetricCard label="Active commands" value={data ? String(activeCommands) : '—'} detail="Includes running, waiting, and authorization states" icon={Clock3} />
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
            {data?.hostMetrics.available === false && (
              <p role="status" className="text-sm text-amber-200">
                {data.hostMetrics.reason ?? 'Host metrics are unavailable.'}
              </p>
            )}
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
              <CardDescription>The backend does not expose an account-scoped connection metadata endpoint in this deployment.</CardDescription>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link href="/dashboard/connections">Manage <ArrowUpRight className="ml-2 h-4 w-4" /></Link>
            </Button>
          </CardHeader>
          <CardContent className="flex items-center gap-3">
            <Badge variant="outline">Unavailable</Badge>
            <p className="text-sm text-muted-foreground">This overview cannot verify account grants; use the Connections page for service-specific state.</p>
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
