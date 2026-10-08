'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Brain, Calendar, Database, Globe, HardDrive, Mail, MessageSquare, Github,
  RefreshCw, Shield,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { apiClient, ApiClientError } from '@/lib/api-client';

interface AiAccess {
  accesses: Record<string, boolean>;
  user: string;
}

interface Capabilities {
  capabilities: string[];
}

interface Domain {
  key: string;
  label: string;
  icon: React.ElementType;
  desc: string;
  caps: string[];
}

// Spec §47 feature flags — the same map the backend builds capabilities from.
const DOMAINS: Domain[] = [
  {
    key: 'email',
    label: 'Email',
    icon: Mail,
    desc: 'Read, summarize, draft and send email via Gmail/Outlook and IMAP/SMTP connectors.',
    caps: ['email.read', 'email.summarize', 'email.draft', 'email.send'],
  },
  {
    key: 'calendar',
    label: 'Calendar',
    icon: Calendar,
    desc: 'Read and write calendar events through connected calendar providers.',
    caps: ['calendar.read', 'calendar.write'],
  },
  {
    key: 'filesystem',
    label: 'Filesystem',
    icon: HardDrive,
    desc: 'Read and write sandboxed local files (gated, never leaves the sandbox).',
    caps: ['files.read', 'files.write'],
  },
  {
    key: 'web',
    label: 'Web',
    icon: Globe,
    desc: 'Web search and browsing for the model — routed through the sandbox proxy.',
    caps: ['web.search', 'web.browse'],
  },
  {
    key: 'slack',
    label: 'Slack',
    icon: MessageSquare,
    desc: 'Send messages to Slack channels as the authenticated workspace bot.',
    caps: ['slack.send'],
  },
  {
    key: 'database',
    label: 'Database',
    icon: Database,
    desc: 'Run read-only queries against approved, connected databases.',
    caps: ['database.query'],
  },
  {
    key: 'github',
    label: 'GitHub',
    icon: Github,
    desc: 'Read and (with explicit confirmation) write GitHub repos and issues.',
    caps: ['github.read', 'github.write'],
  },
];

const CONFIRM_DOMAINS = new Set(['email', 'filesystem', 'database', 'github']);

