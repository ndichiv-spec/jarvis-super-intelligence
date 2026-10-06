'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Brain, Activity, Server, Globe, Bot, Layers, Sparkles,
  MessageSquare, Code2, Mic, Box, Eye, ArrowLeft,
  Atom, Shield, Network, Library, Terminal, Cpu,
  FlaskConical,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { RoomLink } from '@/components/room-link';
import { useBackend, useProviders, useSystemUsage } from '@/stores/platform-store';

import EmbeddedBrowser from '@/components/embedded-browser/EmbeddedBrowser';
import SelfReliantIDE from '@/app/dashboard/self-reliant/page';
import { ChatWindow } from '@/components/chat/chat-window';
import AdvancedAgentOrchestration from '@/components/advanced-agent-orchestration';
import JarvisFullPotential from '@/components/jarvis-full-potential';
import Jarvis3DVisualization from '@/components/jarvis-3d-visualization';
import JarvisVoiceInterface from '@/components/jarvis-voice-interface';
import JarvisHolographicInterface from '@/components/jarvis-holographic-interface';
import JarvisMultidimensionalViz from '@/components/jarvis-multidimensional-viz';
import { SystemTelemetry } from '@/components/dashboard/system-telemetry';

interface SystemStatus {
  status: string;
  name: string;
  version: string;
  services?: Record<string, string>;
  silverwing?: { integrated: boolean; error: string | null; mount: string };
}

type DashboardCard = {
  id: string;
  title: string;
  subtitle: string;
  icon: React.ElementType;
};

const DASHBOARD_CARDS: DashboardCard[] = [
  {
    id: 'browser',
    title: 'Embedded Browser',
    subtitle: 'Integrated web browser',
    icon: Globe,
  },
  {
    id: 'self-resilient',
    title: 'Self-Resilient IDE',
    subtitle: 'Adaptive code editor',
    icon: Code2,
  },
  {
    id: 'real-ai-chat',
    title: 'Real AI Chat',
    subtitle: 'Neural conversation engine',
    icon: MessageSquare,
  },
  {
    id: 'advanced-agents',
    title: 'Advanced Agents',
    subtitle: 'Multi-agent orchestration',
    icon: Bot,
  },
  {
    id: 'core-intelligence',
    title: 'Core Intelligence',
    subtitle: 'Full AI potential unlocked',
    icon: Sparkles,
  },
  {
    id: '3d-visualization',
    title: '3D Visualization',
    subtitle: 'Spatial data rendering',
    icon: Atom,
  },
  {
    id: 'voice-interface',
    title: 'Voice Interface',
    subtitle: 'Speech recognition & TTS',
    icon: Mic,
  },
  {
    id: 'system-chambers',
    title: 'System Chambers',
    subtitle: '8 core system modules',
    icon: Server,
  },
  {
    id: 'runtime-status',
    title: 'Runtime Status',
    subtitle: 'Live system health',
    icon: Activity,
  },
  {
    id: 'multidimensional',
    title: 'Multi-Dimensional',
    subtitle: 'Quantum data analysis',
    icon: Box,
  },
  {
    id: 'tier-management',
    title: 'Tier Management',
    subtitle: '6-tier intelligence control',
    icon: Layers,
  },
];

const DASHBOARD_GROUPS = [
  {
    title: 'Workbench',
    description: 'Build, browse, and coordinate work',
    cardIds: ['advanced-agents', 'browser', 'self-resilient'],
    accent: 'cyan',
  },
  {
    title: 'Intelligence',
    description: 'Explore JARVIS interfaces and visual tools',
    cardIds: ['core-intelligence', 'voice-interface', '3d-visualization', 'runtime-status', 'multidimensional'],
    accent: 'emerald',
  },
  {
    title: 'Platform',
    description: 'Inspect system modules and configuration',
    cardIds: ['system-chambers', 'tier-management'],
    accent: 'slate',
  },
] as const;

