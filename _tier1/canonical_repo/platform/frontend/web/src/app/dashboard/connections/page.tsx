'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Mail, Shield, ShieldCheck, ShieldX, CheckCircle2, XCircle, AlertCircle,
  Save, TestTube, Trash2, Settings, Power, Activity, RefreshCw,
  Edit3, Lock, Unlock, Send, Search, FileText, Clock, Github, ExternalLink,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api-client';
import API_ENDPOINTS from '@/config/api';

const MASK = '········';

const PROVIDER_DEFAULTS: Record<string, { imap_host: string; imap_port: number; smtp_host: string; smtp_port: number; }> = {
  Gmail:   { imap_host: 'imap.gmail.com', imap_port: 993, smtp_host: 'smtp.gmail.com', smtp_port: 587 },
  Outlook: { imap_host: 'outlook.office365.com', imap_port: 993, smtp_host: 'smtp-mail.outlook.com', smtp_port: 587 },
  iCloud:  { imap_host: 'imap.mail.me.com', imap_port: 993, smtp_host: 'smtp.mail.me.com', smtp_port: 587 },
  Other:   { imap_host: '', imap_port: 993, smtp_host: '', smtp_port: 587 },
};

const CAP_LABELS: Record<string, { label: string; icon: React.ElementType; color: string }> = {
  read:       { label: 'Read / Search',     icon: Search,  color: 'text-blue-400' },
  summarize:  { label: 'Summarize',        icon: FileText, color: 'text-purple-400' },
  draft:      { label: 'Draft',            icon: Edit3,    color: 'text-amber-400' },
  send:       { label: 'Send / Reply',     icon: Send,     color: 'text-emerald-400' },
};

interface ConnectorConfig {
  kind?: string;
  label?: string;
  provider?: string;
  imap_host?: string;
  imap_port?: number;
  imap_ssl?: boolean;
  imap_user?: string;
  password?: string;
  smtp_host?: string;
  smtp_port?: number;
  smtp_starttls?: boolean;
  send_from?: string;
  capabilities?: string[];
  enabled?: boolean;
  configured?: boolean;
  possible_capabilities?: string[];
  last_tested_at?: string;
  last_test_ok?: boolean;
}

interface AuditEntry {
  ts?: string;
  actor?: string;
  kind?: string;
  action?: string;
  ok?: boolean;
  error?: string;
  params?: Record<string, unknown>;
  [k: string]: unknown;
}

interface TestResult {
  ok?: boolean;
  message?: string;
  at?: string;
  imap?: { ok?: boolean; message?: string };
  smtp?: { ok?: boolean; message?: string };
}

interface ConnectorConfigResponse {
  kind?: string;
  label?: string;
  provider?: string;
  imap_host?: string;
  imap_port?: number;
  imap_ssl?: boolean;
  imap_user?: string;
  smtp_host?: string;
  smtp_port?: number;
  smtp_starttls?: boolean;
  send_from?: string;
  capabilities?: string[];
  enabled?: boolean;
  configured?: boolean;
  possible_capabilities?: string[];
  last_tested_at?: string;
  last_test_ok?: boolean;
}

interface GitHubConnection {
  provider: string;
  connected: boolean;
  status: string;
  account?: string | null;
  scopes: string[];
  expires_at?: number | null;
  capabilities: string[];
}

interface GitHubRepository {
  id: number;
  full_name: string;
  private: boolean;
  description?: string | null;
  default_branch: string;
  html_url: string;
  updated_at: string;
  permissions?: Record<string, boolean>;
}

interface GitHubFile {
  path: string;
  sha: string;
  size: number;
  content: string | null;
  binary: boolean;
  html_url: string;
}