export default function AiAccessPage() {
  const [access, setAccess] = useState<Record<string, boolean>>({});
  const [user, setUser] = useState<string | undefined>();
  const [caps, setCaps] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<Record<string, boolean>>({});

  const load = async () => {
    setLoading(true);
    try {
      const [aRes, cRes] = await Promise.all([
        apiClient.get<AiAccess>('/api/v1/developer/access'),
        apiClient.get<Capabilities>('/api/v1/developer/capabilities'),
      ]);
      setAccess(aRes.accesses || {});
      setUser(aRes.user);
      setCaps(cRes.capabilities || []);
    } catch (e: any) {
      toast.error(`Failed to load AI access: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const refreshCaps = async () => {
    try {
      const r = await apiClient.get<Capabilities>('/api/v1/developer/capabilities');
      setCaps(r.capabilities || []);
    } catch {
      /* ignore — toggles will still reflect locally */
    }
  };

  const toggle = async (domain: Domain) => {
    const next = !access[domain.key];
    setToggling((t) => ({ ...t, [domain.key]: true }));

    if (next && CONFIRM_DOMAINS.has(domain.key)) {
      const ok = window.confirm(
        `${domain.label} AI access is powerful.\n\n` +
          `It will grant the model the following capabilities:\n` +
          domain.caps.map((c) => `  • ${c}`).join('\n') +
          `\n\nThese actions are still subject to the per-action human confirmation` +
          ` gate (e.g. email.send / files.write / database.query / github.write ` +
          `always require explicit approval before execution).\n\n` +
          `Enable ${domain.label} access?`
      );
      if (!ok) {
        setToggling((t) => ({ ...t, [domain.key]: false }));
        return;
      }
    }

    try {
      await apiClient.post<{ success: boolean; extension: string; enabled: boolean }>(
        `/api/v1/developer/access/${domain.key}`,
        { extension: domain.key, enabled: next }
      );
      setAccess((a) => ({ ...a, [domain.key]: next }));
      toast.success(
        `${domain.label} ${next ? 'enabled' : 'disabled'} — ` +
          `${next ? 'capabilities are now active' : 'capabilities revoked'}`
      );
      await refreshCaps();
    } catch (e: any) {
      if (e instanceof ApiClientError && e.status === 403) {
        toast.error('Admin access required to change AI access.');
      } else {
        toast.error(e.message);
      }
    } finally {
      setToggling((t) => ({ ...t, [domain.key]: false }));
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const activeCount = Object.values(access).filter(Boolean).length;
  const spin = (cond: boolean) =>
    cond ? <RefreshCw className="h-4 w-4 animate-spin" /> : null;

  if (loading) {
    return (
      <div className="flex-1 space-y-6 p-6 pt-6 flex items-center justify-center min-h-[60vh]">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center"
        >
          <RefreshCw className="h-8 w-8 text-cyan-400 animate-spin mx-auto mb-3" />
          <p className="text-cyan-200">Loading AI access…</p>
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
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 via-cyan-400 to-indigo-600 shadow-lg shadow-indigo-500/30">
              <Shield className="h-7 w-7 text-white" />
            </div>
          </div>
          <div>
            <h1 className="text-3xl font-black bg-gradient-to-r from-indigo-400 via-cyan-300 to-indigo-400 bg-clip-text text-transparent">
              AI Access
            </h1>
            <p className="text-sm text-muted-foreground/70 mt-0.5">
              Grant capability packs to JARVIS. Each send/write action still requires
              explicit human confirmation before it runs.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {user && (
            <Badge variant="outline" className="text-xs">
              Signed in as {user}
            </Badge>
          )}
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button variant="outline" size="sm" asChild>
            <a href="/dashboard/extensions">
              <Brain className="h-4 w-4 mr-2" />
              Connections
            </a>
          </Button>
        </div>
      </motion.div>

      {/* Summary */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border border-indigo-500/20">
          <CardContent className="pt-6 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Shield className="h-6 w-6 text-indigo-400" />
              <div>
                <p className="font-semibold text-indigo-300">Active AI Access</p>
                <p className="text-sm text-muted-foreground/70">
                  {activeCount}/{DOMAINS.length} domains enabled · {caps.length} derived capabilities
                </p>
              </div>
            </div>
            <Badge variant={activeCount > 0 ? 'default' : 'secondary'}>
              {activeCount > 0 ? `${caps.length} capabilities live` : 'All access off'}
            </Badge>
          </CardContent>
        </Card>
      </motion.div>

      {/* Active derived capabilities */}
      {caps.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
        >
          <Card className="bg-slate-900/60 border border-white/10">
            <CardHeader>
              <CardTitle className="text-white text-base">Active capabilities</CardTitle>
              <CardDescription>
                These are derived from the enabled domains above (spec §47) and are
                what the model actually sees as available tools.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {caps.map((c) => (
                <Badge key={c} variant="outline" className="text-xs">
                  {c}
                </Badge>
              ))}
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* Domains */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {DOMAINS.map((domain, i) => {
            const on = !!access[domain.key];
            const Icon = domain.icon;
            return (
              <motion.div
                key={domain.key}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03 }}
              >
                <Card
                  className={
                    'h-full bg-gradient-to-br from-slate-900/80 to-slate-800/80 border transition-colors flex flex-col ' +
                    (on
                      ? 'border-indigo-500/30'
                      : 'border-white/10 hover:border-white/20')
                  }
                >
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-white">
                      <Icon className={`h-5 w-5 ${on ? 'text-indigo-400' : 'text-muted-foreground'}`} />
                      {domain.label}
                      <Badge
                        variant={on ? 'default' : 'secondary'}
                        className="ml-auto text-xs"
                      >
                        {on ? 'Enabled' : 'Disabled'}
                      </Badge>
                    </CardTitle>
                    <CardDescription className="line-clamp-3">
                      {domain.desc}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="mt-auto flex items-center justify-between gap-2">
                    <div className="flex flex-wrap gap-1">
                      {domain.caps.map((c) => (
                        <Badge key={c} variant="outline" className="text-[10px] px-1.5">
                          {c}
                        </Badge>
                      ))}
                    </div>
                    <Button
                      size="sm"
                      variant={on ? 'outline' : 'default'}
                      onClick={() => toggle(domain)}
                      disabled={!!toggling[domain.key]}
                    >
                      {spin(!!toggling[domain.key]) ? null : null}
                      {toggling[domain.key] ? '…' : on ? 'Disable' : 'Enable'}
                    </Button>
                  </CardContent>
                </Card>
              </motion.div>
            );
          })}
        </div>
      </motion.div>

      {activeCount === 0 && (
        <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border border-white/10">
          <CardContent className="pt-10 text-center">
            <Shield className="h-12 w-12 text-muted-foreground/40 mx-auto mb-3" />
            <p className="text-muted-foreground/60">
              All AI access is currently off. Enable a domain above to grant JARVIS
              its first capability packs.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