const TIERS = [
  { id: 1, name: 'Foundation', desc: 'Core AI, Basic Chat', color: 'blue', icon: Brain },
  { id: 2, name: 'Enhanced AI', desc: 'Advanced NLP, Memory', color: 'cyan', icon: Activity },
  { id: 3, name: 'Collaboration', desc: 'Agent Swarm, Multi-Agent', color: 'purple', icon: Bot },
  { id: 4, name: 'Enterprise', desc: 'Security, Compliance', color: 'emerald', icon: Shield },
  { id: 5, name: 'Advanced', desc: 'Quantum, Neural Nets', color: 'violet', icon: Network },
  { id: 6, name: 'Autonomous', desc: 'Self-Learning, Self-Optimize', color: 'pink', icon: Sparkles },
];

const CHAMBERS = [
  { name: 'Core AI', desc: 'Basic Chat', icon: Brain, color: 'blue' },
  { name: 'Advanced NLP', desc: 'Memory System', icon: Activity, color: 'cyan' },
  { name: 'Agent Swarm', desc: 'Multi-Agent', icon: Bot, color: 'purple' },
  { name: 'Runtime Status', desc: 'Live system health', icon: Activity, color: 'violet' },
  { name: 'Quantum', desc: 'Qubit Engine', icon: Atom, color: 'fuchsia' },
  { name: 'Neural Nets', desc: 'Deep Learning', icon: Network, color: 'pink' },
  { name: 'Security Hub', desc: 'Threat Protection', icon: Shield, color: 'emerald' },
  { name: 'Global Monitor', desc: '24/7 Surveillance', icon: Globe, color: 'sky' },
];

