'use client';

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { commandsApi, type CommandRecord } from '@/features/runtime/commands-api';

const TERMINAL_STATUSES = new Set(['COMPLETED', 'PARTIAL', 'FAILED', 'CANCELLED']);
const POLL_INTERVAL_MS = 3000;
const MAX_POLL_ATTEMPTS = 100;

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'The command request could not be completed.';
}

function formatValue(value: unknown): string {
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function timestamp(value: unknown): string | null {
  if (typeof value !== 'number' && typeof value !== 'string') return null;
  const date = typeof value === 'number'
    ? new Date(value > 1e12 ? value : value * 1000)
    : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toLocaleString();
}

function isTerminal(command: CommandRecord): boolean {
  return TERMINAL_STATUSES.has(command.status.toUpperCase());
}

export function WorldTaskPanel({
  conversationId,
  authenticated,
}: {
  conversationId?: string | null;
  authenticated: boolean;
}) {
  const [goal, setGoal] = useState('');
  const [commands, setCommands] = useState<CommandRecord[]>([]);
  const [loading, setLoading] = useState(authenticated);
  const [submitting, setSubmitting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [pollingPaused, setPollingPaused] = useState(false);
  const [pollReset, setPollReset] = useState(0);
  const mounted = useRef(true);
  const inFlight = useRef(false);
  const requestId = useRef<string | null>(null);
  const currentCommands = useRef(commands);
  currentCommands.current = commands;

  const activeIds = useMemo(
    () => commands.filter((command) => !isTerminal(command)).map((command) => command.command_id).join(','),
    [commands],
  );
  const hasActiveCommands = activeIds.length > 0;

  const refresh = useCallback(async (manual = false) => {
    if (!authenticated || inFlight.current) return;
    inFlight.current = true;
    if (manual && mounted.current) setRefreshing(true);
    try {
      const records = await commandsApi.list();
      if (mounted.current) {
        setCommands(records);
        setError(null);
        setHistoryLoaded(true);
        setPollingPaused(false);
      }
    } catch (refreshError) {
      if (mounted.current) setError(errorMessage(refreshError));
    } finally {
      inFlight.current = false;
      if (mounted.current && manual) setRefreshing(false);
    }
  }, [authenticated]);

  useEffect(() => {
    mounted.current = true;
    if (authenticated) {
      setLoading(true);
      void refresh().finally(() => {
        if (mounted.current) setLoading(false);
      });
    } else {
      setLoading(false);
    }
    return () => {
      mounted.current = false;
    };
  }, [authenticated, refresh]);

  useEffect(() => {
    if (!authenticated || !hasActiveCommands || pollingPaused) return;
    let attempts = 0;
    const interval = window.setInterval(() => {
      attempts += 1;
      if (attempts >= MAX_POLL_ATTEMPTS) {
        window.clearInterval(interval);
        setPollingPaused(true);
        return;
      }
      if (!inFlight.current) void refresh();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [authenticated, hasActiveCommands, pollingPaused, pollReset, refresh]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanGoal = goal.trim();
    if (!authenticated || !cleanGoal || submitting) return;
    setSubmitting(true);
    setError(null);
    requestId.current ??= typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `command-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    try {
      const record = await commandsApi.submit({
        goal: cleanGoal,
        ...(conversationId ? { conversation_id: conversationId } : {}),
        request_id: requestId.current,
      });
      if (!record.command_id) throw new Error('JARVIS did not return a durable command ID.');
      if (mounted.current) {
        setCommands((previous) => [
          record,
          ...previous.filter((item) => item.command_id !== record.command_id),
        ].slice(0, 50));
        setGoal('');
        setHistoryLoaded(true);
      }
      requestId.current = null;
    } catch (submitError) {
      if (mounted.current) setError(errorMessage(submitError));
    } finally {
      if (mounted.current) setSubmitting(false);
    }
  }

  async function decide(commandId: string, nodeId: string, approved: boolean) {
    const key = `${commandId}:${nodeId}`;
    if (busyAction) return;
    setBusyAction(key);
    setError(null);
    try {
      const record = await commandsApi.authorize(commandId, nodeId, approved);
      if (mounted.current) {
        setCommands((previous) => previous.map((item) => item.command_id === record.command_id ? record : item));
      }
    } catch (decisionError) {
      if (mounted.current) setError(errorMessage(decisionError));
    } finally {
      if (mounted.current) setBusyAction(null);
    }
  }

  function retryPolling() {
    setPollingPaused(false);
    setPollReset((value) => value + 1);
    void refresh(true);
  }

  return (
    <section
      aria-label="World workspace task execution"
      className="shrink-0 border-b border-cyan-300/10 bg-[#09111b] px-4 py-4 sm:px-7"
    >
      <div className="mx-auto max-h-[45vh] max-w-5xl space-y-4 overflow-y-auto pr-1">
        <header>
          <h3 className="text-sm font-semibold text-slate-100">Submit a task to JARVIS</h3>
          <p className="mt-1 text-xs text-slate-400">
            This explicit action creates a durable command. It does not change how chat messages are handled.
          </p>
        </header>

        {!authenticated ? (
          <p role="status" className="text-sm text-amber-200">Sign in to submit or view your tasks.</p>
        ) : (
          <>
            <form onSubmit={submit} className="space-y-2">
              <label htmlFor="world-task-goal" className="block text-xs font-medium text-slate-300">
                What would you like JARVIS to do?
              </label>
              <textarea
                id="world-task-goal"
                name="goal"
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                required
                rows={3}
                maxLength={4000}
                placeholder="Describe one task in plain language"
                className="w-full resize-y rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500"
              />
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-[11px] text-slate-500">
                  JARVIS reports the command plan, authorization needs, results, and errors returned by its runtime.
                </p>
                <button
                  type="submit"
                  disabled={submitting || !goal.trim()}
                  className="rounded-lg border border-cyan-200/25 bg-cyan-300/10 px-3 py-2 text-xs font-semibold text-cyan-100 hover:bg-cyan-300/15 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {submitting ? 'Submitting…' : 'Submit task'}
                </button>
              </div>
            </form>

            <div className="flex items-center justify-between gap-3 border-t border-white/[0.07] pt-3">
              <h4 className="text-xs font-semibold text-slate-200">Your recent commands</h4>
              <button
                type="button"
                onClick={retryPolling}
                disabled={refreshing || loading}
                className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-slate-300 hover:bg-white/[0.05] disabled:opacity-50"
              >
                <RefreshCw aria-hidden="true" className={`h-3 w-3 ${refreshing ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>

            {error && <p role="alert" className="rounded-md border border-rose-300/20 bg-rose-300/5 p-2 text-xs text-rose-200">{error}</p>}
            {loading ? (
              <p role="status" className="text-xs text-slate-400">Loading command history…</p>
            ) : !historyLoaded || commands.length === 0 ? (
              <p className="text-xs text-slate-400">No command history is available yet.</p>
            ) : (
              <ul className="space-y-3">
                {commands.map((command) => {
                  const pendingNodeIds = command.status === 'AWAITING_AUTHORIZATION'
                    ? (command.authorization?.node_ids ?? [])
                    : [];
                  return (
                    <li key={command.command_id} className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-3">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="whitespace-pre-wrap break-words text-sm text-slate-100">{command.goal || 'Task goal unavailable'}</p>
                          <p className="mt-1 font-mono text-[10px] text-slate-500">
                            Command {command.command_id}
                            {command.task_id ? ` · Task ${command.task_id}` : ''}
                          </p>
                        </div>
                        <span className="shrink-0 rounded-full border border-white/10 px-2 py-1 text-[10px] font-semibold text-slate-200">
                          {command.status}
                        </span>
                      </div>

                      {pendingNodeIds.length > 0 && (
                        <div className="mt-3 rounded-md border border-amber-200/15 bg-amber-200/[0.04] p-2">
                          <p className="text-xs font-medium text-amber-100">Authorization is required for these pending plan nodes.</p>
                          <ul className="mt-2 space-y-2">
                            {pendingNodeIds.map((nodeId) => {
                              const isBusy = busyAction === `${command.command_id}:${nodeId}`;
                              return (
                                <li key={nodeId} className="flex flex-wrap items-center justify-between gap-2">
                                  <code className="break-all text-[11px] text-slate-200">{nodeId}</code>
                                  <div className="flex gap-2">
                                    <button
                                      type="button"
                                      onClick={() => void decide(command.command_id, nodeId, true)}
                                      disabled={Boolean(busyAction) || command.status !== 'AWAITING_AUTHORIZATION'}
                                      className="rounded border border-emerald-200/20 px-2 py-1 text-[11px] text-emerald-100 disabled:opacity-50"
                                    >
                                      {isBusy ? 'Saving…' : 'Approve'}
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => void decide(command.command_id, nodeId, false)}
                                      disabled={Boolean(busyAction) || command.status !== 'AWAITING_AUTHORIZATION'}
                                      className="rounded border border-rose-200/20 px-2 py-1 text-[11px] text-rose-100 disabled:opacity-50"
                                    >
                                      Reject
                                    </button>
                                  </div>
                                </li>
                              );
                            })}
                          </ul>
                        </div>
                      )}

                      <details className="mt-3">
                        <summary className="cursor-pointer text-xs text-cyan-100/80">Plan, result, errors &amp; provenance</summary>
                        <dl className="mt-2 space-y-2 text-xs">
                          {command.plan !== undefined && command.plan !== null && (
                            <div>
                              <dt className="font-medium text-slate-300">Plan</dt>
                              <dd><pre className="mt-1 max-h-36 overflow-auto whitespace-pre-wrap break-words rounded bg-black/20 p-2 text-[10px] text-slate-400">{formatValue(command.plan)}</pre></dd>
                            </div>
                          )}
                          {command.result !== undefined && command.result !== null && (
                            <div>
                              <dt className="font-medium text-slate-300">Result reported by JARVIS</dt>
                              <dd><pre className="mt-1 max-h-36 overflow-auto whitespace-pre-wrap break-words rounded bg-black/20 p-2 text-[10px] text-slate-300">{formatValue(command.result)}</pre></dd>
                            </div>
                          )}
                          {!!command.errors?.length && (
                            <div>
                              <dt className="font-medium text-rose-200">Errors</dt>
                              <dd className="mt-1 space-y-1 text-rose-200">{command.errors.map((item, index) => <p key={index}>{formatValue(item)}</p>)}</dd>
                            </div>
                          )}
                          <div>
                            <dt className="font-medium text-slate-300">Execution history</dt>
                            {!command.events?.length ? (
                              <dd className="mt-1 text-slate-500">No command events have been reported.</dd>
                            ) : (
                              <dd>
                                <ol className="mt-1 space-y-1 text-slate-400">
                                  {command.events.map((item, index) => (
                                    <li key={`${item.sequence ?? index}-${item.event ?? 'event'}`}>
                                      {item.event || 'Command event'}
                                      {timestamp(item.timestamp) ? ` · ${timestamp(item.timestamp)}` : ''}
                                    </li>
                                  ))}
                                </ol>
                              </dd>
                            )}
                          </div>
                          <div className="text-[10px] text-slate-500">
                            {[
                              command.request_id ? `Request ${command.request_id}` : null,
                              command.conversation_id ? `Conversation ${command.conversation_id}` : null,
                              timestamp(command.created_at) ? `Created ${timestamp(command.created_at)}` : null,
                              timestamp(command.completed_at) ? `Finished ${timestamp(command.completed_at)}` : null,
                            ].filter(Boolean).join(' · ') || 'No additional provenance was reported.'}
                          </div>
                        </dl>
                      </details>
                    </li>
                  );
                })}
              </ul>
            )}
            {hasActiveCommands && (
              <p role="status" className="text-[11px] text-slate-500">
                {pollingPaused
                  ? 'Automatic updates paused after five minutes. Refresh to check the durable command record.'
                  : 'Refreshing active command records periodically. Their current state is shown above.'}
              </p>
            )}
          </>
        )}
      </div>
    </section>
  );
}
