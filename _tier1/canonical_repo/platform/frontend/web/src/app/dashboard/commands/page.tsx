'use client';

import { useMemo, useState, type FormEvent } from 'react';
import { Activity, ArrowDown, Bot, Check, Circle, Clock3, Cpu, GitBranch, Loader2, Play, ShieldAlert, Square, Wrench } from 'lucide-react';
import apiClient from '@/lib/api-client';
import { usePlatformStore } from '@/stores/platform-store';
import { isActiveCommandStatus, type RuntimeCommand } from '@/lib/types/runtime';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';

function eventStatus(command: RuntimeCommand, capability: string): 'queued' | 'active' | 'completed' | 'failed' | 'blocked' {
  const events = command.events.filter((event) => event.capability === capability);
  const latest = events[events.length - 1]?.event;
  if (latest === 'capability_started') return 'active';
  if (latest === 'capability_completed') return 'completed';
  if (latest === 'capability_failed') return 'failed';
  if (command.status === 'FAILED' || command.status === 'CANCELLED') return 'blocked';
  return 'queued';
}

function stateClass(state: string): string {
  if (state === 'completed') return 'border-emerald-400/20 bg-emerald-400/[0.04]';
  if (state === 'failed') return 'border-rose-400/25 bg-rose-400/[0.05]';
  if (state === 'active') return 'border-cyan-300/25 bg-cyan-300/[0.05]';
  return 'border-white/[0.08] bg-white/[0.02]';
}

function statusClass(status: string): string {
  if (status === 'COMPLETED' || status === 'completed') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300';
  if (status === 'FAILED' || status === 'failed') return 'border-rose-400/30 bg-rose-400/10 text-rose-300';
  if (status === 'EXECUTING' || status === 'active' || status === 'VERIFYING') return 'border-cyan-300/30 bg-cyan-300/10 text-cyan-200';
  if (status === 'AWAITING_AUTHORIZATION') return 'border-amber-300/30 bg-amber-300/10 text-amber-200';
  return 'border-white/10 bg-white/[0.04] text-slate-300';
}

