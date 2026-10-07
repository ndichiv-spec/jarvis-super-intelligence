'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion } from 'framer-motion';
import {
  Brain, Bot, Cpu, Activity, BookOpen, Settings, Shield,
  MessageSquare, Workflow, MonitorPlay, Code2,
  ArrowUpCircle, Library, Server, Globe, Zap,
  Crown, Sparkles, Terminal, Mail, Puzzle,
  Mic, Image, Eye, Box, Network, Search,
  Bell, Lock, Key, GitBranch, Target, Gauge,
  FileText, Palette, Wrench, Database, ArrowLeftRight,
  FlaskConical, Satellite, ShieldCheck, Users,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useChatStore } from '@/features/chat/store';
import {
  useSystemUsage,
  useBackend,
  useProviders,
  useSilverwing,
  usePlatformStore,
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
  { label: 'JARVIS Copilot', href: '/dashboard/copilot', icon: MessageSquare, category: 'AI Core', crossReference: '/dashboard/agents' },
  { label: 'Agent Orchestration', href: '/dashboard/agents', icon: Bot, category: 'AI Core', crossReference: '/dashboard/monitoring' },
  { label: 'Supreme', href: '/supreme', icon: Crown, category: 'AI Core', crossReference: '/dashboard/agents' },
  { label: 'Voice', href: '/voice', icon: Mic, badge: 'BETA', category: 'AI Core', crossReference: '/dashboard/memory' },
  { label: 'Image', href: '/image-generation', icon: Image, badge: 'AI', category: 'AI Core', crossReference: '/dashboard/knowledge' },
  { label: 'Bio-Growth Lab', href: '/dashboard/bio-growth', icon: FlaskConical, category: 'AI Core', crossReference: '/dashboard/knowledge' },

  // Workspace — productive environments
  { label: 'Desktop', href: '/desktop', icon: MonitorPlay, badge: 'NEW', category: 'Workspace', crossReference: '/dashboard/embedded-browser' },
  { label: 'Browser', href: '/dashboard/embedded-browser', icon: Globe, category: 'Workspace', crossReference: '/dashboard/knowledge' },
  { label: 'Maps & Geography', href: '/dashboard/geography', icon: Satellite, category: 'Workspace', crossReference: '/dashboard/search' },
  { label: 'Workflows', href: '/workflows', icon: Workflow, category: 'Workspace', crossReference: '/dashboard/agents' },
  { label: 'Runtime Status', href: '/dashboard/runtime-status', icon: Activity, badge: 'LIVE', category: 'Workspace', crossReference: '/dashboard/monitoring' },
  { label: 'IDE', href: '/dashboard/self-reliant', icon: Code2, badge: 'NEW', category: 'Workspace', crossReference: '/dashboard/extensions' },

  // Infrastructure — system backbone
  { label: 'Command Center', href: '/dashboard/commands', icon: Activity, category: 'Infrastructure', crossReference: '/dashboard/monitoring' },
  { label: 'System Control', href: '/dashboard/system', icon: Cpu, category: 'Infrastructure', crossReference: '/dashboard/connections' },
  { label: 'Capability Readiness', href: '/dashboard/capabilities', icon: Gauge, category: 'Infrastructure', crossReference: '/dashboard/settings' },
  { label: 'Knowledge Studio', href: '/dashboard/knowledge', icon: BookOpen, category: 'Infrastructure', crossReference: '/dashboard/search' },
  { label: 'Memory', href: '/dashboard/memory', icon: Library, category: 'Infrastructure', crossReference: '/dashboard/knowledge' },
  { label: 'Connections', href: '/dashboard/connections', icon: Mail, category: 'Infrastructure', crossReference: '/dashboard/extensions' },
  { label: 'Stark Control', href: '/stark-control', icon: Terminal, badge: 'CORE', category: 'Infrastructure', crossReference: '/dashboard/system' },
  { label: 'File Browser', href: '/dashboard/files', icon: FileText, category: 'Infrastructure', crossReference: '/dashboard/system' },

  // System — configuration and management
  { label: 'Settings', href: '/dashboard/settings', icon: Settings, category: 'System', crossReference: '/dashboard/admin' },
  { label: 'Extensions', href: '/dashboard/extensions', icon: Puzzle, category: 'System', crossReference: '/dashboard/connections' },
  { label: 'Admin Console', href: '/dashboard/admin', icon: Shield, badge: 'ENT', category: 'System', crossReference: '/dashboard/settings' },
  { label: 'Self-Upgrade', href: '/upgrade', icon: ArrowUpCircle, category: 'System', crossReference: '/omega' },

  // Enterprise — security and compliance
  { label: 'Security', href: '/dashboard/security', icon: Shield, badge: 'SEC', category: 'Enterprise', crossReference: '/dashboard/admin' },
  { label: 'Enterprise SSO', href: '/enterprise-sso', icon: Lock, category: 'Enterprise', crossReference: '/dashboard/admin' },
  { label: 'API Keys', href: '/dashboard/api-keys', icon: Key, category: 'Enterprise', crossReference: '/dashboard/settings' },
  { label: 'Research & Discovery', href: '/dashboard/search', icon: Search, category: 'Enterprise', crossReference: '/dashboard/knowledge' },
];

