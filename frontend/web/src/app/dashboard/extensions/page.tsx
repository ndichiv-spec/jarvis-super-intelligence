'use client';

import { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Puzzle, Sparkles, Power, RefreshCw, Settings, ExternalLink, Trash2, Plus,
  BarChart3, MessageSquare, Calendar, Cloud, Globe, Github,
  Database, Brain, Terminal, Palette, CreditCard, Server, Activity,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { apiClient, ApiClientError, AuthError } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/config/api';

interface Extension {
  id: string;
  name: string;
  desc: string;
  category: string;
  icon: string;
  logo: string;
  installed: boolean;
  enabled: boolean;
  connected: boolean;
  status: string;
  config: Record<string, unknown>;
  installed_at?: string | null;
  connected_at?: string | null;
  launch_url?: string;
  connect_type?: string;
  key_env?: string;
  caps?: string[];
}

interface RuntimeTool {
  id: string;
  name: string;
  status: 'ready' | 'degraded' | 'unavailable' | 'auth_required' | 'error' | string;
  description: string;
  actions: Array<{
    id: string;
    description: string;
    execution_supported: boolean;
    authorized: boolean;
    requires_confirmation: boolean;
  }>;
  connection: { configured: boolean; reachable: boolean; authenticated: boolean };
  health: { error?: string; last_checked?: string; latency_ms?: number; [key: string]: unknown };
}

interface RuntimeEvent {
  event_id: string;
  event_type: string;
  timestamp: string;
  capability: string;
  status: string;
}

interface RuntimeInventory {
  status: string;
  execution_supported: boolean;
  tools: RuntimeTool[];
  events: RuntimeEvent[];
  checked_at: string;
}

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  core: Sparkles,
  ai: Brain,
  development: Github,
  devops: Terminal,
  cloud: Cloud,
  data: Database,
  research: Globe,
  communication: MessageSquare,
  productivity: Calendar,
  design: Palette,
  commerce: CreditCard,
  system: Server,
};

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  available: { label: 'Available', cls: 'text-muted-foreground/60' },
  needs_connection: { label: 'Needs connection', cls: 'text-amber-400' },
  connected: { label: 'Connected', cls: 'text-emerald-400' },
  disabled: { label: 'Disabled', cls: 'text-muted-foreground/60' },
};

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'An unexpected error occurred';
}

function ExtLogo({ ext }: { ext: Extension }) {
  const [broken, setBroken] = useState(false);
  if (!ext.logo || broken) {
    return (
      <span className="flex h-8 w-8 items-center justify-center text-2xl" aria-label={ext.name}>
        {ext.icon || '🔌'}
      </span>
    );
  }
  return (
    <img
      src={ext.logo}
      alt={ext.name}
      onError={() => setBroken(true)}
      loading="lazy"
      className="h-8 w-8 rounded object-contain"
    />
  );
}

function StatusDot({ status }: { status: string }) {
  const map: Record<string, string> = {
    connected: 'bg-emerald-400',
    needs_connection: 'bg-amber-400',
    disabled: 'bg-slate-400',
    available: 'bg-slate-500',
  };
  return <span className={`h-2 w-2 shrink-0 rounded-full ${map[status] || map.available}`} />;
}

