'use client';

import { useState, useMemo } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion } from 'framer-motion';
import {
  Brain, Bot, Cpu, Activity, BookOpen, Settings, Shield,
  Layers, MessageSquare, Workflow, MonitorPlay, Code2,
  ArrowUpCircle, Library, Server, Globe, Zap,
  Crown, Sparkles, Terminal, Mail, Puzzle,
  Mic, Image, Eye, Box, Network, Search,
  Bell, Lock, Key, GitBranch, Target, Gauge,
  FileText, Palette, Wrench, Database, ArrowLeftRight,
  FlaskConical, Satellite, ShieldCheck, Users,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  useSystemUsage,
  useBackend,
  useProviders,
  useSilverwing,
} from '@/stores/platform-store';

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
  badge?: string;
  category: string;
  crossReference?: string;
}

export const NAV_ITEMS: NavItem[] = [
  // AI Core — the central intelligence cluster
  { label: 'Neural Chat', href: '/dashboard', icon: Brain, category: 'AI Core', crossReference: '/dashboard/agents' },
  { label: 'Command Runtime', href: '/dashboard/commands', icon: Workflow, badge: 'RUNTIME', category: 'AI Core', crossReference: '/dashboard/monitoring' },
  { label: 'Agent Orchestration', href: '/dashboard/agents', icon: Bot, category: 'AI Core', crossReference: '/dashboard/monitoring' },
  { label: 'UME', href: '/dashboard/knowledge', icon: Layers, category: 'AI Core', crossReference: '/dashboard/system' },
  { label: 'Supreme', href: '/supreme', icon: Crown, category: 'AI Core', crossReference: '/dashboard/agents' },
  { label: 'Voice', href: '/voice', icon: Mic, badge: 'BETA', category: 'AI Core', crossReference: '/dashboard/memory' },
  { label: 'Image', href: '/image-generation', icon: Image, badge: 'AI', category: 'AI Core', crossReference: '/dashboard/knowledge' },
  { label: 'Maps & Locations', href: '/locations', icon: Satellite, category: 'AI Core', crossReference: '/dashboard/knowledge' },

  // Workspace — productive environments
  { label: 'Desktop', href: '/desktop', icon: MonitorPlay, badge: 'NEW', category: 'Workspace', crossReference: '/dashboard/embedded-browser' },
  { label: 'Browser', href: '/dashboard/embedded-browser', icon: Globe, category: 'Workspace', crossReference: '/knowledge-hub' },
  { label: 'Workflows', href: '/workflows', icon: Workflow, category: 'Workspace', crossReference: '/dashboard/agents' },
  { label: 'Holographic', href: '/holographic', icon: Sparkles, badge: '3D', category: 'Workspace', crossReference: '/dashboard/monitoring' },
  { label: 'IDE', href: '/dashboard/self-reliant', icon: Code2, badge: 'NEW', category: 'Workspace', crossReference: '/dashboard/extensions' },

  // Infrastructure — system backbone
  { label: 'Command Center', href: '/dashboard/monitoring', icon: Activity, category: 'Infrastructure', crossReference: '/dashboard/system' },
  { label: 'System Control', href: '/dashboard/system', icon: Cpu, category: 'Infrastructure', crossReference: '/dashboard/connections' },
  { label: 'Knowledge Matrix', href: '/dashboard/knowledge', icon: BookOpen, category: 'Infrastructure', crossReference: '/dashboard/memory' },
  { label: 'Memory', href: '/dashboard/memory', icon: Library, category: 'Infrastructure', crossReference: '/dashboard/knowledge' },
  { label: 'Connections', href: '/dashboard/connections', icon: Mail, category: 'Infrastructure', crossReference: '/dashboard/extensions' },
  { label: 'Stark Control', href: '/stark-control', icon: Terminal, badge: 'CORE', category: 'Infrastructure', crossReference: '/dashboard/system' },
  { label: 'Knowledge Hub', href: '/knowledge-hub', icon: Library, category: 'Infrastructure', crossReference: '/dashboard/knowledge' },

  // System — configuration and management
  { label: 'Settings', href: '/dashboard/settings', icon: Settings, category: 'System', crossReference: '/dashboard/admin' },
  { label: 'Extensions', href: '/dashboard/extensions', icon: Puzzle, category: 'System', crossReference: '/dashboard/connections' },
  { label: 'Admin Console', href: '/dashboard/admin', icon: Shield, badge: 'ENT', category: 'System', crossReference: '/dashboard/settings' },
  { label: 'Self-Upgrade', href: '/upgrade', icon: ArrowUpCircle, category: 'System', crossReference: '/omega' },

  // Enterprise — security and compliance
  { label: 'Security', href: '/dashboard/security', icon: Shield, badge: 'SEC', category: 'Enterprise', crossReference: '/dashboard/admin' },
  { label: 'Enterprise SSO', href: '/enterprise-sso', icon: Lock, category: 'Enterprise', crossReference: '/dashboard/admin' },
  { label: 'API Keys', href: '/dashboard/api-keys', icon: Key, category: 'Enterprise', crossReference: '/dashboard/settings' },
  { label: 'Global Search', href: '/dashboard/search', icon: Search, category: 'Enterprise', crossReference: '/dashboard/knowledge' },
];