const SIDEBAR_WIDTH = 280;

interface SidebarProps {
  isMobile: boolean;
  isOpen: boolean;
  onClose: () => void;
}

export function Sidebar({ isMobile, isOpen, onClose }: SidebarProps) {
  const pathname = usePathname();
  const connected = useChatStore((s) => s.connected);
  const systemUsage = useSystemUsage();
  const backend = useBackend();
  const { summary } = useProviders();
  const silverwing = useSilverwing();
  const activeModel = useChatStore((s) => s.activeModel);

  // Subscribe to platform data — refresh on mount
  useEffect(() => {
    const refresh = async () => {
      await usePlatformStore.getState().refreshAll();
      // Poll every 30s for system metrics (public endpoint, no auth needed)
      const interval = setInterval(() => {
        usePlatformStore.getState().refreshSystem();
        usePlatformStore.getState().refreshBackend();
      }, 30000);
      return () => clearInterval(interval);
    };
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const cpuPercent = systemUsage?.cpu_percent ?? 0;
  const memPercent = systemUsage?.memory_percent ?? 0;
  const diskPercent = systemUsage?.disk_percent ?? 0;
  const processCount = systemUsage?.processes ?? 0;
  const connectionLabel = backend.connected
    ? 'Connected'
    : backend.status === 'idle' || backend.status === 'loading'
      ? 'Checking'
      : backend.status === 'degraded'
        ? 'Degraded'
        : 'Unavailable';
  const connectionTone = backend.connected
    ? 'text-emerald-400'
    : backend.status === 'idle' || backend.status === 'loading' || backend.status === 'degraded'
      ? 'text-amber-300'
      : 'text-red-400';

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
            <span className="absolute -right-0.5 -top-0.5 flex h-3 w-3">
              {connected && backend.connected && (
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              )}
              <span className={`relative inline-flex h-3 w-3 rounded-full border-2 border-[hsl(222,47%,8%)] ${
                connected && backend.connected ? 'bg-emerald-500' : 'bg-red-500'
              }`} />
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
                <div className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/40">
                  {category}
                </div>
                <div className="space-y-1">
                  {items.map((item) => {
                    const active = isActive(item.href);
                    const Icon = item.icon;
                    return (
                      <Link key={item.href} href={item.href} onClick={isMobile ? onClose : undefined}>
                        <motion.div
                          whileHover={{ x: 4 }}
                          className={`relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all ${
                            active
                              ? 'bg-gradient-to-r from-blue-500/15 to-cyan-500/10 text-blue-400 border border-blue-500/20'
                              : 'text-muted-foreground/70 hover:bg-white/5 hover:text-foreground'
                          }`}
                        >
                          {active && (
                            <motion.div
                              layoutId="activeNav"
                              className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-1 rounded-r-full bg-gradient-to-b from-blue-400 to-cyan-400"
                            />
                          )}
                          <Icon className={`h-5 w-5 shrink-0 ${active ? 'text-blue-400' : 'text-muted-foreground/50'}`} />
                          <span className="flex-1">{item.label}</span>
                          {item.badge && (
                            <Badge className={`h-4 px-1.5 text-[9px] font-bold ${
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
            <div className="px-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/40">
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
                    className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-muted-foreground/50 hover:bg-white/5 hover:text-foreground transition-all cursor-pointer"
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
            <div className="px-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/40">
              System Metrics
            </div>
            <div className="space-y-1">
              {[
                { label: 'CPU Usage', value: systemUsage ? `${Math.round(cpuPercent)}%` : '—', icon: Cpu, color: 'text-blue-400', status: cpuPercent > 80 ? 'critical' : cpuPercent > 60 ? 'warning' : 'good' },
                { label: 'Memory', value: systemUsage ? `${Math.round(memPercent)}%` : '—', icon: Database, color: 'text-cyan-400', status: memPercent > 85 ? 'critical' : memPercent > 70 ? 'warning' : 'good' },
                { label: 'Disk', value: systemUsage ? `${Math.round(diskPercent)}%` : '—', icon: Gauge, color: 'text-purple-400', status: diskPercent > 85 ? 'critical' : diskPercent > 70 ? 'warning' : 'good' },
                { label: 'Active Processes', value: systemUsage ? processCount.toLocaleString() : '—', icon: Activity, color: 'text-emerald-400', status: systemUsage ? 'good' as const : 'unknown' as const },
                { label: 'Backend API', value: connectionLabel, icon: Server, color: backend.connected ? 'text-emerald-400' : 'text-red-400', status: backend.connected ? 'good' : 'critical' },
                { label: 'Silverwing', value: silverwing.connected ? `${silverwing.status || 'idle'}` : 'Offline', icon: Zap, color: silverwing.connected ? 'text-amber-400' : 'text-gray-400', status: silverwing.connected ? 'good' : 'offline' },
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

          {/* Provider Connection Summary */}
          {summary.total > 0 && (
            <div className="mt-6 space-y-2 px-3">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/40">
                Provider Fleet
              </div>
              <div className="space-y-1">
                {summary.connected > 0 && (
                  <div className="flex items-center justify-between rounded-xl px-3 py-2.5 text-sm">
                    <span className="text-muted-foreground/70">Connected</span>
                    <span className="text-xs font-bold text-emerald-400">{summary.connected}/{summary.total}</span>
                  </div>
                )}
                {summary.disconnected > 0 && (
                  <div className="flex items-center justify-between rounded-xl px-3 py-2.5 text-sm">
                    <span className="text-muted-foreground/70">Offline</span>
                    <span className="text-xs font-bold text-gray-400">{summary.disconnected}/{summary.total}</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </ScrollArea>

        {/* System Status Bar */}
        <div className="border-t border-white/5 p-4">
          <div className="rounded-xl bg-white/[0.03] border border-white/5 p-3">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap className="h-3.5 w-3.5 text-amber-400" />
                <span className="text-[11px] font-medium text-muted-foreground/60">System Status</span>
              </div>
              <span className={`text-xs font-bold ${connectionTone}`}>{connectionLabel}</span>
            </div>
            <div className="mt-2 flex items-center justify-between text-[10px] text-muted-foreground/40">
              <span>Chat model: {activeModel || 'Auto-Select'}</span>
              <span>Latency: {backend.latencyMs ? `${backend.latencyMs}ms` : '—'}</span>
            </div>
            <p className="mt-1 text-[10px] text-muted-foreground/40">
              Last checked: {backend.lastChecked ? backend.lastChecked.toLocaleTimeString() : 'not checked yet'}
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}

export type { NavItem };
