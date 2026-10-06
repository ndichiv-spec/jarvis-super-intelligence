'use client';

import { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Mail, Shield, CheckCircle2, XCircle, AlertCircle,
  Save, TestTube, Trash2, Settings, Power, Activity, RefreshCw,
  Edit3, Lock, Send, Search, FileText, Clock,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { API_ENDPOINTS } from '@/config/api';
import { apiClient } from '@/lib/api-client';
import { ServiceConnections } from '@/components/connections/service-connections';

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
  account?: string;
  connection_status?: string | null;
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

interface ConnectorRecord extends ConnectorConfig {
  kind: string;
  config?: ConnectorConfig;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function oauthProviderName(provider: string | null): string | null {
  switch (provider?.toLowerCase()) {
    case 'gmail':
    case 'google':
      return 'Google';
    case 'outlook':
    case 'microsoft':
      return 'Microsoft';
    default:
      return null;
  }
}

function oauthErrorMessage(error: string, provider: string | null): string {
  const providerName = oauthProviderName(provider);
  const subject = providerName ? `${providerName} authorization` : 'Provider authorization';
  switch (error) {
    case 'access_denied':
      return `${subject} was declined. No provider connection was added.`;
    case 'invalid_state':
      return `${subject} could not be verified. Please start the connection again.`;
    case 'not_configured':
    case 'configuration_missing':
      return `${subject} is not configured by an administrator yet.`;
    case 'exchange_failed':
      return `${subject} could not be completed. Please try again or contact an administrator.`;
    default:
      return `${subject} could not be completed. Please try again or contact an administrator.`;
  }
}

function formatTimestamp(timestamp?: string): string {
  if (!timestamp) return 'Time not reported';
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? 'Time not reported' : date.toLocaleString();
}

export default function ConnectionsPage() {
  const [connectors, setConnectors] = useState<Record<string, ConnectorConfig>>({});
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<ConnectorConfig>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [oauthLoading, setOauthLoading] = useState<string | null>(null);
  const [activity, setActivity] = useState<AuditEntry[]>([]);
  const [activityLoading, setActivityLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activityError, setActivityError] = useState<string | null>(null);

  const loadActivity = useCallback(async () => {
    setActivityLoading(true);
    setActivityError(null);
    try {
      const res = await apiClient.get<{ entries: AuditEntry[] }>('/api/v1/connectors/activity');
      setActivity(res.entries || []);
    } catch (error: unknown) {
      setActivityError(errorMessage(error, 'Could not load connector activity.'));
    } finally {
      setActivityLoading(false);
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await apiClient.get<{ connectors: ConnectorRecord[] }>('/api/v1/connectors');
      const map: Record<string, ConnectorConfig> = {};
      (res.connectors || []).forEach((connector) => {
        map[connector.kind] = { ...connector, ...(connector.config || {}) };
      });
      setConnectors(map);
      const email = map['email'];
      if (email) setConfig(email);
      await loadActivity();
    } catch (error: unknown) {
      setLoadError(errorMessage(error, 'Could not load connector configuration.'));
      setActivityLoading(false);
      toast.error(`Failed to load connectors: ${errorMessage(error, 'Unknown error')}`);
    } finally {
      setLoading(false);
    }
  }, [loadActivity]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => { void load(); });
    return () => window.cancelAnimationFrame(frame);
  }, [load]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const connected = params.get('connected');
    const oauthError = params.get('oauth_error');
    const provider = oauthProviderName(params.get('provider') || connected);
    const recognizedConnection = connected === 'gmail' || connected === 'outlook';
    const verificationFailed = recognizedConnection && params.get('verification') === 'failed';
    if (verificationFailed) {
      const providerName = oauthProviderName(connected) || 'Provider';
      toast.warning(
        `${providerName} authorization completed, but the read-only verification probe failed. The account may be authorized; check its connection status and retry verification.`,
      );
    } else if (recognizedConnection) {
      toast.success(`${provider || 'Provider'} account connected`);
    }
    if (oauthError) toast.error(oauthErrorMessage(oauthError, provider ? (params.get('provider') || connected) : null));
    if (connected || oauthError || params.has('verification') || params.has('provider')) {
      for (const key of ['connected', 'oauth_error', 'verification', 'provider']) params.delete(key);
      const remainingQuery = params.toString();
      window.history.replaceState(
        {},
        '',
        `${window.location.pathname}${remainingQuery ? `?${remainingQuery}` : ''}${window.location.hash}`,
      );
    }
  }, []);

  const email = connectors['email'];
  const isConfigured = !!email?.configured;
  const isEnabled = (isConfigured ? email?.enabled : config.enabled) === true;
  const connectedProviderCount = ['gmail', 'outlook'].filter((kind) => (
    connectors[kind]?.configured && connectors[kind]?.connection_status === 'Connected'
  )).length;
  const emailReady = email?.configured === true && email.enabled === true && email.last_test_ok === true;
  const attentionCount = Number(!emailReady)
    + ['gmail', 'outlook'].filter((kind) => !(
      connectors[kind]?.configured && connectors[kind]?.connection_status === 'Connected'
    )).length;

  const toggleEnabled = async (kind: string, on: boolean) => {
    if (kind === 'email' && !isConfigured) {
      setConfig((current) => ({ ...current, enabled: on }));
      return;
    }
    try {
      await apiClient.patch(`/api/v1/connectors/${kind}`, { enabled: on });
      toast.success(`Connector ${on ? 'enabled' : 'disabled (kill switch)'}`);
      await load();
    } catch (error: unknown) {
      toast.error(errorMessage(error, 'Could not update connector'));
    }
  };

  const testConnection = async () => {
    const freshPassword = Boolean(config.password && config.password !== MASK);
    if (!config.imap_host || !config.imap_user || (!isConfigured && !freshPassword)) {
      toast.error('IMAP host, username, and an app password are required to test');
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
        password: freshPassword ? config.password : '',
        smtp_host: config.smtp_host || '',
        smtp_port: config.smtp_port ?? 587,
        smtp_starttls: config.smtp_starttls ?? true,
        send_from: config.send_from || '',
      });
      const ok = res.ok ?? (res.imap?.ok === true && (res.smtp ? res.smtp.ok === true : true));
      if (ok) {
        toast.success('Connection test passed');
      } else {
        // Surface the real reason instead of a bare "Connection test failed",
        // so IMAP/SMTP failures (e.g. STARTTLS/AUTH not negotiated) are visible.
        const parts = [res.message, res.imap?.message, res.smtp?.message].filter(Boolean);
        toast.error(`Connection test failed${parts.length ? `: ${parts.join(' | ')}` : ''}`);
      }
      await load();
    } catch (error: unknown) {
      toast.error(errorMessage(error, 'Test failed'));
    } finally {
      setTesting(false);
    }
  };

  const saveConnection = async () => {
    const freshPassword = Boolean(config.password && config.password !== MASK);
    if (!config.imap_host || !config.imap_user || (!isConfigured && !freshPassword)) {
      toast.error('IMAP host, username, and an app password are required');
      return;
    }
    if (!isConfigured && (config.capabilities || []).length === 0) {
      toast.error('Choose at least one email capability to grant before saving. The email API enables all capabilities if none are selected.');
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
          capabilities: config.capabilities ?? [],
          enabled: config.enabled ?? false,
        });
      }
      toast.success('Email connection saved');
      // Re-mask the password after save
      setConfig((c) => ({ ...c, password: MASK }));
      await load();
    } catch (error: unknown) {
      toast.error(errorMessage(error, 'Could not save email connection'));
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
    } catch (error: unknown) {
      toast.error(errorMessage(error, 'Could not remove email connection'));
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

  const connectOAuth = async (kind: 'gmail' | 'outlook') => {
    const providerName = kind === 'gmail' ? 'Google' : 'Microsoft';
    if (!window.confirm(`Continue to ${providerName} to review and approve the access requested for JARVIS? You can cancel before granting access.`)) return;
    setOauthLoading(kind);
    try {
      const response = await apiClient.post<{ authorize_url: string }>(
        API_ENDPOINTS.connectors.oauthAuthorize(kind),
      );
      window.location.assign(response.authorize_url);
    } catch {
      toast.error(`Could not start ${providerName} authorization. Check the administrator OAuth configuration and try again.`);
      setOauthLoading(null);
    }
  };

  const disconnectOAuth = async (kind: 'gmail' | 'outlook') => {
    const providerName = kind === 'gmail' ? 'Google' : 'Microsoft';
    if (!confirm(`Remove the ${providerName} OAuth credentials stored by JARVIS? You may also need to revoke the app's grant in your ${providerName} account settings.`)) return;
    setOauthLoading(kind);
    try {
      await apiClient.delete(API_ENDPOINTS.connectors.oauthDisconnect(kind));
      toast.success(`${providerName} credentials removed from JARVIS`);
      await load();
    } catch (e: unknown) {
      toast.error(errorMessage(e, `Could not disconnect ${kind}`));
    } finally {
      setOauthLoading(null);
    }
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
    if (email?.enabled === false) return <Badge variant="outline" className="text-red-400">Disabled (kill switch)</Badge>;
    if (email?.enabled !== true) return <Badge variant="outline">State unavailable</Badge>;
    if (email?.last_test_ok === true) return <Badge className="bg-emerald-500/20 text-emerald-400">Test passed</Badge>;
    if (email?.last_test_ok === false) return <Badge variant="destructive">Last test failed</Badge>;
    return <Badge variant="outline">Not tested</Badge>;
  };

  return (
    <div className="w-full min-w-0 max-w-full space-y-6 overflow-x-clip bg-grid p-4 pt-6 sm:p-6">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} className="flex min-w-0 flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-3 sm:gap-4">
          <div className="relative">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 via-cyan-400 to-blue-600 shadow-lg shadow-blue-500/30">
              <Shield className="h-7 w-7 text-white" />
            </div>
          </div>
          <div className="min-w-0">
            <h1 className="text-3xl font-black bg-gradient-to-r from-blue-400 via-cyan-300 to-blue-400 bg-clip-text text-transparent">Connections</h1>
            <p className="mt-0.5 break-words text-sm text-muted-foreground/70">
              Admin-managed integrations. Provider access requires consent; email sending requires a separate SMTP setup.
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" className="shrink-0" onClick={load} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </motion.div>

      {loadError && (
        <div role="alert" className="flex flex-col gap-3 border border-rose-400/30 bg-rose-950/20 p-4 text-sm text-rose-200 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-medium">Connector configuration is unavailable.</p>
            <p className="mt-1 text-xs text-rose-200/75">{loadError}</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
            {loading && <RefreshCw className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
            Retry
          </Button>
        </div>
      )}

      <ServiceConnections />

      <section aria-labelledby="connection-readiness-title" className="min-w-0 overflow-hidden border border-cyan-300/15 bg-slate-950/70">
        <div className="flex flex-col gap-1 border-b border-white/5 px-5 py-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 id="connection-readiness-title" className="text-base font-semibold text-slate-100">Connection readiness</h2>
            <p className="text-xs text-slate-400">OAuth authorization and outbound email are separate connections.</p>
          </div>
          <span className="text-xs text-slate-500">
            {loading
              ? (Object.keys(connectors).length ? 'Refreshing · previous values may be stale' : 'Checking live status…')
              : loadError
                ? (Object.keys(connectors).length ? 'Refresh failed · showing last known values' : 'Live status unavailable')
                : 'Status reported by the connectors API'}
          </span>
        </div>
        <div className="grid min-w-0 grid-cols-1 divide-y divide-white/5 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          <div className="px-5 py-4">
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Configured integrations</p>
            <p className="mt-1 text-xl font-semibold text-slate-100">
              {loading ? 'Checking…' : loadError ? 'Unavailable' : `${['email', 'gmail', 'outlook'].filter((kind) => connectors[kind]?.configured).length} / 3`}
            </p>
          </div>
          <div className="px-5 py-4">
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Provider authorization</p>
            <p className="mt-1 text-xl font-semibold text-slate-100">
              {loading ? 'Checking…' : loadError ? 'Unavailable' : `${connectedProviderCount} / 2 authorized`}
            </p>
          </div>
          <div className="px-5 py-4">
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Needs attention</p>
            <p className={`mt-1 text-xl font-semibold ${attentionCount ? 'text-amber-300' : 'text-emerald-300'}`}>
              {loading ? 'Checking…' : loadError ? 'Unavailable' : attentionCount === 0 ? 'None' : `${attentionCount} connection${attentionCount === 1 ? '' : 's'}`}
            </p>
          </div>
        </div>
        {!loading && !loadError && Object.keys(connectors).length === 0 && (
          <p className="border-t border-white/5 px-5 py-3 text-sm text-slate-400">
            The API reports no configured connectors yet. Set up a provider below to begin.
          </p>
        )}
      </section>

      <div className="grid min-w-0 grid-cols-1 gap-4 md:grid-cols-2">
        {([
          { kind: 'gmail', name: 'Google / Gmail', description: 'Authorize JARVIS with Google OAuth. JARVIS never asks for your Google password.' },
          { kind: 'outlook', name: 'Microsoft Outlook', description: 'Authorize JARVIS with Microsoft OAuth. JARVIS never asks for your Microsoft password.' },
        ] as const).map(({ kind, name, description }) => {
          const connection = connectors[kind];
          const connected = connection?.configured && connection.connection_status === 'Connected';
          const providerStatus = loading
            ? 'Refreshing'
            : loadError
              ? 'Unavailable'
              : connected
                ? 'Connected'
                : connection?.configured
                  ? 'Status unknown'
                  : 'Authorization required';
          return (
            <Card key={kind} className="min-w-0 border border-white/10 bg-slate-950/75">
              <CardHeader>
                <CardTitle className="flex items-center justify-between gap-3 text-white">
                  <span className="flex min-w-0 items-center gap-2 break-words"><Mail className="h-5 w-5 shrink-0 text-blue-400" />{name}</span>
                  <Badge variant={connected ? 'default' : 'secondary'}>{providerStatus}</Badge>
                </CardTitle>
                <CardDescription>{description}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {connection?.account && (
                  <p className="text-sm text-muted-foreground">Authorized account: {connection.account}</p>
                )}
                {connection?.capabilities && connection.capabilities.length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    Reported capabilities: {connection.capabilities.join(', ')}
                  </p>
                )}
                <p className="text-xs text-muted-foreground">
                  {connection?.configured
                    ? 'JARVIS stores OAuth tokens encrypted on the backend. Sending mail remains confirmation-gated.'
                    : 'Requires an administrator-configured OAuth client and your consent at the provider.'}
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    onClick={() => void connectOAuth(kind)}
                    disabled={oauthLoading !== null || loading || !!loadError}
                  >
                    {oauthLoading === kind ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : <Lock className="mr-2 h-4 w-4" />}
                    {connection?.configured ? 'Reconnect account' : 'Connect account'}
                  </Button>
                  {connection?.configured && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void disconnectOAuth(kind)}
                      disabled={oauthLoading !== null || loading}
                    >
                      Remove from JARVIS
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
        <Card className="border border-white/10 bg-[#0d151c]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-slate-100">
              <Shield className="h-5 w-5 text-cyan-300" />
              Outbound email identity
            </CardTitle>
            <CardDescription>The configured SMTP sender is used for mail actions; JARVIS does not invent a developer address.</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-200">
              {email?.configured
                ? email.send_from || 'Sender address is not reported by the configured connector.'
                : loadError
                  ? 'Outbound identity status is unavailable.'
                  : 'No outbound email identity is configured.'}
            </p>
            <p className="mt-2 text-xs leading-5 text-slate-500">
              Provider sign-in results are shown in JARVIS notifications. Email notifications require a configured sender and are not implied by this account setting.
            </p>
          </CardContent>
        </Card>
      </motion.div>

      {/* Global gate note */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
        <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border border-blue-500/20">
          <CardContent className="pt-6 flex items-start gap-4">
            <AlertCircle className="h-5 w-5 text-amber-400 mt-0.5 flex-shrink-0" />
            <div>
              <p className="font-semibold text-amber-300">Integration access and controls</p>
              <p className="text-sm text-muted-foreground/80 mt-1">
              Integrations require administrator configuration and explicit provider consent. Email setup is separate
              from OAuth access; current connection state and activity are shown only when reported by the connectors API.
              </p>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      <div className="grid min-w-0 grid-cols-1 gap-6 xl:grid-cols-3">
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
                  <Button size="sm" variant="outline" onClick={testConnection} disabled={testing || loading || !!loadError}>
                    {testing ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <TestTube className="h-4 w-4 mr-2" />}
                    Test
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      const heading = document.getElementById('email-configuration-title');
                      heading?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                      heading?.focus();
                    }}
                    disabled={loading || !!loadError}
                  >
                    <Edit3 className="h-4 w-4 mr-2" />Configure
                  </Button>
                  {isConfigured && (
                    <Button
                      size="sm"
                      variant="destructive"
                      aria-label="Remove email connection"
                      onClick={deleteConnection}
                      disabled={loading || !!loadError}
                    >
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
                <CardTitle id="email-configuration-title" tabIndex={-1} className="flex items-center gap-2 text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400">
                  <Power className="h-5 w-5 text-amber-400" />
                  Email Connector Switch
                </CardTitle>
                <CardDescription>Enables or disables this email connector at dispatch time.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <Label htmlFor="email-actions-active">Email actions active</Label>
                  <Switch
                    id="email-actions-active"
                    aria-label="Email actions active"
                    checked={isEnabled}
                    disabled={loading || !!loadError || (email?.configured === true && email.enabled === undefined)}
                    onCheckedChange={(v) => toggleEnabled('email', v)}
                  />
                </div>
              </CardContent>
            </Card>
          </motion.div>
        </div>

        {/* ── Email configuration form ── */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="min-w-0 xl:col-span-2">
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
                <Label htmlFor="email-provider">Provider</Label>
                <Select value={config.provider || 'Other'} onValueChange={setProvider}>
                  <SelectTrigger id="email-provider"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.keys(PROVIDER_DEFAULTS).map((p) => (
                      <SelectItem key={p} value={p}>{p}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* IMAP block */}
              <div className="min-w-0 p-4 rounded-lg bg-slate-800/50 border border-blue-500/10 space-y-4">
                <p className="text-xs font-semibold uppercase text-muted-foreground/60">IMAP (read)</p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="imap-host">IMAP Host</Label>
                    <Input id="imap-host" value={config.imap_host || ''} onChange={(e) => setConfig({ ...config, imap_host: e.target.value })}
                      placeholder="imap.gmail.com" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="imap-port">IMAP port</Label>
                    <Input id="imap-port" type="number" value={config.imap_port ?? 993}
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
                    <Label htmlFor="imap-user">Username (email address)</Label>
                    <Input id="imap-user" value={config.imap_user || ''} onChange={(e) => setConfig({ ...config, imap_user: e.target.value })}
                      placeholder="you@gmail.com" />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="imap-password">App Password</Label>
                  <Input id="imap-password" type="password" value={config.password || ''}
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
              <div className="min-w-0 p-4 rounded-lg bg-slate-800/50 border border-emerald-500/10 space-y-4">
                <p className="text-xs font-semibold uppercase text-muted-foreground/60">SMTP (send)</p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="smtp-host">SMTP Host</Label>
                    <Input id="smtp-host" value={config.smtp_host || ''} onChange={(e) => setConfig({ ...config, smtp_host: e.target.value })}
                      placeholder="smtp.gmail.com" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="smtp-port">SMTP port</Label>
                    <Input id="smtp-port" type="number" value={config.smtp_port ?? 587}
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
                    <Label htmlFor="send-from">Send From</Label>
                    <Input id="send-from" value={config.send_from || ''} onChange={(e) => setConfig({ ...config, send_from: e.target.value })}
                      placeholder="you@gmail.com" />
                  </div>
                </div>
              </div>

              {/* Capability toggles */}
              <div className="space-y-3">
                <h3 className="text-sm font-semibold">What the AI may do (consent toggles)</h3>
                <p className="text-xs text-muted-foreground/60">
                  Capabilities not explicitly enabled by you or reported by the API stay off. Choose at least one to create an email connection.
                </p>
                <div className="grid min-w-0 grid-cols-1 gap-3 pt-1 sm:grid-cols-2">
                  {(['read', 'summarize', 'draft', 'send'] as const).map((cap) => {
                    const meta = CAP_LABELS[cap];
                    const Icon = meta.icon;
                    const on = config.capabilities?.includes(cap) ?? false;
                    const controlId = `email-capability-${cap}`;
                    return (
                      <div key={cap} className="flex items-center justify-between p-3 rounded-lg bg-slate-800/40 border border-white/5">
                        <Label htmlFor={controlId} className="flex min-w-0 cursor-pointer items-center gap-2">
                          <Icon className={`h-4 w-4 ${meta.color}`} />
                          <span className="break-words text-sm text-white">{meta.label}</span>
                        </Label>
                        <Switch id={controlId} aria-label={`${meta.label} capability`} checked={on} onCheckedChange={() => toggleCapability(cap)} />
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex flex-wrap gap-3 pt-2">
                <Button onClick={testConnection} disabled={testing || loading || !!loadError}>
                  {testing ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <TestTube className="h-4 w-4 mr-2" />}
                  {testing ? 'Testing…' : 'Test Connection'}
                </Button>
                <Button onClick={saveConnection} disabled={saving || loading || !!loadError || !config.imap_host || !config.imap_user} variant="default">
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
            {loadError ? (
              <p role="status" className="text-sm text-muted-foreground">
                Activity is unavailable because connector status could not be refreshed.
              </p>
            ) : loading || activityLoading ? (
              <p role="status" className="text-sm text-muted-foreground">Loading recent connector activity…</p>
            ) : activityError ? (
              <p role="alert" className="text-sm text-rose-200">Activity unavailable: {activityError}</p>
            ) : activity.length === 0 ? (
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
                          {formatTimestamp(e.ts)}
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