export default function ConnectionsPage() {
  const [connectors, setConnectors] = useState<Record<string, ConnectorConfig>>({});
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<ConnectorConfig>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [activity, setActivity] = useState<AuditEntry[]>([]);
  const [githubConnection, setGitHubConnection] = useState<GitHubConnection | null>(null);
  const [githubLoading, setGitHubLoading] = useState(false);
  const [githubBusy, setGitHubBusy] = useState(false);
  const [githubError, setGitHubError] = useState<string | null>(null);
  const [githubRepositories, setGitHubRepositories] = useState<GitHubRepository[]>([]);
  const [githubPage, setGitHubPage] = useState(1);
  const [githubHasNextPage, setGitHubHasNextPage] = useState(false);
  const [selectedGitHubRepository, setSelectedGitHubRepository] = useState<GitHubRepository | null>(null);
  const [githubFilePath, setGitHubFilePath] = useState('');
  const [githubFile, setGitHubFile] = useState<GitHubFile | null>(null);

  const loadGitHubConnection = async () => {
    setGitHubLoading(true);
    setGitHubError(null);
    try {
      const connection = await apiClient.get<GitHubConnection>(API_ENDPOINTS.connectors.github.connection);
      setGitHubConnection(connection);
    } catch (error) {
      setGitHubConnection(null);
      setGitHubError(error instanceof Error ? error.message : 'GitHub connection status is unavailable.');
    } finally {
      setGitHubLoading(false);
    }
  };

  const load = async () => {
    setLoading(true);
    const githubRequest = loadGitHubConnection();
    try {
      const res = await apiClient.get<{ connectors: any[] }>(API_ENDPOINTS.connectors.list);
      const map: Record<string, ConnectorConfig> = {};
      (res.connectors || []).forEach((c: any) => {
        map[c.kind] = { ...c, ...(c.config || {}) } as ConnectorConfig;
      });
      setConnectors(map);
      const email = map['email'];
      if (email) setConfig(email);
      await loadActivity();
    } catch (e: any) {
      toast.error(`Failed to load connectors: ${e.message}`);
    } finally {
      await githubRequest;
      setLoading(false);
    }
  };

  const loadActivity = async () => {
    try {
      const res = await apiClient.get<{ entries: AuditEntry[] }>(API_ENDPOINTS.connectors.activity);
      setActivity(res.entries || []);
    } catch {
      setActivity([]);
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const connected = params.get('connected');
    const verified = params.get('verified');
    const githubError = params.get('github_error');
    if (connected === 'github') {
      toast.success(verified === '1' ? 'GitHub authorization verified.' : 'GitHub authorization received; verify the connection before use.');
    }
    if (githubError) toast.error(`GitHub authorization was not completed: ${githubError}`);
    if (connected || githubError) window.history.replaceState({}, '', window.location.pathname);
    void load();
  }, []);

  const connectGitHub = async () => {
    setGitHubBusy(true);
    setGitHubError(null);
    try {
      const response = await apiClient.post<{ authorize_url: string }>(
        API_ENDPOINTS.connectors.github.authorize,
        {},
        { retries: 0 },
      );
      if (!response.authorize_url) throw new Error('The server returned no GitHub authorization URL.');
      window.location.assign(response.authorize_url);
    } catch (error) {
      setGitHubError(error instanceof Error ? error.message : 'Could not start GitHub authorization.');
      setGitHubBusy(false);
    }
  };

  const verifyGitHub = async () => {
    setGitHubBusy(true);
    setGitHubError(null);
    try {
      const response = await apiClient.post<{
        ok: boolean;
        status: string;
        account: { login: string; name?: string | null; html_url?: string | null };
      }>(API_ENDPOINTS.connectors.github.test, {}, { retries: 0 });
      setGitHubConnection((current) => current ? {
        ...current,
        connected: true,
        status: response.status,
        account: response.account.login,
      } : current);
      toast.success(`GitHub verified for ${response.account.login}.`);
    } catch (error) {
      setGitHubError(error instanceof Error ? error.message : 'GitHub connection verification failed.');
    } finally {
      setGitHubBusy(false);
    }
  };

  const loadGitHubRepositories = async (page = 1) => {
    setGitHubBusy(true);
    setGitHubError(null);
    try {
      const response = await apiClient.get<{ repositories: GitHubRepository[]; has_next_page: boolean }>(
        API_ENDPOINTS.connectors.github.repositories(page),
      );
      setGitHubRepositories(response.repositories);
      setGitHubPage(page);
      setGitHubHasNextPage(response.has_next_page);
      setSelectedGitHubRepository(null);
      setGitHubFile(null);
    } catch (error) {
      setGitHubError(error instanceof Error ? error.message : 'GitHub repositories could not be loaded.');
    } finally {
      setGitHubBusy(false);
    }
  };

  const inspectGitHubRepository = async (repository: GitHubRepository) => {
    setGitHubBusy(true);
    setGitHubError(null);
    try {
      const [owner, name] = repository.full_name.split('/', 2);
      if (!owner || !name) throw new Error('GitHub returned a repository with an invalid name.');
      const details = await apiClient.get<GitHubRepository>(
        API_ENDPOINTS.connectors.github.repository(owner, name),
      );
      setSelectedGitHubRepository(details);
      setGitHubFile(null);
    } catch (error) {
      setGitHubError(error instanceof Error ? error.message : 'Repository inspection failed.');
    } finally {
      setGitHubBusy(false);
    }
  };

  const readGitHubFile = async () => {
    if (!selectedGitHubRepository || !githubFilePath.trim()) return;
    setGitHubBusy(true);
    setGitHubError(null);
    try {
      const [owner, name] = selectedGitHubRepository.full_name.split('/', 2);
      if (!owner || !name) throw new Error('Selected repository name is invalid.');
      const file = await apiClient.get<GitHubFile>(
        API_ENDPOINTS.connectors.github.file(owner, name, githubFilePath.trim()),
      );
      setGitHubFile(file);
    } catch (error) {
      setGitHubFile(null);
      setGitHubError(error instanceof Error ? error.message : 'GitHub file read failed.');
    } finally {
      setGitHubBusy(false);
    }
  };

  const disconnectGitHub = async () => {
    if (!confirm('Remove the GitHub authorization stored for your account?')) return;
    setGitHubBusy(true);
    setGitHubError(null);
    try {
      await apiClient.delete(API_ENDPOINTS.connectors.github.disconnect);
      setGitHubConnection({
        provider: 'GitHub',
        connected: false,
        status: 'Authorization required',
        scopes: [],
        capabilities: [],
      });
      setGitHubRepositories([]);
      setSelectedGitHubRepository(null);
      setGitHubFile(null);
      toast.success('GitHub authorization removed.');
    } catch (error) {
      setGitHubError(error instanceof Error ? error.message : 'Could not disconnect GitHub.');
    } finally {
      setGitHubBusy(false);
    }
  };

  const email = connectors['email'];
  const isConfigured = !!email?.configured;
  const isEnabled = email?.enabled ?? true;

  const toggleEnabled = async (kind: string, on: boolean) => {
    try {
      await apiClient.patch(`/api/v1/connectors/${kind}`, { enabled: on });
      toast.success(`Connector ${on ? 'enabled' : 'disabled (kill switch)'}`);
      await load();
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  const testConnection = async () => {
    if (!config.imap_host || !config.imap_user || !(config.password && config.password !== MASK)) {
      toast.error('IMAP host, username, and app password are required to test');
      return;
    }
    setTesting(true);
    try {
      const res = await apiClient.post<TestResult>(`/api/v1/connectors/email/test`, {
        provider: config.provider || 'Other',
        imap_host: config.imap_host,
        imap_port: config.imap_port ?? 993,
        imap_ssl: config.imap_ssl ?? true,
        imap_user: config.imap_user,
        password: config.password,
        smtp_host: config.smtp_host || '',
        smtp_port: config.smtp_port ?? 587,
        smtp_starttls: config.smtp_starttls ?? true,
        send_from: config.send_from || '',
      });
      const ok = res.imap?.ok && (res.smtp ? res.smtp.ok : true);
      if (ok) {
        toast.success('Connection test passed');
      } else {
        // Surface the real reason instead of a bare "Connection test failed",
        // so IMAP/SMTP failures (e.g. STARTTLS/AUTH not negotiated) are visible.
        const parts = [res.message, res.imap?.message, res.smtp?.message].filter(Boolean);
        toast.error(`Connection test failed${parts.length ? `: ${parts.join(' | ')}` : ''}`);
      }
      await load();
    } catch (e: any) {
      toast.error(e.message || 'Test failed');
    } finally {
      setTesting(false);
    }
  };

  const saveConnection = async () => {
    if (!config.imap_host || !config.imap_user || !(config.password && config.password !== MASK)) {
      toast.error('IMAP host, username, and app password are required');
      return;
    }
    setSaving(true);
    try {
      if (isConfigured) {
        await apiClient.patch('/api/v1/connectors/email', {
          provider: config.provider,
          imap_host: config.imap_host,
          imap_port: config.imap_port,
          imap_ssl: config.imap_ssl,
          imap_user: config.imap_user,
          password: config.password !== MASK ? config.password : undefined,
          smtp_host: config.smtp_host,
          smtp_port: config.smtp_port,
          smtp_starttls: config.smtp_starttls,
          send_from: config.send_from,
          capabilities: config.capabilities,
          enabled: config.enabled,
        });
      } else {
        await apiClient.post('/api/v1/connectors/email', {
          provider: config.provider || 'Other',
          imap_host: config.imap_host,
          imap_port: config.imap_port ?? 993,
          imap_ssl: config.imap_ssl ?? true,
          imap_user: config.imap_user,
          password: config.password,
          smtp_host: config.smtp_host || '',
          smtp_port: config.smtp_port ?? 587,
          smtp_starttls: config.smtp_starttls ?? true,
          send_from: config.send_from || '',
          capabilities: config.capabilities || ['read', 'summarize', 'draft', 'send'],
          enabled: config.enabled ?? true,
        });
      }
      toast.success('Email connection saved');
      // Re-mask the password after save
      setConfig((c) => ({ ...c, password: MASK }));
      await load();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const deleteConnection = async () => {
    if (!confirm('Remove the email connection? Its credentials and audit entries are affected.')) return;
    try {
      await apiClient.delete('/api/v1/connectors/email');
      toast.success('Email connection removed');
      setConfig({});
      await load();
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  const setProvider = (provider: string) => {
    const d = PROVIDER_DEFAULTS[provider] || PROVIDER_DEFAULTS.Other;
    setConfig((c) => ({
      ...c, provider,
      imap_host: d.imap_host, imap_port: d.imap_port,
      smtp_host: d.smtp_host, smtp_port: d.smtp_port,
    }));
  };

  const toggleCapability = (cap: string) => {
    const cur = config.capabilities || [];
    setConfig({
      ...config,
      capabilities: cur.includes(cap) ? cur.filter((c) => c !== cap) : [...cur, cap],
    });
  };

  const statusBadge = () => {
    if (!isConfigured) return <Badge variant="secondary">Not configured</Badge>;
    if (!isEnabled) return <Badge variant="outline" className="text-red-400">Disabled (kill switch)</Badge>;
    if (email?.last_test_ok) return <Badge className="bg-emerald-500/20 text-emerald-400">Connected</Badge>;
    return <Badge variant="outline">Enabled</Badge>;
  };

  return (
    <div className="flex-1 space-y-6 p-6 pt-6 bg-grid">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="relative">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 via-cyan-400 to-blue-600 shadow-lg shadow-blue-500/30">
              <Shield className="h-7 w-7 text-white" />
            </div>
          </div>
          <div>
            <h1 className="text-3xl font-black bg-gradient-to-r from-blue-400 via-cyan-300 to-blue-400 bg-clip-text text-transparent">Connections</h1>
            <p className="text-sm text-muted-foreground/70 mt-0.5">
              Manage developer integrations that let JARVIS reach your external systems.
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </motion.div>

      {/* Global gate note */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
        <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border border-blue-500/20">
          <CardContent className="pt-6 flex items-start gap-4">
            <AlertCircle className="h-5 w-5 text-amber-400 mt-0.5 flex-shrink-0" />
            <div>
              <p className="font-semibold text-amber-300">Admin-managed integrations</p>
              <p className="text-sm text-muted-foreground/80 mt-1">
                Email connector settings are admin-managed. GitHub authorization is user-scoped OAuth; repository
                reads are audited and limited to permissions the provider grants.
              </p>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      <Card className="border-white/10 bg-gradient-to-br from-slate-950/90 to-slate-900/80">
        <CardHeader>
          <CardTitle className="flex items-center gap-3">
            <Github className="h-5 w-5 text-white" />
            GitHub account connection
          </CardTitle>
          <CardDescription>
            OAuth credentials stay server-side in the encrypted token vault. This surface supports verified account access,
            repository discovery, repository metadata, and file reads; it does not create branches or write repository content.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-white/10 bg-black/20 p-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">Authorization</span>
                {githubLoading
                  ? <Badge variant="outline">Loading</Badge>
                  : githubConnection?.connected
                    ? <Badge variant="outline">{githubConnection.status}</Badge>
                    : githubError
                      ? <Badge variant="destructive">Unavailable</Badge>
                      : <Badge variant="secondary">Authorization required</Badge>}
              </div>
              {githubConnection?.account && (
                <p className="text-xs text-muted-foreground">Account: {githubConnection.account}</p>
              )}
              {githubConnection?.expires_at && (
                <p className="text-xs text-muted-foreground">
                  Token expiration: {new Date(githubConnection.expires_at * 1000).toLocaleString()}
                </p>
              )}
              <div className="flex flex-wrap gap-1 pt-1">
                {githubConnection?.scopes.map((scope) => (
                  <Badge key={scope} variant="outline" className="font-mono text-[10px]">{scope}</Badge>
                ))}
                {githubConnection?.scopes.length === 0 && githubConnection?.connected && (
                  <span className="text-xs text-amber-200">GitHub did not report OAuth scopes.</span>
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={connectGitHub} disabled={githubBusy || githubLoading}>
                <ExternalLink className="mr-2 h-4 w-4" />
                {githubConnection?.connected ? 'Reauthorize' : 'Authorize GitHub'}
              </Button>
              <Button size="sm" variant="outline" onClick={verifyGitHub} disabled={!githubConnection?.connected || githubBusy}>
                {githubBusy ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : <TestTube className="mr-2 h-4 w-4" />}
                Verify
              </Button>
              <Button size="sm" variant="outline" onClick={() => void loadGitHubRepositories(1)} disabled={!githubConnection?.connected || githubBusy}>
                <Search className="mr-2 h-4 w-4" />
                Repositories
              </Button>
              {githubConnection?.connected && (
                <Button size="sm" variant="destructive" onClick={disconnectGitHub} disabled={githubBusy}>
                  <Trash2 className="mr-2 h-4 w-4" />
                  Disconnect
                </Button>
              )}
            </div>
          </div>

          {githubError && (
            <p role="alert" className="rounded-md border border-rose-400/20 bg-rose-400/5 p-3 text-sm text-rose-200">
              {githubError}
            </p>
          )}

          {githubRepositories.length > 0 && (
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Authorized repositories</p>
                <div className="max-h-72 space-y-2 overflow-y-auto">
                  {githubRepositories.map((repository) => (
                    <button
                      type="button"
                      key={repository.id}
                      onClick={() => void inspectGitHubRepository(repository)}
                      className={`w-full rounded-lg border p-3 text-left transition-colors hover:border-cyan-300/30 ${
                        selectedGitHubRepository?.id === repository.id ? 'border-cyan-300/40 bg-cyan-300/5' : 'border-white/10 bg-black/20'
                      }`}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-medium">{repository.full_name}</span>
                        <Badge variant="outline">{repository.private ? 'Private' : 'Public'}</Badge>
                      </span>
                      <span className="mt-1 block truncate text-xs text-muted-foreground">
                        {repository.description || `Default branch: ${repository.default_branch}`}
                      </span>
                    </button>
                  ))}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Page {githubPage}</span>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" disabled={githubPage <= 1 || githubBusy} onClick={() => void loadGitHubRepositories(githubPage - 1)}>Previous</Button>
                    <Button size="sm" variant="outline" disabled={!githubHasNextPage || githubBusy} onClick={() => void loadGitHubRepositories(githubPage + 1)}>Next</Button>
                  </div>
                </div>
              </div>

              {selectedGitHubRepository && (
                <div className="space-y-3 rounded-lg border border-white/10 bg-black/20 p-4">
                  <div>
                    <p className="font-medium">{selectedGitHubRepository.full_name}</p>
                    <a href={selectedGitHubRepository.html_url} target="_blank" rel="noreferrer" className="text-xs text-cyan-300 hover:underline">
                      Open on GitHub <ExternalLink className="inline h-3 w-3" />
                    </a>
                  </div>
                  <div className="flex gap-2">
                    <Input
                      value={githubFilePath}
                      onChange={(event) => setGitHubFilePath(event.target.value)}
                      placeholder="Repository file path"
                      aria-label="GitHub repository file path"
                    />
                    <Button onClick={() => void readGitHubFile()} disabled={!githubFilePath.trim() || githubBusy}>Read file</Button>
                  </div>
                  {githubFile && (
                    <div className="space-y-2">
                      <p className="text-xs text-muted-foreground">
                        {githubFile.path} · {githubFile.size} bytes · SHA {githubFile.sha}
                      </p>
                      {githubFile.binary
                        ? <p role="status" className="text-sm text-muted-foreground">Binary file; content is not rendered in the browser.</p>
                        : <pre className="max-h-80 overflow-auto rounded border border-white/10 bg-black/40 p-3 text-xs">{githubFile.content ?? 'GitHub returned no UTF-8 text content.'}</pre>}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
          {githubRepositories.length === 0 && githubConnection?.connected && (
            <p role="status" className="text-sm text-muted-foreground">
              {githubBusy ? 'Loading authorized repository data…' : 'Choose Repositories to query GitHub using the current account authorization.'}
            </p>
          )}
          <p className="text-xs text-muted-foreground/70">
            Only Repository.Read is exposed here. GitHub write operations, branch creation, commits, and pull requests are unavailable until separately authorized and implemented.
          </p>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* ── Connector summary cards ── */}
        <div className="xl:col-span-1 space-y-4">
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
            <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border border-white/10">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-white">
                  <Mail className="h-5 w-5 text-blue-400" />
                  Email (IMAP + SMTP)
                </CardTitle>
                <CardDescription>Read, search, draft, and send email on your behalf.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {statusBadge()}
                {email?.last_tested_at && (
                  <p className="text-xs text-muted-foreground/60">
                    Last tested {new Date(email.last_tested_at).toLocaleString()}
                  </p>
                )}
                <div className="flex gap-2 pt-2">
                  <Button size="sm" variant="outline" onClick={testConnection} disabled={testing}>
                    {testing ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <TestTube className="h-4 w-4 mr-2" />}
                    Test
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setEditing('email')} disabled={!isConfigured && !email?.configured}>
                    <Edit3 className="h-4 w-4 mr-2" />Configure
                  </Button>
                  {isConfigured && (
                    <Button size="sm" variant="destructive" onClick={deleteConnection}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          </motion.div>

          {/* Kill switch card */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
            <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border border-white/10">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-white">
                  <Power className="h-5 w-5 text-amber-400" />
                  Global Kill Switch
                </CardTitle>
                <CardDescription>Disables every connector action at dispatch time until re-enabled.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <Label>Connectors active</Label>
                  <Switch checked={isEnabled} onCheckedChange={(v) => toggleEnabled('email', v)} />
                </div>
              </CardContent>
            </Card>
          </motion.div>
        </div>

        {/* ── Email configuration form ── */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="xl:col-span-2">
          <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border border-blue-500/30">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <Settings className="h-5 w-5 text-cyan-400" />
                Email Configuration
              </CardTitle>
              <CardDescription>
                Enter an app password (not your account password). Gmail/Outlook/Apple require an app-specific
                password; credentials are encrypted at rest with Fernet, keyed off <code>JARVIS_SECRET_KEY</code>.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Provider */}
              <div className="space-y-2">
                <Label>Provider</Label>
                <Select value={config.provider || 'Other'} onValueChange={setProvider}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.keys(PROVIDER_DEFAULTS).map((p) => (
                      <SelectItem key={p} value={p}>{p}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* IMAP block */}
              <div className="p-4 rounded-lg bg-slate-800/50 border border-blue-500/10 space-y-4">
                <p className="text-xs font-semibold uppercase text-muted-foreground/60">IMAP (read)</p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="space-y-2 md:col-span-2">
                    <Label>IMAP Host</Label>
                    <Input value={config.imap_host || ''} onChange={(e) => setConfig({ ...config, imap_host: e.target.value })}
                      placeholder="imap.gmail.com" />
                  </div>
                  <div className="space-y-2">
                    <Label>Port</Label>
                    <Input type="number" value={config.imap_port ?? 993}
                      onChange={(e) => setConfig({ ...config, imap_port: parseInt(e.target.value) || 993 })} />
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="flex items-center justify-between p-3 rounded-lg bg-slate-800/40 border border-white/5">
                  <Label htmlFor="imap-ssl" className="text-sm">Use SSL/TLS (port 993)</Label>
                  <Switch id="imap-ssl" checked={config.imap_ssl ?? true}
                    onCheckedChange={(v) => setConfig({ ...config, imap_ssl: v })} />
                </div>
                  <div className="space-y-1">
                    <Label>Username (email address)</Label>
                    <Input value={config.imap_user || ''} onChange={(e) => setConfig({ ...config, imap_user: e.target.value })}
                      placeholder="you@gmail.com" />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>App Password</Label>
                  <Input type="password" value={config.password || ''}
                    onChange={(e) => setConfig({ ...config, password: e.target.value })}
                    placeholder={isConfigured ? MASK : 'App-specific password'} />
                  {isConfigured && (
                    <p className="text-xs text-muted-foreground/60">
                      Leave as {MASK} to keep the saved password. Enter a new value to replace it.
                    </p>
                  )}
                </div>
              </div>

              {/* SMTP block */}
              <div className="p-4 rounded-lg bg-slate-800/50 border border-emerald-500/10 space-y-4">
                <p className="text-xs font-semibold uppercase text-muted-foreground/60">SMTP (send)</p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="space-y-2 md:col-span-2">
                    <Label>SMTP Host</Label>
                    <Input value={config.smtp_host || ''} onChange={(e) => setConfig({ ...config, smtp_host: e.target.value })}
                      placeholder="smtp.gmail.com" />
                  </div>
                  <div className="space-y-2">
                    <Label>Port</Label>
                    <Input type="number" value={config.smtp_port ?? 587}
                      onChange={(e) => setConfig({ ...config, smtp_port: parseInt(e.target.value) || 587 })} />
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-end">
                  <div className="flex items-center justify-between p-3 rounded-lg bg-slate-800/40 border border-white/5">
                    <Label htmlFor="smtp-starttls" className="text-sm">Use STARTTLS (port 587)</Label>
                    <Switch id="smtp-starttls" checked={config.smtp_starttls ?? true}
                      onCheckedChange={(v) => setConfig({ ...config, smtp_starttls: v })} />
                  </div>
                  <div className="space-y-1">
                    <Label>Send From</Label>
                    <Input value={config.send_from || ''} onChange={(e) => setConfig({ ...config, send_from: e.target.value })}
                      placeholder="you@gmail.com" />
                  </div>
                </div>
              </div>

              {/* Capability toggles */}
              <div className="space-y-3">
                <Label className="text-sm font-semibold">What the AI may do (consent toggles)</Label>
                <p className="text-xs text-muted-foreground/60">
                  Revoking a capability blocks the matching action immediately at dispatch time.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                  {(['read', 'summarize', 'draft', 'send'] as const).map((cap) => {
                    const meta = CAP_LABELS[cap];
                    const Icon = meta.icon;
                    const on = config.capabilities?.includes(cap) ?? true;
                    return (
                      <div key={cap} className="flex items-center justify-between p-3 rounded-lg bg-slate-800/40 border border-white/5">
                        <div className="flex items-center gap-2">
                          <Icon className={`h-4 w-4 ${meta.color}`} />
                          <span className="text-sm text-white">{meta.label}</span>
                        </div>
                        <Switch checked={on} onCheckedChange={(v) => toggleCapability(cap)} />
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex gap-3 pt-2">
                <Button onClick={testConnection} disabled={testing}>
                  {testing ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <TestTube className="h-4 w-4 mr-2" />}
                  {testing ? 'Testing…' : 'Test Connection'}
                </Button>
                <Button onClick={saveConnection} disabled={saving || !config.imap_host || !config.imap_user} variant="default">
                  {saving ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : (isConfigured ? <Save className="h-4 w-4 mr-2" /> : <Lock className="h-4 w-4 mr-2" />)}
                  {saving ? 'Saving…' : isConfigured ? 'Update Connection' : 'Save Connection'}
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* ── Audit activity feed ── */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
        <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border border-white/10">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-white">
              <Activity className="h-5 w-5 text-cyan-400" />
              Activity Feed
            </CardTitle>
            <CardDescription>Every connector action by the AI or an admin, in order.</CardDescription>
          </CardHeader>
          <CardContent>
            {activity.length === 0 ? (
              <p className="text-sm text-muted-foreground/50">No activity yet.</p>
            ) : (
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {activity.map((e, i) => {
                  const ok = e.ok;
                  const icon = ok ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <XCircle className="h-4 w-4 text-red-400" />;
                  return (
                    <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-slate-800/40 border border-white/5">
                      {icon}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-white">{e.actor}</span>
                          <Badge variant={ok ? 'default' : 'destructive'} className="text-xs">
                            {e.action}
                          </Badge>
                          {e.kind && <Badge variant="outline" className="text-xs">{e.kind}</Badge>}
                        </div>
                        {e.error && <p className="text-xs text-red-300/80 mt-1 break-words">{e.error}</p>}
                        <p className="text-[10px] text-muted-foreground/50 mt-1 flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {e.ts ? new Date(e.ts).toLocaleString() : ''}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
