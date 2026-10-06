'use client';

import { type FormEvent, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Activity, ArrowRight, ExternalLink, Globe2, Loader2, Mail, MessageSquareText,
  Send, ShieldCheck,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { API_ENDPOINTS } from '@/config/api';
import apiClient from '@/lib/api-client';

interface ConnectorStatus {
  kind: string;
  configured?: boolean;
  enabled?: boolean;
  connected?: boolean;
  last_test_ok?: boolean;
  connection_status?: string;
  capabilities?: string[];
}

interface ConnectorListResponse {
  connectors?: ConnectorStatus[];
}

interface ConnectorActionResponse {
  ok?: boolean;
  error?: string;
  confirmation_required?: boolean;
}

const LOCAL_ACTIONS = [
  { label: 'Workspace overview', description: 'Return to the main JARVIS workbench.', route: '/dashboard' },
  { label: 'Runtime status', description: 'View live platform health and readiness.', route: '/dashboard/runtime-status' },
  { label: 'Search & research', description: 'Search connected sources and seed a research session.', route: '/dashboard/search' },
  { label: 'Knowledge Studio', description: 'Browse and manage saved knowledge entries.', route: '/dashboard/knowledge' },
];

const BROWSER_DESTINATIONS = [
  { label: 'YouTube', url: 'https://www.youtube.com' },
  { label: 'YouTube Music', url: 'https://music.youtube.com' },
];

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export default function CopilotPage() {
  const router = useRouter();
  const [requireConsent, setRequireConsent] = useState(true);
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [oauthLoading, setOauthLoading] = useState<string | null>(null);
  const [emailTo, setEmailTo] = useState('');
  const [emailSubject, setEmailSubject] = useState('');
  const [emailBody, setEmailBody] = useState('');
  const [sendingEmail, setSendingEmail] = useState(false);
  const [statusMessage, setStatusMessage] = useState('No action triggered yet.');
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      try {
        setRequireConsent(window.localStorage.getItem('jarvis-explicit-consent-required') !== 'false');
      } catch {
        setRequireConsent(true);
      }
    });

    let active = true;
    void apiClient.get<ConnectorListResponse>(API_ENDPOINTS.connectors.list)
      .then((response) => {
        if (active) setConnectors(response.connectors ?? []);
      })
      .catch((error: unknown) => {
        if (active) setLoadError(errorMessage(error, 'Could not load connector status.'));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      window.cancelAnimationFrame(frame);
    };
  }, []);

  const updateConsent = (required: boolean) => {
    setRequireConsent(required);
    try {
      window.localStorage.setItem('jarvis-explicit-consent-required', String(required));
    } catch {
      setStatusMessage('Preference could not be saved in this browser; consent remains required for this session.');
      setRequireConsent(true);
    }
  };

  const confirmAction = (description: string) => {
    if (!requireConsent) return true;
    const confirmed = window.confirm(`${description}\n\nContinue?`);
    if (!confirmed) setStatusMessage('Action cancelled. No external action was started.');
    return confirmed;
  };

  const openLocalRoute = (route: string, label: string) => {
    if (!confirmAction(`JARVIS will navigate to ${label} (${route}).`)) return;
    router.push(route);
    setStatusMessage(`Opened ${label} inside JARVIS.`);
  };

  const openInBrowser = (url: string, label: string) => {
    if (!confirmAction(`JARVIS Browser will attempt to open ${url}. Browser security policy may block the page.`)) return;
    router.push(`/dashboard/embedded-browser?url=${encodeURIComponent(url)}`);
    setStatusMessage(`Sent ${label} to JARVIS Browser. Navigation is subject to browser and site policy.`);
  };

  const connectProvider = async (kind: 'gmail' | 'outlook') => {
    const providerName = kind === 'gmail' ? 'Google' : 'Microsoft';
    if (!confirmAction(`JARVIS will request ${providerName} authorization. Review the provider's consent screen and approve only the access you intend to grant.`)) return;

    setOauthLoading(kind);
    setStatusMessage(`Starting ${providerName} authorization…`);
    try {
      const response = await apiClient.post<{ authorize_url: string }>(
        API_ENDPOINTS.connectors.oauthAuthorize(kind),
      );
      window.location.assign(response.authorize_url);
    } catch (error: unknown) {
      setStatusMessage(errorMessage(error, `Could not start ${providerName} authorization.`));
      setOauthLoading(null);
    }
  };

  const connectorStatus = (kind: string) => connectors.find((connector) => connector.kind === kind);
  const emailConnector = connectorStatus('email');
  const emailReady = Boolean(
    emailConnector?.configured
      && emailConnector.enabled !== false
      && emailConnector.capabilities?.includes('send'),
  );
  const providerConnected = (kind: string) => {
    const connector = connectorStatus(kind);
    return Boolean(connector && (connector.connected || connector.connection_status === 'Connected') && connector.enabled !== false);
  };

  const sendEmail = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!emailReady || sendingEmail) return;

    const to = emailTo.trim();
    const subject = emailSubject.trim();
    const body = emailBody.trim();
    if (!to || !subject || !body) return;

    const approved = window.confirm(
      `Send this email?\n\nTo: ${to}\nSubject: ${subject}\n\nJARVIS will send it using the configured email connector. This cannot be undone.`,
    );
    if (!approved) {
      setStatusMessage('Email cancelled. Nothing was sent.');
      return;
    }

    setSendingEmail(true);
    setStatusMessage('Sending email through the configured connector…');
    try {
      const result = await apiClient.post<ConnectorActionResponse>(
        API_ENDPOINTS.connectors.action('email'),
        {
          action: 'email.send',
          params: { to: [to], subject, body, confirm: true },
        },
        { retries: 0 },
      );
      if (result.ok) {
        setEmailTo('');
        setEmailSubject('');
        setEmailBody('');
        setStatusMessage(`Email sent to ${to}.`);
      } else if (result.confirmation_required) {
        setStatusMessage('The email was not sent. The server requires a fresh confirmation.');
      } else {
        setStatusMessage(result.error || 'The email connector did not confirm delivery.');
      }
    } catch (error: unknown) {
      setStatusMessage(errorMessage(error, 'The email could not be sent.'));
    } finally {
      setSendingEmail(false);
    }
  };

  return (
    <main className="min-h-full bg-[#080d12] px-4 py-8 text-slate-100 sm:px-7 lg:px-10">
      <div className="mx-auto max-w-6xl space-y-7">
        <header className="border-b border-white/10 pb-6">
          <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.22em] text-cyan-300">JARVIS / Copilot</p>
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Action center</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
                Navigate JARVIS, open destinations in its policy-controlled browser, and manage provider authorization.
              </p>
            </div>
            <span className="inline-flex items-center gap-2 self-start border border-emerald-400/25 bg-emerald-500/5 px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-emerald-200 sm:self-auto">
              <ShieldCheck className="h-4 w-4" aria-hidden="true" />
              Consent-aware actions
            </span>
          </div>
        </header>

        <section aria-labelledby="local-actions-title" className="grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
          <Card className="border-white/10 bg-[#0d151c]">
            <CardHeader>
              <CardTitle id="local-actions-title" className="flex items-center gap-2 text-slate-100">
                <Activity className="h-5 w-5 text-cyan-300" />
                JARVIS workspace
              </CardTitle>
              <CardDescription>Local navigation stays inside the authenticated application.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-2">
              {LOCAL_ACTIONS.map((action) => (
                <div key={action.route} className="flex flex-col justify-between gap-3 border-t border-white/10 py-3 first:border-t-0 sm:flex-row sm:items-center">
                  <div>
                    <p className="text-sm font-medium text-slate-100">{action.label}</p>
                    <p className="mt-1 text-xs text-slate-400">{action.description}</p>
                  </div>
                  <Button variant="outline" onClick={() => openLocalRoute(action.route, action.label)} className="shrink-0">
                    Open <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-[#0d151c]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-slate-100">
                <Globe2 className="h-5 w-5 text-cyan-300" />
                Open in JARVIS Browser
              </CardTitle>
              <CardDescription>Requests go through the embedded browser; the destination is not guaranteed to render.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {BROWSER_DESTINATIONS.map((destination) => (
                <div key={destination.url} className="flex items-center justify-between gap-3 border-t border-white/10 py-3 first:border-t-0">
                  <div>
                    <p className="text-sm font-medium text-slate-100">{destination.label}</p>
                    <p className="text-xs text-slate-500">{destination.url}</p>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => openInBrowser(destination.url, destination.label)}>
                    Open <ExternalLink className="ml-2 h-3.5 w-3.5" aria-hidden="true" />
                  </Button>
                </div>
              ))}
              <p className="border-l-2 border-amber-300/50 pl-3 pt-2 text-xs leading-5 text-amber-100/70">
                Site policy, authentication, or browser security may block navigation. JARVIS does not bypass those controls.
              </p>
            </CardContent>
          </Card>
        </section>

        <section aria-labelledby="provider-title" className="grid gap-5 lg:grid-cols-[1fr_1fr]">
          <Card className="border-white/10 bg-[#0d151c]">
            <CardHeader>
              <CardTitle id="provider-title" className="flex items-center gap-2 text-slate-100">
                <Mail className="h-5 w-5 text-amber-300" />
                Provider-backed services
              </CardTitle>
              <CardDescription>Authorization is handled by the existing connector API and provider consent flow.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {(['gmail', 'outlook'] as const).map((kind) => {
                const providerName = kind === 'gmail' ? 'Google' : 'Microsoft';
                const connected = providerConnected(kind);
                return (
                  <div key={kind} className="flex flex-col gap-3 border-t border-white/10 pt-3 first:border-t-0 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-sm font-medium text-slate-100">{providerName} account</p>
                      <p className="mt-1 text-xs text-slate-400">
                        {loading
                          ? 'Checking connector status…'
                          : connectorStatus(kind)?.connection_status
                            || (connected ? 'Configured in the connector service.' : 'Not connected through this connector.')}
                      </p>
                    </div>
                    <Button
                      variant={connected ? 'outline' : 'secondary'}
                      onClick={() => connected
                        ? openLocalRoute('/dashboard/connections', 'Connections')
                        : void connectProvider(kind)}
                      disabled={loading || oauthLoading !== null}
                      className="shrink-0"
                    >
                      {oauthLoading === kind && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
                      {connected ? 'Manage connection' : `Authorize ${providerName}`}
                    </Button>
                  </div>
                );
              })}
              {loadError && <p role="alert" className="border-l-2 border-rose-400/60 pl-3 text-xs text-rose-200">{loadError}</p>}
              <p className="border-l-2 border-amber-300/50 pl-3 pt-2 text-xs leading-5 text-amber-100/70">
                Connecting grants only the provider access shown on its consent screen. Email sending is a separate SMTP capability with a confirmation step below.
              </p>
              <Button variant="link" className="px-0 text-cyan-200" onClick={() => router.push('/dashboard/connections')}>
                Open Connections <ArrowRight className="ml-1 h-3.5 w-3.5" aria-hidden="true" />
              </Button>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-[#0d151c]">
            <CardHeader>
              <CardTitle className="text-slate-100">Action safeguards</CardTitle>
              <CardDescription>Keep an explicit confirmation before a navigation or provider authorization starts.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-start justify-between gap-4 border-y border-white/10 py-4">
                <div>
                  <p className="text-sm font-medium text-slate-100">Ask before starting actions</p>
                  <p className="mt-1 max-w-sm text-xs leading-5 text-slate-400">
                    This preference is stored in this browser. Provider consent remains independently controlled by Google or Microsoft.
                  </p>
                </div>
                <Switch
                  checked={requireConsent}
                  onCheckedChange={updateConsent}
                  aria-label="Require confirmation before starting actions"
                />
              </div>
              <div role="status" aria-live="polite" className="flex items-start gap-3 border border-white/10 bg-[#080d12] p-3">
                <MessageSquareText className="mt-0.5 h-4 w-4 shrink-0 text-cyan-300" aria-hidden="true" />
                <div>
                  <p className="text-xs font-medium text-slate-200">Latest action</p>
                  <p className="mt-1 text-xs leading-5 text-slate-400">{statusMessage}</p>
                </div>
              </div>
              <p className="text-xs leading-5 text-slate-500">
                No autonomous phone or TV controls are available here. No developer email identity is collected or assumed.
              </p>
            </CardContent>
          </Card>
        </section>

        <section aria-labelledby="email-compose-title">
          <Card className="border-white/10 bg-[#0d151c]">
            <CardHeader>
              <CardTitle id="email-compose-title" className="flex items-center gap-2 text-slate-100">
                <Send className="h-5 w-5 text-cyan-300" aria-hidden="true" />
                Send an email
              </CardTitle>
              <CardDescription>
                Uses the configured SMTP connector. JARVIS asks for confirmation before each send; provider OAuth sign-in alone does not enable email sending.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {emailReady ? (
                <form onSubmit={(event) => void sendEmail(event)} className="grid gap-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="grid gap-2">
                      <Label htmlFor="copilot-email-to">Recipient</Label>
                      <Input
                        id="copilot-email-to"
                        type="email"
                        autoComplete="email"
                        maxLength={254}
                        required
                        value={emailTo}
                        onChange={(event) => setEmailTo(event.target.value)}
                        placeholder="recipient@example.com"
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="copilot-email-subject">Subject</Label>
                      <Input
                        id="copilot-email-subject"
                        maxLength={998}
                        required
                        value={emailSubject}
                        onChange={(event) => setEmailSubject(event.target.value)}
                        placeholder="Subject"
                      />
                    </div>
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="copilot-email-body">Message</Label>
                    <Textarea
                      id="copilot-email-body"
                      maxLength={10000}
                      required
                      rows={6}
                      value={emailBody}
                      onChange={(event) => setEmailBody(event.target.value)}
                      placeholder="Write the message to send…"
                    />
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="text-xs text-slate-500">
                      Delivery depends on the configured SMTP service and may fail; JARVIS reports the connector result.
                    </p>
                    <Button type="submit" disabled={sendingEmail} className="shrink-0">
                      {sendingEmail
                        ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                        : <Send className="mr-2 h-4 w-4" aria-hidden="true" />}
                      {sendingEmail ? 'Sending…' : 'Review and send'}
                    </Button>
                  </div>
                </form>
              ) : (
                <div className="flex flex-col items-start justify-between gap-3 border border-white/10 bg-[#080d12] p-4 sm:flex-row sm:items-center">
                  <p className="text-sm text-slate-400">
                    {loading
                      ? 'Checking email connector readiness…'
                      : 'Email sending is unavailable until an enabled SMTP connector with the send capability is configured and tested.'}
                  </p>
                  <Button variant="outline" onClick={() => router.push('/dashboard/connections')} className="shrink-0">
                    Configure email <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
                  </Button>
                </div>
              )}
              <p role="status" aria-live="polite" className="mt-4 min-h-5 text-xs text-slate-400">
                {statusMessage}
              </p>
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}
