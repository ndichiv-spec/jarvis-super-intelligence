'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity, AlertTriangle, ArrowRight, Ban, Check, Clock3, Loader2,
  Play, RefreshCw, ShieldAlert, Workflow, X,
} from 'lucide-react';
import { toast } from 'sonner';
import { apiClient, AuthError } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';

type CommandStatus =
  | 'QUEUED' | 'RECEIVED' | 'UNDERSTANDING' | 'PLANNING' | 'AWAITING_AUTHORIZATION'
  | 'READY' | 'EXECUTING' | 'WAITING' | 'VERIFYING' | 'RECOVERING'
  | 'REPLANNING' | 'COMPLETED' | 'PARTIAL' | 'FAILED' | 'CANCELLED'
  | 'CANCEL_REQUESTED'
  | string;

interface CommandEvent {
  event_id: string;
  timestamp: string;
  event: string;
  [key: string]: unknown;
}

interface CommandRecord {
  command_id: string;
  goal: string;
  status: CommandStatus;
  created_at: number;
  started_at: number | null;
  completed_at: number | null;
  capabilities: string[];
  plan: { task_id?: string; capabilities?: string[] };
  authorization: { required?: boolean; approved?: boolean | null; node_ids?: string[] } | null;
  result: unknown;
  errors: string[];
  events: CommandEvent[];
}

interface CommandMetrics {
  generated_at: string;
  total_commands: number;
  by_status: Record<string, number>;
}

const ACTIVE_STATUSES = new Set([
  'QUEUED', 'RECEIVED', 'UNDERSTANDING', 'PLANNING', 'AWAITING_AUTHORIZATION',
  'READY', 'EXECUTING', 'WAITING', 'VERIFYING', 'RECOVERING', 'REPLANNING',
  'CANCEL_REQUESTED',
]);

const STATUS_TONES: Record<string, string> = {
  COMPLETED: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
  FAILED: 'border-rose-400/30 bg-rose-400/10 text-rose-200',
  PARTIAL: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
  CANCELLED: 'border-slate-400/30 bg-slate-400/10 text-slate-300',
  AWAITING_AUTHORIZATION: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
  EXECUTING: 'border-cyan-400/30 bg-cyan-400/10 text-cyan-200',
  PLANNING: 'border-blue-400/30 bg-blue-400/10 text-blue-200',
};

function formatTime(value?: number | string | null): string {
  if (value === null || value === undefined || value === '') return 'Not reported';
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
  return Number.isNaN(date.getTime()) ? 'Not reported' : date.toLocaleString();
}

function statusTone(status: string): string {
  return STATUS_TONES[status] ?? 'border-white/15 bg-white/[0.04] text-slate-300';
}

function errorText(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'The command service request failed.';
}

