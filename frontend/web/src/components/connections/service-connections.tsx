'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { ExternalLink, Github, Loader2, RefreshCw, ShieldCheck, Unplug } from 'lucide-react';
import { toast } from 'sonner';
import { ApiClientError, apiClient } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

interface ServiceConnection {
  id: string;
  provider: string;
  authorization_type: string;
  connected: boolean;
  status: string;
  account: string | null;
  scopes: string | null;
  expires_at: number | null;
  refresh_supported: boolean;
  capabilities: string[];
  installed: boolean;
  enabled: boolean;
  authorization_configured: boolean;
  health: string;
}

interface Repository {
  name: string;
  full_name: string;
  description: string;
  private: boolean;
  language: string | null;
}

function errorText(error: unknown): string {
  if (error instanceof ApiClientError && error.details && typeof error.details === 'object') {
    const detail = (error.details as { detail?: unknown }).detail;
    if (detail && typeof detail === 'object') {
      const fields = detail as Record<string, unknown>;
      const actionable = [
        fields.required_permission,
        fields.reason,
        fields.current_permission,
        fields.remediation,
      ].filter((value): value is string => typeof value === 'string' && value.length > 0);
      if (actionable.length > 0) return actionable.join(' · ');
    }
  }
  if (error instanceof Error) return error.message;
  return 'The connection request failed.';
}