export default function CommandCenterPage() {
  const [goal, setGoal] = useState('');
  const [selectedCommandId, setSelectedCommandId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const commands = usePlatformStore((state) => state.commands);
  const capabilities = usePlatformStore((state) => state.commandCapabilities);
  const commandError = usePlatformStore((state) => state.commandError);
  const commandAvailability = usePlatformStore((state) => state.commandAvailability);
  const capabilityAvailability = usePlatformStore((state) => state.commandCapabilitiesAvailability);
  const setRuntimeCommand = usePlatformStore((state) => state.setRuntimeCommand);
  const refreshCommands = usePlatformStore((state) => state.refreshCommands);
  const command = commands.find((item) => item.command_id === selectedCommandId)
    ?? commands.find((item) => isActiveCommandStatus(item.status))
    ?? null;
  const history = commands;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!goal.trim() || submitting) return;
    setSubmitting(true);
    setError('');
    try {
      const created = await apiClient.post<RuntimeCommand>('/api/v1/commands', {
        goal: goal.trim(),
        request_id: crypto.randomUUID(),
        autonomy: 'SUPERVISED',
      }, { retries: 0 });
      setRuntimeCommand(created);
      setSelectedCommandId(created.command_id);
      setGoal('');
      void refreshCommands();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Command could not be submitted');
    } finally {
      setSubmitting(false);
    }
  };

  const decideAuthorization = async (approved: boolean) => {
    if (!command) return;
    setError('');
    try {
      const updated = await apiClient.post<RuntimeCommand>(
        `/api/v1/commands/${command.command_id}/authorization`,
        { approved },
        { retries: 0 },
      );
      setRuntimeCommand(updated);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Authorization decision failed');
    }
  };

  const cancel = async () => {
    if (!command) return;
    try {
      await apiClient.post(
        `/api/v1/commands/${command.command_id}/cancel`,
        undefined,
        { retries: 0 },
      );
      const latest = await apiClient.get<RuntimeCommand>(`/api/v1/commands/${command.command_id}`);
      setRuntimeCommand(latest);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Command cancellation failed');
    }
  };

  const availableCount = useMemo(
    () => capabilities.filter((capability) => capability.availability === 'AVAILABLE').length,
    [capabilities],
  );

  return (
    <main className="min-h-full space-y-5 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.24em] text-cyan-300/70">JARVIS · Runtime 2.0</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-white">Command Center</h1>
          <p className="mt-1 text-sm text-slate-400">Submit a goal, authorize sensitive actions, and follow the actual execution trace.</p>
        </div>
        <Badge className="border border-white/10 bg-slate-900/70 px-3 py-1.5 text-slate-300">
          <Activity aria-hidden="true" className="mr-2 h-3.5 w-3.5 text-cyan-300" />
          {capabilityAvailability === 'completed'
            ? `${availableCount} / ${capabilities.length} capabilities available`
            : 'Capability registry unavailable'}
        </Badge>
      </header>

      {(error || commandError) && (
        <p role="alert" className="rounded-lg border border-rose-400/20 bg-rose-400/5 px-4 py-3 text-sm text-rose-200">
          {error || commandError}
        </p>
      )}
      {(commandAvailability === 'idle' || commandAvailability === 'loading') && (
        <p role="status" className="text-sm text-slate-400">Loading owner-scoped command history…</p>
      )}

      <form onSubmit={submit}>
        <Card className="border-white/10 bg-slate-950/70 shadow-xl shadow-cyan-950/10">
          <CardContent className="p-4 md:p-5">
            <label htmlFor="command-goal" className="mb-2 block text-sm font-medium text-slate-200">What should JARVIS do?</label>
            <Textarea
              id="command-goal"
              value={goal}
              onChange={(event) => setGoal(event.target.value)}
              placeholder="Describe the goal. JARVIS will plan using registered capabilities and report what actually ran."
              maxLength={12000}
              rows={3}
              className="resize-y border-white/10 bg-black/20 text-slate-100 placeholder:text-slate-500 focus-visible:ring-cyan-400/50"
            />
            <div className="mt-3 flex items-center justify-between gap-3">
              <p className="text-xs text-slate-500">Sensitive or external actions wait for your explicit approval.</p>
              <Button type="submit" disabled={submitting || !goal.trim()} className="gap-2">
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                Run command
              </Button>
            </div>
          </CardContent>
        </Card>
      </form>

      {command && (
        <section aria-label="Active command" className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(280px,0.8fr)]">
          <Card className="border-white/10 bg-slate-950/65">
            <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
              <div className="min-w-0">
                <CardTitle className="text-base text-white">Execution graph</CardTitle>
                <p className="mt-2 break-words text-sm text-slate-400">{command.goal}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Badge className={statusClass(command.status)}>{command.status}</Badge>
                {isActiveCommandStatus(command.status) && (
                  <Button type="button" variant="outline" size="icon" aria-label="Cancel command" onClick={cancel}>
                    <Square className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {command.plan.length === 0 ? (
                <div className="rounded-lg border border-dashed border-white/10 px-4 py-6 text-sm text-slate-400">
                  {isActiveCommandStatus(command.status) ? 'JARVIS is understanding the request; no plan has been emitted yet.' : 'No executable plan was produced.'}
                </div>
              ) : (
                <ol className="space-y-2">
                  {command.plan.map((step, index) => {
                    const state = eventStatus(command, step.capability);
                    const StateIcon = state === 'active' ? Loader2 : state === 'completed' ? Check : state === 'failed' ? ShieldAlert : Circle;
                    return (
                      <li key={`${step.step_id}-${index}`} className="relative">
                        {index < command.plan.length - 1 && <span aria-hidden="true" className="absolute left-[17px] top-10 h-[calc(100%+0.5rem)] border-l border-slate-700" />}
                        <div className={`relative flex gap-3 rounded-lg border p-3 ${stateClass(state)}`}>
                          <StateIcon aria-hidden="true" className={`mt-0.5 h-4 w-4 shrink-0 ${state === 'active' ? 'animate-spin motion-reduce:animate-none' : ''}`} />
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-sm font-medium text-slate-100">{step.summary || step.capability}</span>
                              <code className="rounded bg-black/20 px-1.5 py-0.5 text-[10px] text-cyan-200">{step.capability}</code>
                              <span className="ml-auto text-[10px] uppercase tracking-wide text-slate-400">{state}</span>
                            </div>
                            {step.depends_on.length > 0 && (
                              <p className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                                <GitBranch aria-hidden="true" className="h-3 w-3" /> Depends on {step.depends_on.join(', ')}
                              </p>
                            )}
                          </div>
                        </div>
                        {index < command.plan.length - 1 && (
                          <div className="my-1 ml-3.5 text-slate-600"><ArrowDown aria-hidden="true" className="h-3 w-3" /></div>
                        )}
                      </li>
                    );
                  })}
                </ol>
              )}
              {command.result && (
                <div className="mt-4 rounded-lg border border-emerald-400/20 bg-emerald-400/[0.04] p-4">
                  <h3 className="text-sm font-semibold text-emerald-100">Runtime result</h3>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{command.result.summary}</p>
                  <p className="mt-2 text-xs text-slate-500">
                    Verification: {command.result.completion_condition_met || 'not satisfied'} · {command.result.confidence_state}
                  </p>
                </div>
              )}
              {command.status === 'AWAITING_AUTHORIZATION' && command.authorization && (
                <div className="mt-4 rounded-lg border border-amber-300/25 bg-amber-300/[0.06] p-4">
                  <div className="flex items-start gap-3">
                    <ShieldAlert aria-hidden="true" className="mt-0.5 h-5 w-5 text-amber-200" />
                    <div className="flex-1">
                      <h3 className="text-sm font-semibold text-amber-100">Approval required</h3>
                      <p className="mt-1 text-xs text-amber-100/70">Requested actions: {command.authorization.capabilities.join(', ')}</p>
                      <div className="mt-3 flex gap-2">
                        <Button type="button" size="sm" onClick={() => void decideAuthorization(true)}>Approve</Button>
                        <Button type="button" size="sm" variant="outline" onClick={() => void decideAuthorization(false)}>Deny</Button>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <div className="space-y-4">
            <Card className="border-white/10 bg-slate-950/65">
              <CardHeader><CardTitle className="text-base text-white">Runtime intelligence</CardTitle></CardHeader>
              <CardContent className="space-y-3 text-sm">
                <IntelRow icon={Activity} label="Objective" value={command.goal} />
                <IntelRow icon={Wrench} label="Active step" value={command.active_step || '—'} />
                <IntelRow icon={Cpu} label="Model" value={command.models.join(', ') || 'Not selected'} />
                <IntelRow icon={Bot} label="Agent" value="JARVIS supervisor" />
                <IntelRow icon={Wrench} label="Executed capabilities" value={command.capabilities.join(', ') || 'None yet'} />
                {command.errors.map((message, index) => (
                  <p key={`${index}-${message}`} role="status" className="rounded border border-rose-400/20 p-2 text-xs text-rose-200">{message}</p>
                ))}
              </CardContent>
            </Card>
            <Card className="border-white/10 bg-slate-950/65">
              <CardHeader><CardTitle className="flex items-center gap-2 text-base text-white"><Clock3 aria-hidden="true" className="h-4 w-4 text-cyan-200" />Live runtime events</CardTitle></CardHeader>
              <CardContent>
                <ol aria-live="polite" aria-relevant="additions" className="max-h-72 space-y-2 overflow-y-auto pr-1">
                  {[...command.events].reverse().map((event) => (
                    <li key={event.sequence} className="border-l border-slate-700 pl-3">
                      <p className="text-xs font-medium text-slate-200">{event.event.replaceAll('_', ' ')}</p>
                      {event.detail && <p className="mt-0.5 line-clamp-3 text-xs text-slate-500">{event.detail}</p>}
                      <time className="mt-1 block text-[10px] text-slate-600" dateTime={new Date(event.timestamp * 1000).toISOString()}>
                        {new Date(event.timestamp * 1000).toLocaleTimeString()}
                      </time>
                    </li>
                  ))}
                  {command.events.length === 0 && <li className="text-xs text-slate-500">Waiting for runtime events.</li>}
                </ol>
              </CardContent>
            </Card>
          </div>
        </section>
      )}

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(280px,0.8fr)]">
        <Card className="border-white/10 bg-slate-950/60">
          <CardHeader><CardTitle className="text-base text-white">Capability registry</CardTitle></CardHeader>
          <CardContent>
            <div className="grid gap-2 sm:grid-cols-2">
              {capabilities.slice(0, 16).map((capability) => (
                <div key={capability.id} className="flex items-start justify-between gap-3 rounded-lg border border-white/[0.07] px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-slate-200">{capability.name}</p>
                    <p className="mt-0.5 text-[10px] text-slate-500">{capability.domain} · {capability.risk_level}</p>
                  </div>
                  <Badge className={statusClass(capability.availability)}>{capability.availability}</Badge>
                </div>
              ))}
              {capabilities.length === 0 && (
                <p role="status" className="text-xs text-slate-500">
                  {capabilityAvailability === 'completed'
                    ? 'No command capabilities are registered.'
                    : 'Capability registry is unavailable until the backend responds.'}
                </p>
              )}
            </div>
          </CardContent>
        </Card>
        <Card className="border-white/10 bg-slate-950/60">
          <CardHeader><CardTitle className="text-base text-white">Recent commands</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {history.slice(0, 6).map((item) => (
              <button
                type="button"
                key={item.command_id}
                onClick={() => setSelectedCommandId(item.command_id)}
                className="flex w-full items-center justify-between gap-3 rounded-lg border border-white/[0.07] p-3 text-left hover:border-cyan-200/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300"
              >
                <span className="line-clamp-2 text-xs text-slate-300">{item.goal}</span>
                <Badge className={statusClass(item.status)}>{item.status}</Badge>
              </button>
            ))}
            {history.length === 0 && (
              <p className="text-xs text-slate-500">
                {commandAvailability === 'completed' ? 'No commands recorded for this account yet.' : 'Command history is unavailable.'}
              </p>
            )}
          </CardContent>
        </Card>
      </section>
    </main>
  );
}

function IntelRow({ icon: Icon, label, value }: { icon: typeof Activity; label: string; value: string }) {
  return (
    <div className="flex items-start gap-2">
      <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-cyan-200/70" />
      <div className="min-w-0">
        <p className="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
        <p className="break-words text-xs text-slate-200">{value}</p>
      </div>
    </div>
  );
}
