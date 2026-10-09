'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity, ArrowUpCircle, BookOpen, Bot, Brain, BriefcaseBusiness, ChevronDown,
  Code2, Command, Cpu, Database, FileText, FlaskConical, Gauge, Globe,
  KeyRound, Layers3, Library, LockKeyhole, Mail, Map, MessageSquare,
  Monitor, Puzzle, Search, Settings2, ShieldCheck, Sparkles, Terminal,
  Users, Workflow, X,
} from 'lucide-react';
import { useBackend, useProviders, useSystemUsage } from '@/stores/platform-store';

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
}

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: 'Workspace',
    items: [
      { label: 'Conversation', href: '/dashboard', icon: MessageSquare },
      { label: 'Agents & tasks', href: '/dashboard/agents', icon: Bot },
      { label: 'Copilot', href: '/dashboard/copilot', icon: Sparkles },
      { label: 'Sessions', href: '/dashboard/sessions', icon: Users },
      { label: 'Browser', href: '/dashboard/embedded-browser', icon: Globe },
      { label: 'Files', href: '/dashboard/files', icon: FileText },
      { label: 'Workflows', href: '/workflows', icon: Workflow },
      { label: 'Desktop', href: '/desktop', icon: Monitor },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { label: 'Knowledge', href: '/dashboard/knowledge', icon: BookOpen },
      { label: 'Memory', href: '/dashboard/memory', icon: Library },
      { label: 'Research', href: '/dashboard/search', icon: Search },
      { label: 'Cognitive', href: '/dashboard/cognitive', icon: Brain },
      { label: 'Capabilities', href: '/dashboard/capabilities', icon: Gauge },
      { label: 'Developer capabilities', href: '/dashboard/developer/capabilities', icon: Code2 },
      { label: 'Bio-growth', href: '/dashboard/bio-growth', icon: FlaskConical },
      { label: 'Geography', href: '/dashboard/geography', icon: Map },
    ],
  },
  {
    label: 'Operations',
    items: [
      { label: 'Monitoring', href: '/dashboard/monitoring', icon: Activity },
      { label: 'Runtime status', href: '/dashboard/runtime-status', icon: Layers3 },
      { label: 'System', href: '/dashboard/system', icon: Cpu },
      { label: 'System status', href: '/dashboard/system-status', icon: Gauge },
      { label: 'Commands', href: '/dashboard/commands', icon: Terminal },
      { label: 'Connections', href: '/dashboard/connections', icon: Mail },
      { label: 'Extensions', href: '/dashboard/extensions', icon: Puzzle },
      { label: 'Advanced systems', href: '/dashboard/advanced', icon: BriefcaseBusiness },
      { label: 'Operational overview', href: '/dashboard/operational', icon: Database },
      { label: 'Tier 4', href: '/dashboard/tier4', icon: Layers3 },
      { label: 'Phase 3', href: '/dashboard/phase3', icon: FlaskConical },
      { label: 'Self-reliant IDE', href: '/dashboard/self-reliant', icon: Code2 },
      { label: 'OMEGA', href: '/omega', icon: Brain },
      { label: 'Supreme', href: '/supreme', icon: Sparkles },
      { label: 'Upgrade', href: '/upgrade', icon: ArrowUpCircle },
      { label: 'Plugins', href: '/plugins', icon: Puzzle },
    ],
  },
  {
    label: 'Administration',
    items: [
      { label: 'Security', href: '/dashboard/security', icon: ShieldCheck },
      { label: 'Users & roles', href: '/dashboard/admin', icon: Users },
      { label: 'API keys', href: '/dashboard/api-keys', icon: KeyRound },
      { label: 'Settings', href: '/dashboard/settings', icon: Settings2 },
      { label: 'Enterprise SSO', href: '/enterprise-sso', icon: LockKeyhole },
      { label: 'Stark control', href: '/stark-control', icon: Command },
    ],
  },
];

interface SidebarProps {
  isMobile: boolean;
  isCompact: boolean;
  isOpen: boolean;
  onClose: () => void;
}