export function ServiceConnections() {
  const [connection, setConnection] = useState<ServiceConnection | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [repositoryError, setRepositoryError] = useState<string | null>(null);
  const [selectedRepository, setSelectedRepository] = useState('');
  const [repositoryDetails, setRepositoryDetails] = useState<Record<string, unknown> | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await apiClient.get<{ connections: ServiceConnection[] }>(
        '/api/v1/extensions/connections',
      );
      setConnection(result.connections.find((item) => item.id === 'github') ?? null);
    } catch (error: unknown) {
      toast.error(`Could not load service authorizations: ${errorText(error)}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => void load());
    return () => window.cancelAnimationFrame(frame);
  }, [load]);

  const authorize = async () => {
    if (!connection?.authorization_configured) return;
    setBusy(true);
    try {
      const launched = await apiClient.post<{ authorize_url?: string; connect_type: string }>(
        '/api/v1/extensions/github/launch',
      );
      if (!launched.authorize_url || launched.connect_type !== 'oauth') {
        toast.error('GitHub OAuth is not configured for this deployment.');
        return;
      }
      window.open(launched.authorize_url, '_blank', 'noopener,noreferrer');
      toast.info('GitHub authorization opened in a new tab. Return here after approving access.');
    } catch (error: unknown) {
      toast.error(`Could not start GitHub authorization: ${errorText(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    setBusy(true);
    try {
      const result = await apiClient.post<{
        account: string;
        scopes: string | null;
        capabilities: string[];
      }>('/api/v1/extensions/github/verify', {});
      setConnection((current) => current ? {
        ...current,
        connected: true,
        status: 'Connected',
        account: result.account,
        scopes: result.scopes,
        health: 'verified',
        capabilities: result.capabilities,
      } : current);
      toast.success(`GitHub verified for ${result.account}`);
    } catch (error: unknown) {
      toast.error(`GitHub verification failed: ${errorText(error)}`);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!window.confirm('Disconnect GitHub for your JARVIS account? This does not revoke JARVIS in GitHub settings.')) return;
    setBusy(true);
    try {
      await apiClient.delete('/api/v1/extensions/github/connection');
      setRepositories([]);
      setRepositoryDetails(null);
      await load();
      toast.success('GitHub disconnected from this JARVIS account.');
    } catch (error: unknown) {
      toast.error(`Could not disconnect GitHub: ${errorText(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const loadRepositories = async () => {
    setBusy(true);
    setRepositoryError(null);
    setRepositoryDetails(null);
    try {
      const response = await apiClient.post<{
        result: { repos?: Repository[] };
      }>('/api/v1/extensions/github/invoke', {
        capability: 'github.repositories.list',
        params: {},
      });
      const items = response.result.repos ?? [];
      setRepositories(items);
      setSelectedRepository(items[0]?.full_name ?? '');
      if (items.length === 0) setRepositoryError('GitHub returned no repositories for this account.');
    } catch (error: unknown) {
      setRepositoryError(errorText(error));
    } finally {
      setBusy(false);
    }
  };

  const inspectRepository = async () => {
    const [owner, repo] = selectedRepository.split('/');
    if (!owner || !repo) return;
    setBusy(true);
    setRepositoryError(null);
    try {
      const response = await apiClient.post<{
        result: Record<string, unknown>;
      }>('/api/v1/extensions/github/invoke', {
        capability: 'github.repository.read',
        params: { owner, repo },
      });
      setRepositoryDetails(response.result);
    } catch (error: unknown) {
      setRepositoryError(errorText(error));
    } finally {
      setBusy(false);
    }
  };

  const status = loading ? 'Checking authorization' : connection?.status ?? 'Unavailable';
  const connected = connection?.connected === true;

  return (
    <Card className="border-white/10 bg-slate-950/70">
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <Github className="h-5 w-5 text-cyan-200" aria-hidden="true" />
            Service authorizations
          </CardTitle>
          <CardDescription className="mt-1">
            Account-scoped grants and live provider verification. Credentials remain server-side.
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
          {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
          Refresh
        </Button>
      </CardHeader>
      <CardContent>
        {!connection ? (
          <p role="status" className="text-sm text-muted-foreground">No service connection metadata is available.</p>
        ) : (
          <div className="rounded-xl border border-white/10 bg-white/[0.025] p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-semibold text-foreground">GitHub</h3>
                  <span className={`rounded-full border px-2 py-0.5 text-xs ${
                    connected
                      ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
                      : 'border-amber-400/30 bg-amber-400/10 text-amber-200'
                  }`}>
                    {status}
                  </span>
                  {connection.health === 'verified' && (
                    <span className="inline-flex items-center gap-1 text-xs text-emerald-200">
                      <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" /> Verified
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {connection.account ? `Authorized as ${connection.account}` : 'OAuth authorization is scoped to your signed-in JARVIS identity.'}
                </p>
                <p className="mt-1 break-words text-xs text-muted-foreground/70">
                  Granted scopes: {connection.scopes || 'Not reported'}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {connection.installed ? (
                  <>
                    <Button size="sm" onClick={() => void authorize()} disabled={busy || !connection.authorization_configured}>
                      <ExternalLink className="mr-2 h-4 w-4" />
                      {connected ? 'Reauthorize' : 'Authorize'}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => void verify()} disabled={busy || !connected}>
                      {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ShieldCheck className="mr-2 h-4 w-4" />}
                      Verify
                    </Button>
                    {connected && (
                      <Button size="sm" variant="outline" onClick={() => void disconnect()} disabled={busy}>
                        <Unplug className="mr-2 h-4 w-4" />
                        Disconnect
                      </Button>
                    )}
                  </>
                ) : (
                  <Button size="sm" variant="outline" asChild>
                    <Link href="/dashboard/extensions">Install from Extensions</Link>
                  </Button>
                )}
              </div>
            </div>
            {!connection.authorization_configured && (
              <p className="mt-3 border-t border-white/10 pt-3 text-xs text-amber-200/90">
                An administrator must register the GitHub OAuth application and configure its callback URL before this connection can be authorized.
              </p>
            )}
            {connected && connection.enabled && (
              <div className="mt-4 border-t border-white/10 pt-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h4 className="text-sm font-medium">Repository access</h4>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Repository discovery and inspection use the authorized GitHub API grant.
                    </p>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => void loadRepositories()} disabled={busy}>
                    {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    List repositories
                  </Button>
                </div>
                {repositories.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <select
                      aria-label="Select a GitHub repository"
                      value={selectedRepository}
                      onChange={(event) => setSelectedRepository(event.target.value)}
                      className="min-h-9 min-w-52 rounded-md border border-white/15 bg-slate-950 px-3 text-sm text-foreground"
                    >
                      {repositories.map((repository) => (
                        <option key={repository.full_name} value={repository.full_name}>
                          {repository.full_name}{repository.private ? ' · private' : ''}
                        </option>
                      ))}
                    </select>
                    <Button size="sm" variant="outline" onClick={() => void inspectRepository()} disabled={busy || !selectedRepository}>
                      Inspect repository
                    </Button>
                  </div>
                )}
                {repositoryError && <p role="alert" className="mt-3 text-sm text-rose-200">{repositoryError}</p>}
                {repositoryDetails && (
                  <pre className="mt-3 max-h-64 overflow-auto rounded-md border border-white/10 bg-black/30 p-3 text-xs text-slate-200">
                    {JSON.stringify(repositoryDetails, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
