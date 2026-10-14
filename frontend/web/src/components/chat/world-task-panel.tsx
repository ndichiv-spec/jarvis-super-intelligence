'use client';

import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { AlertCircle, CheckCircle2, Loader2, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { worldWorkspaceApi, type WorldCommand } from '@/features/commands/api';

interface WorldTaskPanelProps {
  conversationId: string | null;
  authenticated: boolean;
}

const ACTIVE_STATUSES = new Set([
  'QUEUED', 'RECEIVED', 'UNDERSTANDING', 'PLANNING', 'READY', 'EXECUTING',
  'WAITING', 'VERIFYING', 'RECOVERING', 'REPLANNING', 'CANCEL_REQUESTED',
]);

const STATUS_LABELS: Record<string, string> = {
  QUEUED: 'Queued',
  RECEIVED: 'Received',
  UNDERSTANDING: 'Understanding request',
  PLANNING: 'Planning',
  AWAITING_AUTHORIZATION: 'Waiting for your approval',
  READY: 'Ready to execute',
  EXECUTING: 'Executing',
  WAITING: 'Waiting for a service',
  VERIFYING: 'Verifying result',
  RECOVERING: 'Recovering',
  REPLANNING: 'Updating plan',
  COMPLETED: 'Completed',
  PARTIAL: 'Partially completed',
  FAILED: 'Failed',
  CANCELLED: 'Cancelled',
  CANCEL_REQUESTED: 'Stopping safely',
};

function describeResult(result: Record<string, unknown> | null | undefined): string | null {
  if (!result) return null;
  for (const key of ['summary', 'answer', 'output', 'message']) {
    const value = result[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return null;
}

export function WorldTaskPanel({ conversationId, authenticated }: WorldTaskPanelProps) {
  const [goal, setGoal] = useState('');
  const [command, setCommand] = useState<WorldCommand | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [authorizing, setAuthorizing] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState('');
  const [error, setError] = useState<string | null>(null);

  const pendingNodeIds = useMemo(() => {
    const authorization = command?.authorization;
    const approved = new Set(authorization?.approved_node_ids ?? []);
    return (authorization?.node_ids ?? []).filter((nodeId) => !approved.has(nodeId));
  }, [command?.authorization]);
  const actionByNode = useMemo(
    () => new Map((command?.authorization?.actions ?? []).map((action) => [action.node_id, action])),
    [command?.authorization?.actions],
  );

  useEffect(() => {
    if (!command?.command_id || !ACTIVE_STATUSES.has(command.status)) return;

    let disposed = false;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const refresh = async () => {
      try {
        const latest = await worldWorkspaceApi.get(command.command_id);
        if (!disposed) {
          setCommand(latest);
          setError(null);
        }
      } catch {
        if (!disposed) setError('Task status could not be refreshed. The last saved status is still shown.');
      }
      if (!disposed) timeout = setTimeout(refresh, 2000);
    };

    timeout = setTimeout(refresh, 1200);
    return () => {
      disposed = true;
      if (timeout) clearTimeout(timeout);
    };
  }, [command?.command_id, command?.status]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const request = goal.trim();
    if (!authenticated || !request || submitting) return;
    setSubmitting(true);
    setError(null);
    setCommand(null);
    try {
      const requestId = globalThis.crypto?.randomUUID?.()
        ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const created = await worldWorkspaceApi.submit(request, conversationId, requestId);
      setCommand(created);
      setGoal('');
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'The task could not be submitted.');
    } finally {
      setSubmitting(false);
    }
  }

  async function decideAuthorization(approved: boolean) {
    const currentSelection = selectedNodeId && pendingNodeIds.includes(selectedNodeId)
      ? selectedNodeId
      : undefined;
    if (!command || authorizing || (approved && pendingNodeIds.length !== 1 && !currentSelection)) return;
    const nodeId = currentSelection || (pendingNodeIds.length === 1 ? pendingNodeIds[0] : undefined);
    setAuthorizing(true);
    setError(null);
    try {
      const updated = await worldWorkspaceApi.authorize(command.command_id, approved, nodeId);
      setCommand(updated);
    } catch (decisionError) {
      setError(decisionError instanceof Error ? decisionError.message : 'Your authorization decision could not be saved.');
    } finally {
      setAuthorizing(false);
    }
  }

  const status = command?.status?.toUpperCase();
  const isTerminal = status ? !ACTIVE_STATUSES.has(status) && status !== 'AWAITING_AUTHORIZATION' : false;
  const resultText = describeResult(command?.result);

  return (
    <section
      aria-label="World workspace task execution"
      className="border-b border-white/[0.07] bg-[#0b121d] px-4 py-4 sm:px-7"
    >
      <div className="mx-auto max-w-4xl">
        <div className="mb-3 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-100">World workspace</h3>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-400">
              Describe the outcome you want. JARVIS will plan through its authorized runtime and report the saved task status.
            </p>
          </div>
          {command && (
            <span className="shrink-0 rounded-full border border-white/10 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wide text-slate-300">
              {STATUS_LABELS[status ?? ''] ?? status ?? 'Status unavailable'}
            </span>
          )}
        </div>

        {!authenticated ? (
          <p className="rounded-lg border border-amber-200/15 bg-amber-200/[0.04] p-3 text-sm text-amber-100/80">
            Sign in with an authorized JARVIS account to submit or inspect tasks.
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-2">
            <label htmlFor="world-task-goal" className="sr-only">Describe the task for JARVIS</label>
            <Textarea
              id="world-task-goal"
              value={goal}
              onChange={(event) => setGoal(event.target.value)}
              maxLength={12000}
              rows={3}
              placeholder="For example: Research current options for training a private AI model and compare their costs."
              disabled={submitting}
              className="min-h-20 resize-y border-white/10 bg-[#0e1623] text-slate-100 placeholder:text-slate-500"
            />
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[11px] text-slate-500">
                Consequential steps remain supervised and may pause for your approval.
              </p>
              <Button type="submit" size="sm" disabled={!goal.trim() || submitting}>
                {submitting ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Send className="mr-2 h-3.5 w-3.5" aria-hidden="true" />}
                {submitting ? 'Submitting…' : 'Start task'}
              </Button>
            </div>
          </form>
        )}

        {error && (
          <p role="alert" className="mt-3 flex items-start gap-2 text-xs text-amber-200">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </p>
        )}

        {command && (
          <div className="mt-4 rounded-lg border border-white/[0.08] bg-white/[0.02] p-3" aria-live="polite">
            <p className="text-xs font-medium text-slate-200">{command.goal}</p>
            <p className="mt-1 text-[11px] text-slate-500">Task {command.command_id}</p>

            {status === 'AWAITING_AUTHORIZATION' && (
              <div className="mt-3 space-y-3 rounded-md border border-amber-200/15 bg-amber-200/[0.04] p-3">
                <p className="text-xs text-amber-100/90">JARVIS paused this task for your approval. Review the capability and risk level below before allowing the runtime to continue.</p>
                <ul className="space-y-1 text-xs text-slate-200">
                  {pendingNodeIds.map((nodeId) => {
                    const action = actionByNode.get(nodeId);
                    return (
                      <li key={nodeId}>
                        {action?.capability ?? nodeId} <span className="text-slate-400">({action?.risk_level ?? 'risk level not reported'})</span>
                      </li>
                    );
                  })}
                </ul>
                {pendingNodeIds.length > 1 && (
                  <label className="block text-xs text-slate-300">
                    Action requiring approval
                    <select
                      value={selectedNodeId}
                      onChange={(event) => setSelectedNodeId(event.target.value)}
                      className="mt-1 block w-full rounded-md border border-white/10 bg-[#0e1623] p-2 text-slate-100"
                    >
                      <option value="">Choose an action</option>
                      {pendingNodeIds.map((nodeId) => {
                        const action = actionByNode.get(nodeId);
                        const label = action
                          ? `${action.capability} (${action.risk_level})`
                          : nodeId;
                        return <option key={nodeId} value={nodeId}>{label}</option>;
                      })}
                    </select>
                  </label>
                )}
                <div className="flex gap-2">
                  <Button type="button" size="sm" disabled={authorizing || (pendingNodeIds.length > 1 && !selectedNodeId)} onClick={() => void decideAuthorization(true)}>
                    {authorizing ? 'Saving…' : 'Approve action'}
                  </Button>
                  <Button type="button" size="sm" variant="outline" disabled={authorizing} onClick={() => void decideAuthorization(false)}>
                    Decline
                  </Button>
                </div>
              </div>
            )}

            {resultText && <p className="mt-3 whitespace-pre-wrap text-xs leading-5 text-slate-300">{resultText}</p>}
            {status === 'COMPLETED' && (
              <p className="mt-3 flex items-center gap-2 text-xs text-emerald-200">
                <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                Runtime reports this task completed.
              </p>
            )}
            {isTerminal && status !== 'COMPLETED' && status !== 'PARTIAL' && (
              <p className="mt-3 text-xs text-rose-200">{command.errors?.join(' ') || `The runtime ended this task as ${STATUS_LABELS[status ?? ''] ?? status}.`}</p>
            )}
            {status === 'PARTIAL' && (
              <p className="mt-3 text-xs text-amber-200">The runtime reports partial completion. Review the saved result and errors before relying on it.</p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