function isRouteActive(pathname: string, href: string) {
  if (href === '/dashboard') return pathname === '/dashboard';
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar({ isMobile, isCompact, isOpen, onClose }: SidebarProps) {
  const pathname = usePathname() || '/';
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const backend = useBackend();
  const systemUsage = useSystemUsage();
  const { summary } = useProviders();
  const connectionLabel = backend.connected
    ? 'Reachable'
    : backend.status === 'loading' || backend.status === 'idle'
      ? 'Checking'
      : backend.status === 'degraded'
        ? 'Degraded'
        : 'Unavailable';

  const navWidth = isMobile ? 'min(86vw, 304px)' : isCompact ? '76px' : '272px';
  const hidden = isMobile && !isOpen;

  return (
    <>
      {isMobile && isOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          className="fixed inset-0 z-40 cursor-default bg-slate-950/75 backdrop-blur-sm"
          onClick={onClose}
        />
      )}

      <aside
        id="primary-navigation"
        data-mobile-open={isMobile && isOpen}
        aria-label="Primary navigation"
        aria-hidden={hidden}
        inert={hidden}
        className={`jarvis-sidebar fixed inset-y-0 left-0 z-50 flex flex-col border-r border-slate-800/80 bg-[#0a1020] text-slate-200 transition-transform duration-200 ${
          hidden ? '-translate-x-full' : 'translate-x-0'
        }`}
        style={{ width: navWidth }}
      >
        <div className={`flex h-[68px] shrink-0 items-center border-b border-slate-800/80 ${isCompact ? 'justify-center px-2' : 'gap-3 px-5'}`}>
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-indigo-300/20 bg-indigo-400/[0.09] text-indigo-200">
            <Brain aria-hidden="true" className="h-[18px] w-[18px]" />
          </div>
          {!isCompact && (
            <>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-semibold tracking-[0.18em] text-slate-100">JARVIS</p>
                <p className="mt-0.5 text-[10px] tracking-wide text-slate-500">INTELLIGENCE WORKSPACE</p>
              </div>
              {isMobile && (
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Close navigation"
                  className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-white/[0.06] hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-300"
                >
                  <X aria-hidden="true" className="h-4 w-4" />
                </button>
              )}
            </>
          )}
        </div>

        <nav aria-label="Workspace sections" className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
          <div className="space-y-5">
            {NAV_GROUPS.map((group) => {
              const expanded = !collapsedGroups[group.label];
              return (
                <section key={group.label} aria-label={group.label}>
                  {!isCompact && (
                    <button
                      type="button"
                      aria-expanded={expanded}
                      onClick={() => setCollapsedGroups((current) => ({
                        ...current,
                        [group.label]: !current[group.label],
                      }))}
                      className="mb-1.5 flex w-full items-center justify-between rounded-md px-2 py-1 text-left text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500 transition hover:text-slate-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-300"
                    >
                      {group.label}
                      <ChevronDown aria-hidden="true" className={`h-3.5 w-3.5 transition-transform ${expanded ? '' : '-rotate-90'}`} />
                    </button>
                  )}
                  {(isCompact || expanded) && (
                    <ul className={`space-y-0.5 ${isCompact ? 'border-t border-slate-800/80 pt-2' : ''}`}>
                      {group.items.map((item) => {
                        const active = isRouteActive(pathname, item.href);
                        const Icon = item.icon;
                        return (
                          <li key={item.href}>
                            <Link
                              href={item.href}
                              onClick={isMobile ? onClose : undefined}
                              aria-current={active ? 'page' : undefined}
                              aria-label={isCompact ? item.label : undefined}
                              title={isCompact ? item.label : undefined}
                              className={`group relative flex min-h-9 items-center gap-3 rounded-lg px-2.5 text-[13px] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-300 ${
                                isCompact ? 'justify-center px-0' : ''
                              } ${
                                active
                                  ? 'bg-indigo-400/[0.11] text-indigo-100'
                                  : 'text-slate-400 hover:bg-white/[0.045] hover:text-slate-100'
                              }`}
                            >
                              {active && <span aria-hidden="true" className="absolute inset-y-2 left-0 w-[2px] rounded-r bg-indigo-300" />}
                              <Icon aria-hidden="true" className={`h-[17px] w-[17px] shrink-0 ${active ? 'text-indigo-200' : 'text-slate-500 group-hover:text-slate-300'}`} />
                              {!isCompact && <span className="truncate">{item.label}</span>}
                            </Link>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </section>
              );
            })}
          </div>
        </nav>

        {!isCompact && (
          <div className="shrink-0 border-t border-slate-800/80 p-4">
            <div className="rounded-xl border border-slate-800/80 bg-slate-900/55 px-3 py-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] text-slate-400">API reachability</span>
                <span className={`flex items-center gap-1.5 text-[11px] ${
                  backend.connected ? 'text-emerald-300' : backend.status === 'loading' || backend.status === 'idle' || backend.status === 'degraded' ? 'text-amber-200' : 'text-rose-300'
                }`}>
                  <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
                  {connectionLabel}
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-slate-500">
                <span>CPU {systemUsage ? `${Math.round(systemUsage.cpu_percent)}%` : 'Not reported'}</span>
                <span>
                  Providers {summary.total > 0 ? `${summary.connected}/${summary.total}` : 'Not reported'}
                </span>
              </div>
            </div>
          </div>
        )}
      </aside>
    </>
  );
}