function OverviewPanel({
  systemStatus,
  compact = false,
}: {
  systemStatus: SystemStatus | null;
  compact?: boolean;
}) {
  const backend = useBackend();
  const usage = useSystemUsage();
  const { summary: providerSummary } = useProviders();
  const svcs = systemStatus?.services ? Object.entries(systemStatus.services) : [];
  const backendLabel = backend.connected
    ? 'Connected'
    : backend.status === 'idle' || backend.status === 'loading'
      ? 'Checking'
      : backend.status === 'degraded'
        ? 'Degraded'
        : 'Unavailable';
  const backendTone = backend.connected
    ? 'text-emerald-300'
    : backend.status === 'idle' || backend.status === 'loading'
      ? 'text-amber-200'
      : backend.status === 'degraded'
        ? 'text-amber-200'
        : 'text-rose-300';

  return (
    <div className="space-y-4">
      <section
        aria-label="Live system status"
        className="rounded-xl border border-white/[0.08] bg-[#07121d]/80 p-4"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-200/60">
              System overview
            </p>
            <h2 className="mt-1 text-base font-semibold text-foreground">Current signals</h2>
          </div>
          <span className={`inline-flex items-center gap-2 text-xs font-medium ${backendTone}`}>
            <span className={`h-2 w-2 rounded-full ${
              backend.connected ? 'bg-emerald-400' : backend.status === 'idle' || backend.status === 'loading' || backend.status === 'degraded' ? 'bg-amber-300' : 'bg-rose-400'
            }`} />
            JARVIS backend · {backendLabel}
          </span>
        </div>
        <dl className="mt-4 grid grid-cols-1 gap-3 border-t border-white/[0.07] pt-3 sm:grid-cols-3">
          <div>
            <dt className="text-[10px] uppercase tracking-wider text-muted-foreground/60">Resource telemetry</dt>
            <dd className="mt-1 text-sm font-medium text-foreground/90">
              {usage ? 'Receiving samples' : 'No sample received'}
            </dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-wider text-muted-foreground/60">Provider report</dt>
            <dd className="mt-1 text-sm font-medium text-foreground/90">
              {providerSummary.total > 0
                ? `${providerSummary.connected} of ${providerSummary.total} connected`
                : 'No provider status reported'}
            </dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-wider text-muted-foreground/60">Last backend check</dt>
            <dd className="mt-1 text-sm font-medium text-foreground/90">
              {backend.lastChecked ? backend.lastChecked.toLocaleTimeString() : 'Not checked yet'}
            </dd>
          </div>
        </dl>
      </section>

      {/* Live resource telemetry, sourced from the backend monitoring stream */}
      {usage ? (
        <SystemTelemetry showGauges={!compact} showChart={!compact} />
      ) : (
        <div role="status" className="rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-5 text-sm text-muted-foreground">
          Waiting for a system telemetry sample. Resource metrics will appear here when the monitoring service reports them.
        </div>
      )}
      {systemStatus?.silverwing && (
        <Card className="border-white/10 bg-white/[0.02]">
          <CardContent className="p-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Shield className="h-4 w-4 text-purple-400" />
              <span className="text-sm font-medium">Silverwing Backend</span>
            </div>
            <Badge className={systemStatus.silverwing.integrated
              ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
              : 'bg-red-500/20 text-red-400 border-red-500/30'}>
              {systemStatus.silverwing.integrated ? 'Integrated' : 'Offline'}
            </Badge>
          </CardContent>
        </Card>
      )}
      {svcs.length > 0 && (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {svcs.map(([key, val]) => {
            const Icon = key.includes('agent') ? Bot : key.includes('memory') ? Activity : Globe;
            return (
              <div key={key} className="flex items-center gap-2 rounded-lg border border-white/5 p-2.5">
                <Icon className="h-4 w-4 text-blue-400" />
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium truncate">{key}</div>
                  <div className="text-[9px] text-muted-foreground/60 capitalize">{val}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Cross-feature navigation */}
      {!compact && <Card className="border-white/10 bg-white/[0.02]">
        <CardContent className="p-4">
          <h4 className="text-xs font-semibold text-muted-foreground/60 uppercase tracking-wider mb-3">
            Related Capabilities
          </h4>
          <div className="space-y-2">
            <RoomLink label="Agent Orchestration" href="/dashboard/agents" icon={Bot} description="Multi-agent task management" />
            <RoomLink label="Memory Inspector" href="/dashboard/memory" icon={Library} description="Working, episodic, semantic memory" />
            <RoomLink label="Knowledge Studio" href="/dashboard/knowledge" icon={Network} description="Search, patterns, knowledge graph" />
            <RoomLink label="System Control" href="/dashboard/system" icon={Cpu} description="Processes, providers, capabilities" />
            <RoomLink label="Command Center" href="/dashboard/monitoring" icon={Activity} description="Real-time health and metrics" />
            <RoomLink label="Bio-Growth Lab" href="/dashboard/bio-growth" icon={FlaskConical} description="Growth and adaptation workspace" />
            <RoomLink label="Stark Control" href="/stark-control" icon={Terminal} description="Engine status, tools, goals" />
          </div>
        </CardContent>
      </Card>}
    </div>
  );
}

function TierManagementPanel() {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {TIERS.map((tier) => {
          const Icon = tier.icon;
          return (
            <Card key={tier.id} className="border-white/10 bg-white/[0.02] hover:border-white/20 transition-all">
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 bg-${tier.color}-500/20 rounded-lg`}>
                      <Icon className={`h-5 w-5 text-${tier.color}-400`} />
                    </div>
                    <div>
                      <p className="text-sm font-medium">Tier {tier.id}: {tier.name}</p>
                      <p className="text-[10px] text-muted-foreground/50">{tier.desc}</p>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function SystemChambersPanel() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {CHAMBERS.map((ch, i) => {
        const Icon = ch.icon;
        return (
          <motion.div
            key={ch.name}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: i * 0.04 }}
          >
            <Card className="border-white/10 bg-white/[0.02] text-center hover:border-white/20 transition-all">
              <CardContent className="p-4">
                <div className={`mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-lg bg-${ch.color}-500/20`}>
                  <Icon className={`h-5 w-5 text-${ch.color}-400`} />
                </div>
                <p className="text-sm font-medium">{ch.name}</p>
                <p className="text-[10px] text-muted-foreground/50">{ch.desc}</p>
              </CardContent>
            </Card>
          </motion.div>
        );
      })}
    </div>
  );
}

export default function DashboardPage() {
  const [activeCard, setActiveCard] = useState<string | null>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);

  useEffect(() => {
    fetch('/api/v1/status')
      .then(async r => {
        if (!r.ok) return null;
        const ct = r.headers.get('content-type') || '';
        if (!ct.includes('application/json')) return null;
        return r.json();
      })
      .then(data => { if (data) setSystemStatus(data); })
      .catch(() => {});
  }, []);

  const getComponent = (id: string): React.ReactNode => {
    switch (id) {
      case 'browser': return <EmbeddedBrowser />;
      case 'self-resilient': return <SelfReliantIDE />;
      case 'real-ai-chat': return <ChatWindow showSidebar className="min-h-0" />;
      case 'advanced-agents': return <AdvancedAgentOrchestration />;
      case 'core-intelligence': return <JarvisFullPotential />;
      case '3d-visualization': return <Jarvis3DVisualization />;
      case 'voice-interface': return <JarvisVoiceInterface />;
      case 'system-chambers': return <SystemChambersPanel />;
      case 'runtime-status': return <JarvisHolographicInterface />;
      case 'multidimensional': return <JarvisMultidimensionalViz />;
      case 'tier-management': return <TierManagementPanel />;
      default: return null;
    }
  };

  const activeCardData = DASHBOARD_CARDS.find(c => c.id === activeCard);

  return (
    <div className="flex h-[calc(100dvh-4rem)] min-h-0 flex-col">
      {/* Header */}
      <div className="shrink-0 px-3 py-3 pb-2 sm:p-4 sm:pb-3">
        <div className="flex min-w-0 items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2.5 sm:gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-cyan-400 shadow-lg shadow-blue-500/20 sm:h-10 sm:w-10">
              <Brain className="h-4 w-4 text-white sm:h-5 sm:w-5" />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-lg font-bold text-foreground sm:text-xl">
                <span className="sm:hidden">JARVIS Dashboard</span>
                <span className="hidden sm:inline">
                JARVIS Version 10.0 Dashboard
                </span>
              </h1>
              <p className="hidden text-xs text-muted-foreground/50 sm:block">
                Overview — Unified Control Center
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Badge className="hidden bg-gradient-to-r from-blue-500 to-cyan-400 text-xs font-bold sm:inline-flex">
              v10
            </Badge>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="min-h-0 flex-1 overflow-hidden px-3 pb-3 sm:px-4 sm:pb-4">
        <AnimatePresence mode="wait">
          {activeCard === null ? (
            <motion.div
              key="grid"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="h-full overflow-y-auto"
            >
              <section aria-label="System overview" className="mb-4 sm:mb-6">
                <OverviewPanel systemStatus={systemStatus} compact />
              </section>
              <section aria-labelledby="dashboard-start-heading" className="mb-5">
                <div className="grid gap-3 lg:grid-cols-[minmax(0,1.5fr)_minmax(16rem,0.8fr)]">
                  <div className="flex flex-col justify-between gap-4 rounded-xl border border-cyan-300/15 bg-[linear-gradient(115deg,rgba(9,35,49,0.95),rgba(7,18,29,0.9)_62%)] p-4 sm:flex-row sm:items-center sm:p-5">
                    <div className="flex min-w-0 items-start gap-3">
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-cyan-200/15 bg-cyan-300/[0.08] text-cyan-200">
                        <MessageSquare aria-hidden="true" className="h-5 w-5" />
                      </span>
                      <div className="min-w-0">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-cyan-200/65">
                          Start here
                        </p>
                        <h2 id="dashboard-start-heading" className="mt-1 text-base font-semibold text-foreground sm:text-lg">
                          Open a conversation
                        </h2>
                        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                          Work with JARVIS in the shared chat workspace.
                        </p>
                      </div>
                    </div>
                    <Button
                      onClick={() => setActiveCard('real-ai-chat')}
                      className="min-h-11 w-full shrink-0 justify-between gap-3 bg-cyan-300 text-slate-950 hover:bg-cyan-200 sm:w-auto sm:justify-center"
                    >
                      Open chat
                      <span aria-hidden="true">→</span>
                    </Button>
                  </div>

                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                    <h2 className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground/70">
                      Direct routes
                    </h2>
                    <div className="mt-2 divide-y divide-white/[0.06]">
                      <RoomLink label="Bio-Growth Lab" href="/dashboard/bio-growth" icon={FlaskConical} description="Growth and adaptation" />
                      <RoomLink label="Agent Orchestration" href="/dashboard/agents" icon={Bot} description="Multi-agent task management" />
                    </div>
                  </div>
                </div>
                </section>

              <section aria-labelledby="dashboard-workspaces-heading" className="pb-2">
                <div className="mb-3 flex flex-wrap items-end justify-between gap-x-3 gap-y-1">
                  <div>
                    <h2 id="dashboard-workspaces-heading" className="text-sm font-semibold text-foreground">
                      Workspaces
                    </h2>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Choose a destination by the work you need to do.
                    </p>
                  </div>
                  <span className="text-[11px] text-muted-foreground/55">
                    {DASHBOARD_CARDS.length} destinations
                  </span>
                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {DASHBOARD_GROUPS.map((group, groupIndex) => (
                    <motion.section
                      key={group.title}
                      aria-labelledby={`dashboard-group-${group.title.toLowerCase()}`}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: groupIndex * 0.06 }}
                      className="overflow-hidden rounded-xl border border-white/[0.08] bg-[#07121d]/70"
                    >
                      <header className="border-b border-white/[0.07] px-3.5 py-3">
                        <div className="flex items-center gap-2">
                          <span className={`h-1.5 w-1.5 rounded-full ${
                            group.accent === 'cyan' ? 'bg-cyan-300' : group.accent === 'emerald' ? 'bg-emerald-300' : 'bg-slate-300'
                          }`} />
                          <h3 id={`dashboard-group-${group.title.toLowerCase()}`} className="text-sm font-semibold text-foreground">
                            {group.title}
                          </h3>
                        </div>
                        <p className="mt-1 pl-3.5 text-xs leading-relaxed text-muted-foreground">
                          {group.description}
                        </p>
                      </header>
                      <ul className="divide-y divide-white/[0.06] px-2">
                        {group.cardIds.map((cardId) => {
                          const card = DASHBOARD_CARDS.find((item) => item.id === cardId);
                          if (!card) return null;
                          const Icon = card.icon;
                          const iconTone = group.accent === 'cyan'
                            ? 'border-cyan-300/15 bg-cyan-300/[0.07] text-cyan-200'
                            : group.accent === 'emerald'
                              ? 'border-emerald-300/15 bg-emerald-300/[0.07] text-emerald-200'
                              : 'border-slate-300/15 bg-slate-300/[0.06] text-slate-200';

                          return (
                            <li key={card.id}>
                              <button
                                type="button"
                                onClick={() => setActiveCard(card.id)}
                                className="group flex min-h-[68px] w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-white/[0.04] focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-300"
                              >
                                <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border ${iconTone}`}>
                                  <Icon aria-hidden="true" className="h-4 w-4" />
                                </span>
                                <span className="min-w-0 flex-1">
                                  <span className="block text-sm font-medium leading-5 text-foreground/90">
                                    {card.title}
                                  </span>
                                  <span className="mt-0.5 block text-xs leading-4 text-muted-foreground">
                                    {card.subtitle}
                                  </span>
                                </span>
                                <span aria-hidden="true" className="shrink-0 text-sm text-muted-foreground/40 transition-colors group-hover:text-cyan-200">
                                  →
                                </span>
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    </motion.section>
                  ))}
                </div>
              </section>
            </motion.div>
          ) : (
            <motion.div
              key={activeCard}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="h-full flex flex-col"
            >
              {/* Sub-header with back button */}
              <div className="shrink-0 flex items-center gap-3 pb-3">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setActiveCard(null)}
                  className="gap-1.5 text-muted-foreground hover:text-foreground"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Back
                </Button>
                {activeCardData && (
                  <>
                    <div className="h-5 w-px bg-white/10" />
                    <div className="flex items-center gap-2">
                      {(() => { const Icon = activeCardData.icon; return <Icon className="h-4 w-4 text-cyan-200" />; })()}
                      <span className="text-sm font-semibold">{activeCardData.title}</span>
                    </div>
                  </>
                )}
              </div>

              {/* Component content */}
              <div className={`flex-1 ${
                activeCard === 'real-ai-chat'
                  ? 'min-h-0 overflow-hidden'
                  : 'overflow-y-auto'
              }`}>
                {getComponent(activeCard)}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