export default function ExtensionsPage() {
  const [extensions, setExtensions] = useState<Extension[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [runtime, setRuntime] = useState<RuntimeInventory | null>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [runtimeLoading, setRuntimeLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get<{ extensions: Extension[] }>('/api/v1/extensions');
      setExtensions(res.extensions || []);
    } catch (e: unknown) {
      if (e instanceof AuthError) return; // 401 → global handler redirects to /login
      toast.error(`Failed to load extensions: ${errorMessage(e)}`);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRuntime = useCallback(async () => {
    setRuntimeLoading(true);
    setRuntimeError(null);
    try {
      const result = await apiClient.get<RuntimeInventory>(API_ENDPOINTS.system.capabilityRuntime);
      setRuntime(result);
    } catch (error: unknown) {
      setRuntimeError(errorMessage(error));
      setRuntime(null);
    } finally {
      setRuntimeLoading(false);
    }
  }, []);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      void load();
      void loadRuntime();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [load, loadRuntime]);

  const install = async (ext: Extension) => {
    setActionLoading(`${ext.id}:install`);
    try {
      await apiClient.post('/api/v1/extensions/install', { extension_id: ext.id });
      toast.success(`${ext.name} installed — grant access to activate`);
      await load();
    } catch (e: unknown) {
      if (e instanceof AuthError) return;
      toast.error(errorMessage(e));
    } finally {
      setActionLoading(null);
    }
  };

  const launchConnect = async (ext: Extension) => {
    setActionLoading(`${ext.id}:connect`);
    try {
      const launched = await apiClient.post<{
        launch_url: string;
        authorize_url?: string;
        connect_type?: string;
        key_env?: string;
        message?: string;
      }>(
        `/api/v1/extensions/${ext.id}/launch`);
      const connectType: string = launched.connect_type ||
        (launched.authorize_url ? 'oauth' : 'unsupported');

      if (connectType === 'api_key') {
        // API-key services (OpenAI, Claude, Gemini, Hugging Face ...): open the
        // service's key-creation console, then let the backend validate the key
        // (from env first, or a paste). A valid key flips the extension live on
        // the platform immediately -- no demo confirm-gate, no restart needed.
        if (launched.launch_url) {
          window.open(launched.launch_url, '_blank', 'noopener,noreferrer');
        }
        // First try the env-configured key (self-resilient: set it once).
        try {
          await apiClient.post(`/api/v1/extensions/${ext.id}/connect`, {});
          toast.success(`${ext.name} connected — capabilities are now active across the platform`);
          await load();
          return;
        } catch (e: unknown) {
          if (e instanceof ApiClientError && e.status === 400) {
            // env key missing/invalid -> fall through to the paste prompt
          } else {
            throw e;
          }
        }
        const hint = launched.key_env
          ? ` (set ${launched.key_env} or paste below)`
          : '';
        const key = window.prompt(
          `${ext.name} needs an API key.${hint}\nPaste your key here to connect JARVIS.`);
        if (key === null) {
          toast.info(`${ext.name} remains disconnected — create a key and press Connect again.`);
          return;
        }
        if (!key.trim()) {
          toast.error(`No API key provided for ${ext.name}.`);
          return;
        }
        await apiClient.post(`/api/v1/extensions/${ext.id}/connect`, { api_key: key.trim() });
        toast.success(`${ext.name} connected — capabilities are now active across the platform`);
        await load();
        return;
      } else if (launched.authorize_url) {
        // Real OAuth handoff: JARVIS has an OAuth app registered for this
        // service, so /launch returns the provider's authorize URL. The service
        // opens, you grant access, and it redirects back to JARVIS's
        // /api/v1/extensions/oauth/callback/<ext> — which exchanges the code
        // (server-side, using the secret from env) and VALIDATES the connection
        // on the backend. Capabilities go live automatically when you return.
        window.open(launched.authorize_url, '_blank', 'noopener,noreferrer');
        toast.info(
          `${ext.name} opened — grant access there. JARVIS validates your ` +
          `connection automatically when you're redirected back.`          );
          return;
      }
      toast.info(launched.message || `${ext.name} does not have an operational connection flow yet.`);
    } catch (e: unknown) {
      if (e instanceof AuthError) return;
      toast.error(errorMessage(e));
    } finally {
      setActionLoading(null);
    }
  };

  const toggle = async (ext: Extension, next: boolean) => {
    setActionLoading(`${ext.id}:toggle`);
    try {
      await apiClient.patch(`/api/v1/extensions/${ext.id}`, { enabled: next });
      toast.success(`${ext.name} ${next ? 'enabled' : 'disabled'}`);
      await load();
    } catch (e: unknown) {
      if (e instanceof AuthError) return;
      toast.error(errorMessage(e));
    } finally {
      setActionLoading(null);
    }
  };

  const uninstall = async (ext: Extension) => {
    if (!confirm(`Remove ${ext.name}? Installed config will be lost.`)) return;
    setActionLoading(`${ext.id}:uninstall`);
    try {
      await apiClient.post('/api/v1/extensions/uninstall', { extension_id: ext.id });
      toast.success(`${ext.name} removed`);
      await load();
    } catch (e: unknown) {
      if (e instanceof AuthError) return;
      toast.error(errorMessage(e));
    } finally {
      setActionLoading(null);
    }
  };

  const byCategory = (extensions || []).reduce<Record<string, Extension[]>>((acc, ext) => {
    (acc[ext.category] = acc[ext.category] || []).push(ext);
    return acc;
  }, {});

  const spin = (cond: boolean) =>
    cond ? <RefreshCw className="h-4 w-4 animate-spin" /> : null;
  const runtimeStatusClass = (status: string) => ({
    ready: 'text-emerald-400',
    degraded: 'text-amber-400',
    auth_required: 'text-amber-400',
    unavailable: 'text-slate-400',
    error: 'text-red-400',
  }[status] || 'text-slate-400');

  if (loading) {
    return (
      <div className="flex-1 space-y-6 p-6 pt-6 flex items-center justify-center min-h-[60vh]">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center"
        >
          <RefreshCw className="h-8 w-8 text-blue-400 animate-spin mx-auto mb-3" />
          <p className="text-cyan-200">Loading extensions…</p>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="flex-1 space-y-6 p-6 pt-6 bg-grid">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div className="flex items-center gap-4">
          <div className="relative">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-purple-500 via-fuchsia-400 to-purple-600 shadow-lg shadow-purple-500/30">
              <Puzzle className="h-7 w-7 text-white" />
            </div>
          </div>
          <div>
            <h1 className="text-3xl font-black bg-gradient-to-r from-purple-400 via-fuchsia-300 to-purple-400 bg-clip-text text-transparent">
              Extensions
            </h1>
            <p className="text-sm text-muted-foreground/70 mt-0.5">
              Install and manage capability packs that extend what JARVIS can do.
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => { void load(); void loadRuntime(); }}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button variant="outline" size="sm" asChild>
            <a href="/dashboard/developer/capabilities">
              <Settings className="h-4 w-4 mr-2" />
              AI Access
            </a>
          </Button>
        </div>
      </motion.div>

      <Card className="border border-cyan-500/20 bg-gradient-to-br from-slate-900/90 to-slate-800/80">
        <CardHeader>
          <CardTitle className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2"><Activity className="h-5 w-5 text-cyan-400" /> Capability Runtime</span>
            <Badge variant="outline">
              {runtimeLoading ? 'Checking live health…' : runtime?.status || 'Unavailable'}
            </Badge>
          </CardTitle>
          <CardDescription>
            Live tool inventory and health from the registered backend runtime. Catalog entries below are not proof of execution.
            {runtime?.checked_at && ` Last checked ${new Date(runtime.checked_at).toLocaleString()}.`}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {runtimeError && <p role="alert" className="text-sm text-red-300">{runtimeError}</p>}
          {!runtimeLoading && !runtimeError && runtime?.tools.length === 0 && (
            <p className="text-sm text-muted-foreground">The backend has no registered tool capability.</p>
          )}
          {runtime?.tools && runtime.tools.length > 0 && (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {runtime.tools.map((tool) => (
                <div key={tool.id} className="rounded-lg border border-white/10 bg-black/10 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{tool.name}</span>
                    <span className={`text-xs font-semibold uppercase ${runtimeStatusClass(tool.status)}`}>
                      ● {tool.status.replace('_', ' ')}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{tool.description}</p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {tool.connection.configured ? 'Configured' : 'Not configured'} ·{' '}
                    {tool.connection.reachable ? 'Reachable' : 'Not verified reachable'} ·{' '}
                    {tool.connection.authenticated ? 'Authenticated' : 'Authentication not verified'}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {tool.actions.map((action) => (
                      <Badge
                        key={action.id}
                        variant="outline"
                        title={`${action.description}${action.requires_confirmation ? ' · Requires confirmation' : ''}${!action.authorized ? ' · Not authorized for this account' : ''}`}
                        className={!action.authorized ? 'text-muted-foreground/50' : action.requires_confirmation ? 'text-amber-300' : ''}
                      >
                        {action.id}
                      </Badge>
                    ))}
                    {tool.actions.length === 0 && (
                      <span className="text-xs text-muted-foreground">No action schemas reported</span>
                    )}
                  </div>
                  {tool.health.error && <p className="mt-2 text-xs text-amber-300">{tool.health.error}</p>}
                </div>
              ))}
            </div>
          )}
          <div className="border-t border-white/10 pt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Recent runtime events</p>
            {runtime?.events.length ? (
              <ol className="space-y-1">
                {runtime.events.slice(-8).reverse().map((event) => (
                  <li key={event.event_id} className="flex flex-wrap gap-x-2 text-xs text-muted-foreground">
                    <time>{new Date(event.timestamp).toLocaleTimeString()}</time>
                    <span>{event.event_type}</span>
                    <span>{event.capability}</span>
                    <span>({event.status})</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-xs text-muted-foreground">No capability executions recorded for this account yet.</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Installed summary */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border border-purple-500/20">
          <CardContent className="pt-6 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Sparkles className="h-6 w-6 text-purple-400" />
              <div>
                <p className="font-semibold text-purple-300">Extensions Marketplace</p>
                <p className="text-sm text-muted-foreground/70">
                  {extensions.filter((e) => e.installed && e.connected).length} connected ·{' '}
                  {extensions.filter((e) => e.installed && e.enabled).length} active ·{' '}
                  {extensions.filter((e) => e.installed).length} installed ·{' '}
                  {extensions.length} available
                </p>
              </div>
            </div>
            <Badge variant="outline">v1.0</Badge>
          </CardContent>
        </Card>
      </motion.div>

      {/* Categories */}
      {Object.keys(byCategory).map((category, ci) => (
        <motion.div
          key={category}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 + ci * 0.05 }}
        >
          <div className="flex items-center gap-2 mb-3">
            {(() => {
              const Icon = CATEGORY_ICONS[category];
              return Icon ? <Icon className="h-4 w-4 text-cyan-400" /> : null;
            })()}
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground/50">
              {category}
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {byCategory[category].map((ext, ei) => {
              const sb = STATUS_BADGE[ext.status] || STATUS_BADGE.available;
              const busy = actionLoading === `${ext.id}:connect` || actionLoading === `${ext.id}:toggle` || actionLoading === `${ext.id}:install` || actionLoading === `${ext.id}:uninstall`;
              return (
                <motion.div
                  key={ext.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: ei * 0.05 }}
                >
                  <Card className="h-full bg-gradient-to-br from-slate-900/80 to-slate-800/80 border border-white/10 hover:border-purple-500/30 transition-colors flex flex-col">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-white">
                        <ExtLogo ext={ext} />
                        {ext.name}
                        <Badge
                          variant={ext.enabled ? 'default' : 'secondary'}
                          className="ml-auto text-xs"
                        >
                          {ext.enabled ? 'Enabled' : 'Disabled'}
                        </Badge>
                        {ext.installed && (
                          <Badge
                            variant="outline"
                            className={`ml-1 text-xs gap-1 pl-1.5 ${
                              ext.connected
                                ? 'border-emerald-500/30 text-emerald-300'
                                : 'border-amber-500/30 text-amber-300'
                            }`}
                          >
                            <StatusDot status={ext.status} />
                            {sb.label}
                          </Badge>
                        )}
                      </CardTitle>
                      <CardDescription className="line-clamp-2">
                        {ext.desc}
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="flex-1 flex flex-col gap-4">
                      {ext.connected_at && (
                        <p className="text-xs text-muted-foreground/60">
                          Connected {new Date(ext.connected_at).toLocaleDateString(undefined, {
                            year: 'numeric', month: 'short', day: 'numeric',
                          })}
                        </p>
                      )}
                      {ext.caps && ext.caps.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {ext.caps.map((c) => (
                            <Badge key={c} variant="outline" className="text-[10px] px-1.5">
                              {c}
                            </Badge>
                          ))}
                        </div>
                      )}

                      <div className="mt-auto flex gap-2">
                        {!ext.installed ? (
                          <Button
                            size="sm"
                            className="flex-1"
                            onClick={() => install(ext)}
                            disabled={actionLoading === `${ext.id}:install`}
                          >
                            {spin(actionLoading === `${ext.id}:install`) && (
                              <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                            )}
                            <Plus className="h-4 w-4 mr-1" />
                            Install
                          </Button>
                        ) : (
                          <>
                            <Button
                              size="sm"
                              variant={ext.connected ? 'outline' : 'default'}
                              className="flex-1"
                              onClick={() => launchConnect(ext)}
                              disabled={busy}
                            >
                              {spin(actionLoading === `${ext.id}:connect`) ? (
                                <RefreshCw className="h-4 w-4 animate-spin" />
                              ) : (
                                <ExternalLink className="h-4 w-4" />
                              )}
                              {ext.connected ? 'Reconnect' : 'Connect'}
                            </Button>
                            <Button
                              size="sm"
                              variant={ext.enabled ? 'outline' : 'default'}
                              onClick={() => toggle(ext, !ext.enabled)}
                              disabled={busy}
                            >
                              {spin(actionLoading === `${ext.id}:toggle`) ? (
                                <RefreshCw className="h-4 w-4 animate-spin" />
                              ) : (
                                <Power className="h-4 w-4" />
                              )}
                              {ext.enabled ? 'Disable' : 'Enable'}
                            </Button>
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={() => uninstall(ext)}
                              disabled={busy}
                            >
                              {spin(actionLoading === `${ext.id}:uninstall`) ? (
                                <RefreshCw className="h-4 w-4 animate-spin" />
                              ) : (
                                <Trash2 className="h-4 w-4" />
                              )}
                            </Button>
                          </>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              );
            })}
          </div>
        </motion.div>
      ))}

      {extensions.length === 0 && (
        <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border border-white/10">
          <CardContent className="pt-10 text-center">
            <Puzzle className="h-12 w-12 text-muted-foreground/40 mx-auto mb-3" />
            <p className="text-muted-foreground/60">No extensions available.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