export default function CommandsPage() {
  const [commands, setCommands] = useState<CommandRecord[]>([]);
  const [metrics, setMetrics] = useState<CommandMetrics | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [goal, setGoal] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const selected = useMemo(
    () => commands.find((command) => command.command_id === selectedId) ?? null,
    [commands, selectedId],
  );

  const refresh = useCallback(async (background = false) => {
    if (!background) setLoading(true);
    try {
      const [list, counts, eventResponse] = await Promise.all([
        apiClient.get<{ commands: CommandRecord[] }>('/api/v1/commands?limit=100'),
        apiClient.get<CommandMetrics>('/api/v1/commands/metrics'),
        selectedId
          ? apiClient.get<{ events: CommandEvent[] }>(`/api/v1/commands/${selectedId}/events`)
          : Promise.resolve(null),
      ]);
      const updatedCommands = (list.commands ?? []).map((command) => (
        command.command_id === selectedId && eventResponse
          ? { ...command, events: eventResponse.events }
          : command
      ));
      setCommands(updatedCommands);
      setMetrics(counts);
      setSelectedId((current) => (
        current && updatedCommands.some((item) => item.command_id === current)
          ? current
          : updatedCommands[0]?.command_id ?? null
      ));
      setLastUpdated(new Date().toISOString());
      setError(null);
    } catch (cause: unknown) {
      if (!(cause instanceof AuthError)) {
        setError(errorText(cause));
      }
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => void refresh());
    const interval = window.setInterval(() => void refresh(true), 5000);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearInterval(interval);
    };
  }, [refresh]);

  const submitCommand = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const requestGoal = goal.trim();
    if (!requestGoal) return;
    setSubmitting(true);
    try {
      const command = await apiClient.post<CommandRecord>('/api/v1/commands', {
        goal: requestGoal,
        autonomy: 'SUPERVISED',
      });
      setGoal('');
      setSelectedId(command.command_id);
      toast.success('Command accepted by the JARVIS runtime.');
      await refresh(true);
    } catch (cause: unknown) {
      if (!(cause instanceof AuthError)) toast.error(`Command was not accepted: ${errorText(cause)}`);
    } finally {
      setSubmitting(false);
    }
  };

  const decideAuthorization = async (approved: boolean) => {
    if (!selected) return;
    setActionBusy(true);
    try {
      await apiClient.post(`/api/v1/commands/${selected.command_id}/authorization`, {
        approved,
        node_id: selected.authorization?.node_ids?.[0],
      });
      toast[approved ? 'success' : 'info'](
        approved ? 'Authorization granted. The runtime will resume the command.' : 'Authorization rejected.',
      );
      await refresh(true);
    } catch (cause: unknown) {
      if (!(cause instanceof AuthError)) toast.error(`Could not record your decision: ${errorText(cause)}`);
    } finally {
      setActionBusy(false);
    }
  };

  const cancelCommand = async () => {
    if (!selected) return;
    setActionBusy(true);
    try {
      const result = await apiClient.post<{ status: string; cancellation: string }>(
        `/api/v1/commands/${selected.command_id}/cancel`,
        {},
      );
      toast.info(
        result.status === 'CANCELLED'
          ? 'Command cancelled before execution.'
          : 'Cancellation requested; the running step will reach a safe boundary first.',
      );
      await refresh(true);
    } catch (cause: unknown) {
      if (!(cause instanceof AuthError)) toast.error(`Could not cancel command: ${errorText(cause)}`);
    } finally {
      setActionBusy(false);
    }
  };

  const activeCount = commands.filter((item) => ACTIVE_STATUSES.has(item.status)).length;
  const failedCount = metrics?.by_status.FAILED ?? 0;
  const pendingApproval = selected?.status === 'AWAITING_AUTHORIZATION';

  return (
    <main className="min-h-full bg-[#080d12] px-4 py-6 text-slate-100 sm:px-7 lg:px-10">
      <div className="mx-auto max-w-[1500px] space-y-6">
        <header className="flex flex-col justify-between gap-4 border-b border-white/10 pb-5 sm:flex-row sm:items-end">
          <div>
            <p className="mb-2 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-cyan-300">
              <Activity className="h-3.5 w-3.5" aria-hidden="true" /> JARVIS / Command Center
            </p>
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Command Center</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
              Submit supervised work, inspect persisted runtime events, and approve sensitive actions before execution.
            </p>
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <span>{lastUpdated ? `Updated ${new Date(lastUpdated).toLocaleTimeString()}` : 'Waiting for runtime data'}</span>
            <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={loading}>
              <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </Button>
          </div>
        </header>

        {error && (
          <div role="alert" className="flex items-start gap-3 border border-rose-400/30 bg-rose-950/20 p-4 text-sm text-rose-200">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <div>
              <p className="font-medium">Runtime data could not be refreshed.</p>
              <p className="mt-1 text-rose-200/75">{error}</p>
              {commands.length > 0 && <p className="mt-1 text-xs text-rose-200/60">Showing the last successful response.</p>}
            </div>
          </div>
        )}

        <section aria-label="Command runtime metrics" className="grid grid-cols-2 gap-px border border-white/10 bg-white/10 lg:grid-cols-4">
          {[
            { label: 'Commands', value: metrics?.total_commands },
            { label: 'Active', value: activeCount },
            { label: 'Awaiting approval', value: metrics?.by_status.AWAITING_AUTHORIZATION ?? 0 },
            { label: 'Failed', value: failedCount },
          ].map((metric) => (
            <div key={metric.label} className="bg-[#0b1218] p-4 sm:p-5">
              <p className="font-mono text-[10px] uppercase tracking-[0.15em] text-slate-500">{metric.label}</p>
              <p className="mt-2 text-2xl font-semibold tabular-nums">{metric.value ?? (loading ? '…' : 'Unavailable')}</p>
            </div>
          ))}
        </section>

        <section className="grid min-w-0 gap-5 xl:grid-cols-[minmax(17rem,0.8fr)_minmax(0,1.8fr)]">
          <Card className="border-white/10 bg-[#0b1218]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Play className="h-4 w-4 text-cyan-300" aria-hidden="true" /> Submit a command
              </CardTitle>
              <CardDescription>Commands are executed by the authenticated runtime identity in supervised mode.</CardDescription>
            </CardHeader>
            <CardContent>
              <form className="space-y-3" onSubmit={submitCommand}>
                <label htmlFor="command-goal" className="text-xs font-medium text-slate-300">Intent</label>
                <Textarea
                  id="command-goal"
                  value={goal}
                  onChange={(event) => setGoal(event.target.value)}
                  placeholder="Describe the work JARVIS should perform…"
                  maxLength={12000}
                  rows={4}
                  disabled={submitting}
                  className="resize-y border-white/15 bg-black/20 text-sm"
                />
                <Button type="submit" disabled={submitting || !goal.trim()} className="w-full">
                  {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ArrowRight className="mr-2 h-4 w-4" />}
                  Send to runtime
                </Button>
              </form>
              <div className="mt-5 border-t border-white/10 pt-4">
                <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Recent commands</h2>
                {loading && commands.length === 0 ? (
                  <p className="text-sm text-slate-500">Loading command history…</p>
                ) : commands.length === 0 ? (
                  <p className="text-sm text-slate-500">No commands have been recorded for this account.</p>
                ) : (
                  <ul className="max-h-[34rem] space-y-1 overflow-y-auto">
                    {commands.map((command) => (
                      <li key={command.command_id}>
                        <button
                          type="button"
                          onClick={() => setSelectedId(command.command_id)}
                          aria-current={command.command_id === selectedId ? 'true' : undefined}
                          className={`w-full rounded-lg border p-3 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-300 ${
                            command.command_id === selectedId
                              ? 'border-cyan-300/30 bg-cyan-300/[0.07]'
                              : 'border-transparent hover:border-white/10 hover:bg-white/[0.03]'
                          }`}
                        >
                          <span className="flex items-start justify-between gap-3">
                            <span className="line-clamp-2 text-sm text-slate-200">{command.goal}</span>
                            <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] ${statusTone(command.status)}`}>
                              {command.status.replaceAll('_', ' ')}
                            </span>
                          </span>
                          <span className="mt-2 block text-[10px] text-slate-500">{formatTime(command.created_at)}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </CardContent>
          </Card>

          <Card className="min-w-0 border-white/10 bg-[#0b1218]">
            <CardHeader className="border-b border-white/10">
              {selected ? (
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <CardTitle className="break-words text-base">{selected.goal}</CardTitle>
                    <CardDescription className="mt-2 font-mono text-[10px]">
                      {selected.command_id} · created {formatTime(selected.created_at)}
                    </CardDescription>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded-full border px-2.5 py-1 text-xs ${statusTone(selected.status)}`}>
                      {selected.status.replaceAll('_', ' ')}
                    </span>
                    {ACTIVE_STATUSES.has(selected.status) && !pendingApproval && (
                      <Button variant="outline" size="sm" onClick={() => void cancelCommand()} disabled={actionBusy}>
                        <Ban className="mr-2 h-4 w-4" /> Cancel
                      </Button>
                    )}
                  </div>
                </div>
              ) : (
                <>
                  <CardTitle className="text-base">Execution inspection</CardTitle>
                  <CardDescription>Select a recorded command to inspect its plan, events, and result.</CardDescription>
                </>
              )}
            </CardHeader>
            <CardContent className="space-y-6 pt-5">
              {selected ? (
                <>
                  {pendingApproval && (
                    <section aria-label="Authorization request" className="border border-amber-300/30 bg-amber-300/[0.06] p-4">
                      <div className="flex items-start gap-3">
                        <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-200" aria-hidden="true" />
                        <div className="min-w-0 flex-1">
                          <h2 className="text-sm font-semibold text-amber-100">JARVIS needs authorization</h2>
                          <p className="mt-1 text-xs leading-5 text-amber-100/70">
                            Review the proposed capability plan before allowing this command to continue.
                          </p>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {selected.plan?.capabilities?.map((capability) => (
                              <span key={capability} className="rounded border border-amber-200/20 px-2 py-1 font-mono text-[10px] text-amber-100/80">{capability}</span>
                            ))}
                            {(!selected.plan?.capabilities || selected.plan.capabilities.length === 0) && (
                              <span className="text-xs text-amber-100/70">The runtime did not report capability details.</span>
                            )}
                          </div>
                          <div className="mt-4 flex flex-wrap gap-2">
                            <Button size="sm" onClick={() => void decideAuthorization(true)} disabled={actionBusy}>
                              {actionBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Check className="mr-2 h-4 w-4" />}
                              Approve
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => void decideAuthorization(false)} disabled={actionBusy}>
                              <X className="mr-2 h-4 w-4" /> Reject
                            </Button>
                          </div>
                        </div>
                      </div>
                    </section>
                  )}

                  <section aria-labelledby="command-lineage-title">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <div>
                        <h2 id="command-lineage-title" className="flex items-center gap-2 text-sm font-semibold">
                          <Workflow className="h-4 w-4 text-cyan-200" aria-hidden="true" /> Runtime-reported capability plan
                        </h2>
                        <p className="mt-1 text-xs text-slate-500">Plan items are not execution proof; completion is shown only from runtime status.</p>
                      </div>
                      {selected.plan?.task_id && <span className="font-mono text-[10px] text-slate-500">Task {selected.plan.task_id}</span>}
                    </div>
                    {selected.plan?.capabilities?.length ? (
                      <ol className="flex flex-wrap items-center gap-2">
                        {selected.plan.capabilities.map((capability, index) => (
                          <li key={`${capability}-${index}`} className="flex items-center gap-2">
                            <span className="rounded-lg border border-cyan-300/15 bg-cyan-300/[0.05] px-3 py-2 font-mono text-xs text-cyan-100">{capability}</span>
                            {index < selected.plan.capabilities!.length - 1 && <ArrowRight className="h-3.5 w-3.5 text-slate-600" aria-hidden="true" />}
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p className="rounded-lg border border-dashed border-white/10 p-4 text-sm text-slate-500">
                        No capability plan has been reported by the runtime yet.
                      </p>
                    )}
                  </section>

                  <section aria-labelledby="command-events-title">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <h2 id="command-events-title" className="flex items-center gap-2 text-sm font-semibold">
                        <Clock3 className="h-4 w-4 text-cyan-200" aria-hidden="true" /> Persisted runtime events
                      </h2>
                      <span className="text-xs text-slate-500">Polled from the command record</span>
                    </div>
                    {selected.events?.length ? (
                      <ol className="relative space-y-0 border-l border-white/10 pl-5">
                        {selected.events.slice().reverse().map((event) => (
                          <li key={event.event_id} className="relative pb-4 last:pb-0">
                            <span className="absolute -left-[1.58rem] top-1 h-2.5 w-2.5 rounded-full border border-cyan-300/50 bg-[#0b1218]" aria-hidden="true" />
                            <p className="text-sm font-medium text-slate-200">{event.event.replaceAll('_', ' ')}</p>
                            <time className="mt-1 block text-[10px] text-slate-500">{formatTime(event.timestamp)}</time>
                            {Array.isArray(event.capabilities) && (
                              <p className="mt-1 break-words font-mono text-[10px] text-slate-400">
                                {event.capabilities.join(' · ')}
                              </p>
                            )}
                            {typeof event.error === 'string' && (
                              <p className="mt-2 break-words text-xs text-rose-200">{event.error}</p>
                            )}
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p className="rounded-lg border border-dashed border-white/10 p-4 text-sm text-slate-500">
                        The backend has not persisted any command events yet.
                      </p>
                    )}
                  </section>

                  {(selected.errors?.length > 0 || selected.result !== null) && (
                    <section aria-labelledby="command-result-title" className="border-t border-white/10 pt-4">
                      <h2 id="command-result-title" className="mb-3 text-sm font-semibold">Runtime result</h2>
                      {selected.errors?.map((item, index) => (
                        <p key={index} role="alert" className="mb-2 text-sm text-rose-200">{item}</p>
                      ))}
                      {selected.result !== null && (
                        <pre className="max-h-80 overflow-auto rounded-lg border border-white/10 bg-black/30 p-3 text-xs leading-5 text-slate-200">
                          {JSON.stringify(selected.result, null, 2)}
                        </pre>
                      )}
                    </section>
                  )}
                </>
              ) : (
                <div className="flex min-h-64 items-center justify-center text-center">
                  <div>
                    <Activity className="mx-auto h-8 w-8 text-slate-600" aria-hidden="true" />
                    <p className="mt-3 text-sm text-slate-400">No command selected</p>
                    <p className="mt-1 text-xs text-slate-600">Create a command or select one from this account&apos;s runtime history.</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}