const SIDEBAR_WIDTH = 280;

interface SidebarProps {
  isMobile: boolean;
  isOpen: boolean;
  onClose: () => void;
}

export function Sidebar({ isMobile, isOpen, onClose }: SidebarProps) {
  const pathname = usePathname();
  const systemUsage = useSystemUsage();
  const backend = useBackend();
  const { summary, status: providerAvailability } = useProviders();
  const silverwing = useSilverwing();

  const isActive = (href: string) => {
    if (href === '/dashboard') return pathname === '/dashboard';
    return pathname?.startsWith(href) ?? false;
  };

  const groupedItems = useMemo(() => {
    return NAV_ITEMS.reduce<Record<string, NavItem[]>>((acc, item) => {
      if (!acc[item.category]) acc[item.category] = [];
      acc[item.category].push(item);
      return acc;
    }, {});
  }, []);

  const cpuPercent = systemUsage?.cpu_percent;
  const memPercent = systemUsage?.memory_percent;
  const diskPercent = systemUsage?.disk_percent;
  const processCount = systemUsage?.processes;
  const backendStatusLabel = backend.status === 'idle' || backend.status === 'loading'
    ? 'Checking'
    : backend.status === 'unauthorized'
      ? 'Access restricted'
      : backend.connected
        ? 'Connected'
        : backend.status === 'degraded'
          ? 'Degraded'
          : 'Unavailable';
  const backendStatusClass = backend.connected
    ? 'text-emerald-300'
    : backend.status === 'idle' || backend.status === 'loading'
      ? 'text-slate-300'
      : backend.status === 'degraded' || backend.status === 'unauthorized'
        ? 'text-amber-200'
        : 'text-rose-200';
  const backendStatusDot = backend.connected
    ? 'bg-emerald-500'
    : backend.status === 'idle' || backend.status === 'loading'
      ? 'bg-slate-400'
      : backend.status === 'degraded' || backend.status === 'unauthorized'
        ? 'bg-amber-300'
        : 'bg-rose-300';
  const missingMetricValue = backend.status === 'idle' || backend.status === 'loading'
    ? 'Checking'
    : backend.status === 'unauthorized'
      ? 'Access restricted'
      : backend.connected
        ? 'No data'
        : 'Unavailable';

  return (
    <>
      {isMobile && isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-40 bg-black/80 backdrop-blur-sm"
          onClick={onClose}
        />
      )}

      <aside
        id="primary-navigation"
        aria-hidden={isMobile && !isOpen}
        inert={isMobile && !isOpen}
        className={`fixed left-0 top-0 z-50 flex h-screen flex-col border-r border-white/5 bg-gradient-to-b from-[hsl(222,47%,8%)] to-[hsl(222,47%,4%)] transition-all duration-300 ${
          isMobile && !isOpen ? '-translate-x-full' : 'translate-x-0'
        }`}
        style={{ width: SIDEBAR_WIDTH }}
      >
        {/* Logo / Identity Bar */}
        <div className="flex h-16 items-center gap-3 border-b border-white/5 px-5">
          <div className="relative">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-cyan-400 shadow-lg shadow-blue-500/20">
              <Brain className="h-5 w-5 text-white" />
            </div>
            <span role="status" aria-label={`Backend API ${backendStatusLabel.toLowerCase()}`} className="absolute -right-0.5 -top-0.5 flex h-3 w-3">
              {backend.connected && (
                <span aria-hidden="true" className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              )}
              <span aria-hidden="true" className={`relative inline-flex h-3 w-3 rounded-full border-2 border-[hsl(222,47%,8%)] ${backendStatusDot}`} />
            </span>
          </div>
          <div>
            <span className="text-lg font-bold bg-gradient-to-r from-blue-400 via-cyan-400 to-blue-400 bg-clip-text text-transparent">
              JARVIS
            </span>
            <span className="ml-1.5 text-[10px] font-medium text-muted-foreground/60">v10</span>
          </div>
        </div>

        <ScrollArea className="flex-1 px-3 py-4">
          {/* Navigation */}
          <nav className="space-y-5">
            {Object.entries(groupedItems).map(([category, items]) => (
              <div key={category}>
                <div className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
                  {category}
                </div>
                <div className="space-y-1">
                  {items.map((item) => {
                    const active = isActive(item.href);
                    const Icon = item.icon;
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        onClick={isMobile ? onClose : undefined}
                        aria-current={active ? 'page' : undefined}
                        className="rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200/60"
                      >
                        <motion.div
                          whileHover={{ x: 2 }}
                          className={`relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
                            active
                              ? 'border border-cyan-200/15 bg-cyan-200/[0.06] text-cyan-100'
                              : 'text-muted-foreground/70 hover:bg-white/5 hover:text-foreground'
                          }`}
                        >
                          {active && (
                            <motion.div
                              layoutId="activeNav"
                              className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-cyan-200"
                            />
                          )}
                          <Icon className={`h-5 w-5 shrink-0 ${active ? 'text-cyan-100' : 'text-muted-foreground/50'}`} />
                          <span className="flex-1">{item.label}</span>
                          {item.badge && (
                            <Badge className={`h-5 px-1.5 text-[11px] font-bold ${
                              item.badge === 'LIVE'
                                ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                                : 'bg-purple-500/20 text-purple-400 border-purple-500/30'
                            }`}>
                              {item.badge}
                            </Badge>
                          )}
                        </motion.div>
                      </Link>
                    );
                  })}
                </div>
              </div>
            ))}
          </nav>

          {/* Cross-reference quick links */}
          <div className="mt-6 space-y-2">
            <div className="px-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
              Quick Links
            </div>
            {[
              { label: 'Research → Knowledge', href: '/dashboard/knowledge', icon: BookOpen },
              { label: 'Memory → Cognitive', href: '/dashboard/memory', icon: Library },
              { label: 'Agents → Monitoring', href: '/dashboard/monitoring', icon: Activity },
              { label: 'Tools → Providers', href: '/dashboard/connections', icon: Mail },
              { label: 'Security → System', href: '/dashboard/security', icon: Shield },
            ].map((link) => {
              const Icon = link.icon;
              return (
                <Link key={link.href} href={link.href} onClick={isMobile ? onClose : undefined}>
                  <motion.div
                    whileHover={{ x: 4 }}
                    className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-slate-300 hover:bg-white/5 hover:text-foreground transition-all cursor-pointer"
                  >
                    <Icon className="h-4 w-4" />
                    <span>{link.label}</span>
                  </motion.div>
                </Link>
              );
            })}
          </div>

          {/* Real System Metrics (from backend — no hardcoded values) */}
          <div className="mt-6 space-y-2">
            <div className="px-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
              System Metrics
            </div>
            <div className="space-y-1">
              {[
                { label: 'CPU Usage', value: cpuPercent == null ? missingMetricValue : `${Math.round(cpuPercent)}%`, icon: Cpu, color: 'text-blue-400' },
                { label: 'Memory', value: memPercent == null ? missingMetricValue : `${Math.round(memPercent)}%`, icon: Database, color: 'text-cyan-400' },
                { label: 'Disk', value: diskPercent == null ? missingMetricValue : `${Math.round(diskPercent)}%`, icon: Gauge, color: 'text-purple-400' },
                { label: 'Active Processes', value: processCount == null ? missingMetricValue : processCount.toLocaleString(), icon: Activity, color: 'text-emerald-400' },
                { label: 'Backend API', value: backendStatusLabel, icon: Brain, color: backendStatusClass },
                { label: 'Silverwing', value: silverwing.connected ? `${silverwing.status || 'Connected'}` : silverwing.status === 'unknown' ? 'Not verified' : 'Offline', icon: Zap, color: silverwing.connected ? 'text-amber-400' : 'text-gray-400' },
              ].map((metric) => {
                const Icon = metric.icon;
                return (
                  <div key={metric.label} className="flex items-center justify-between rounded-xl px-3 py-2.5 text-sm">
                    <div className="flex items-center gap-3">
                      <Icon className={`h-4 w-4 ${metric.color}`} />
                      <span className="text-muted-foreground/70">{metric.label}</span>
                    </div>
                    <span className={`text-xs font-bold ${metric.color}`}>{metric.value}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Provider state is reported as verified only when the backend says so. */}
          <div className="mt-6 space-y-2 px-3">
              <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Provider Fleet
              </div>
              <div className="space-y-1">
                {providerAvailability === 'completed' && summary.total > 0 && summary.connected > 0 && (
                  <div className="flex items-center justify-between rounded-xl px-3 py-2.5 text-sm">
                    <span className="text-muted-foreground/70">Verified connected</span>
                    <span className="text-xs font-bold text-emerald-400">{summary.connected}/{summary.total}</span>
                  </div>
                )}
                {providerAvailability === 'completed' && summary.disconnected > 0 && (
                  <div className="flex items-center justify-between rounded-xl px-3 py-2.5 text-sm">
                    <span className="text-muted-foreground/70">Not verified</span>
                    <span className="text-xs font-bold text-gray-400">{summary.disconnected}/{summary.total}</span>
                  </div>
                )}
                {providerAvailability === 'completed' && summary.total === 0 && (
                  <p className="px-3 py-2 text-xs text-slate-300">No providers were returned.</p>
                )}
                {providerAvailability !== 'completed' && (
                  <p role="status" className="px-3 py-2 text-xs text-slate-300">
                    {providerAvailability === 'unauthorized'
                      ? 'Provider inventory requires administrator access.'
                      : providerAvailability === 'idle' || providerAvailability === 'loading'
                        ? 'Provider inventory is loading.'
                        : 'Provider inventory is unavailable.'}
                  </p>
                )}
              </div>
          </div>
        </ScrollArea>

        {/* Backend Status */}
        <div className="border-t border-white/5 p-4">
          <div className="rounded-xl bg-white/[0.03] border border-white/5 p-3">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap className="h-3.5 w-3.5 text-amber-400" />
                <span className="text-xs font-medium text-slate-300">Backend API connection</span>
              </div>
              <span className={`text-xs font-semibold ${backendStatusClass}`}>{backendStatusLabel}</span>
            </div>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs text-slate-400">
              <span>Latency: {backend.latencyMs ? `${backend.latencyMs}ms` : 'Not measured'}</span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}

export type { NavItem };
