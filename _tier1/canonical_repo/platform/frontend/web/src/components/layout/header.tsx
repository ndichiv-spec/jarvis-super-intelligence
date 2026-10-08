'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import { useTheme } from 'next-themes';
import { motion } from 'framer-motion';
import {
  Menu, Search, Bell, Sun, Moon, User, Settings,
  LogOut, Globe, ChevronDown, Command, CheckCheck,
  Activity, Shield, Brain,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Separator } from '@/components/ui/separator';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useAuthStore } from '@/stores/authStore';
import { useGlobalSearchStore } from '@/features/search/store';
import {
  useSystemUsage,
  useBackend,
  useNotifications,
  useActivity,
  usePlatformStore,
} from '@/stores/platform-store';

// Import the GlobalSearch component (federated search across all domains)
const GlobalSearchComponent = dynamic(() => import('@/components/global-search/GlobalSearch').then(m => ({ default: m.GlobalSearch })), { ssr: false });

interface NotificationItem {
  id: string;
  title: string;
  detail: string;
  time: string;
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical';
  domain: string;
}

/**
 * Fetch real notifications from the backend.
 * Falls back to platform store activity events if the dedicated notification
 * endpoint is unavailable (e.g., not authenticated).
 */
async function fetchBackendNotifications(): Promise<NotificationItem[]> {
  const items: NotificationItem[] = [];
  const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/api/v1/monitoring/health-report`);
    if (res.ok) {
      const d = await res.json();
      items.push({
        id: 'backend-health',
        title: d.status === 'healthy' ? 'Backend Healthy' : 'Backend Degraded',
        detail: `Health: ${d.health_score ?? 'n/a'} · Status: ${d.status || 'unknown'}`,
        time: now,
        severity: 'info',
        domain: 'system',
      });
    }
  } catch {
    items.push({
      id: 'backend-offline',
      title: 'Backend Unreachable',
      detail: 'Could not reach the JARVIS backend. Check that :8000 is running.',
      time: now,
      severity: 'critical',
      domain: 'system',
    });
  }

  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/silverwing/api/laboratory/model`);
    if (res.ok) {
      const d = await res.json();
      items.push({
        id: 'silverwing',
        title: `Silverwing Training`,
        detail: `Step ${d.current_step ?? '?'} / ${d.total_steps ?? '?'} · loss ${d.loss ?? 'n/a'} · ${d.status || 'idle'}`,
        time: now,
        severity: 'info',
        domain: 'training',
      });
    }
  } catch { /* optional */ }

  return items;
}

interface HeaderProps {
  onMenuToggle: () => void;
  onCommandOpen: () => void;
  menuOpen: boolean;
}

export function Header({ onMenuToggle, onCommandOpen, menuOpen }: HeaderProps) {
  const { theme, setTheme } = useTheme();
  const [localNotifs, setLocalNotifs] = useState<NotificationItem[]>([]);
  const [readIds, setReadIds] = useState<Set<string>>(new Set());
  const [mounted, setMounted] = useState(false);

  // Defer to client-side theme resolution after mount to prevent
  // hydration mismatches (server always renders 'dark').
  useEffect(() => {
    const timer = window.setTimeout(() => setMounted(true), 0);
    return () => window.clearTimeout(timer);
  }, []);
  const resolvedTheme = mounted && theme ? theme : 'dark';

  const backend = useBackend();
  const systemUsage = useSystemUsage();
  const platformNotifs = useNotifications();
  const user = useAuthStore((s) => s.user);
  const backendStatusLabel = backend.status === 'idle' || backend.status === 'loading'
    ? 'Checking'
    : backend.status === 'unauthorized'
      ? 'Access restricted'
      : backend.connected
        ? 'Connected'
        : backend.status === 'degraded'
          ? 'Degraded'
          : 'Unavailable';
  const backendStatusDot = backend.connected
    ? 'bg-emerald-500'
    : backend.status === 'idle' || backend.status === 'loading'
      ? 'bg-slate-400'
      : backend.status === 'degraded' || backend.status === 'unauthorized'
        ? 'bg-amber-300'
        : 'bg-rose-300';

  // Merge backend notifications with platform store notifications
  const mergedNotifs: NotificationItem[] = [
    ...localNotifs,
    ...platformNotifs.map((n) => ({
      id: n.id,
      title: n.title,
      detail: n.detail,
      time: new Date(n.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      severity: n.severity,
      domain: n.domain,
    })),
  ];

  const refreshNotifications = useCallback(async () => {
    setLocalNotifs(await fetchBackendNotifications());
  }, []);

  // Initial load + periodic poll of backend notifications
  useEffect(() => {
    const initialTimer = window.setTimeout(() => {
      void refreshNotifications();
    }, 0);
    const id = setInterval(refreshNotifications, 30000);
    return () => {
      window.clearTimeout(initialTimer);
      clearInterval(id);
    };
  }, [refreshNotifications]);

  const unread = mergedNotifs.filter((n) => !readIds.has(n.id)).length;

  const handleLogout = useCallback(async () => {
    try {
      await useAuthStore.getState().logout();
    } catch {
      // best-effort
    }
    window.location.href = '/login';
  }, []);

  const cpuPercent = systemUsage?.cpu_percent ?? 0;

  return (
    <header className="sticky top-0 z-30 flex h-16 min-w-0 items-center gap-2 border-b border-white/5 bg-[hsl(222,47%,8%)]/80 px-2 backdrop-blur-xl sm:gap-4 sm:px-4 lg:px-6">
      <Button variant="ghost" size="icon" onClick={onMenuToggle} aria-label="Toggle navigation menu" aria-controls="primary-navigation" aria-expanded={menuOpen} className="h-9 w-9 shrink-0 lg:hidden">
        <Menu aria-hidden="true" className="h-5 w-5" />
      </Button>

      {/* Identity + Context Bar */}
      <div className="hidden items-center gap-2 lg:flex">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500/20 to-cyan-500/20 border border-blue-500/10">
          <Brain className="h-4 w-4 text-blue-400" />
        </div>
        <span className="text-sm font-semibold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
          JARVIS Command Center
        </span>
        {backend.connected && (
          <span className="text-xs font-medium text-emerald-200">Backend API connected</span>
        )}
      </div>

      {/* Context: active compute + model/provider */}
      {systemUsage && (
        <div className="hidden items-center gap-3 text-[11px] text-muted-foreground/50 md:flex">
          <span className="flex items-center gap-1">
            <Activity className="h-3 w-3" />
            CPU {Math.round(cpuPercent)}%
          </span>
          <Separator orientation="vertical" className="h-3 bg-white/5" />
          <span className="flex items-center gap-1">
            <Brain className="h-3 w-3" />
            {backend.latencyMs ? `${backend.latencyMs}ms` : '—'}
          </span>
        </div>
      )}

      <div className="min-w-0 flex-1 md:max-w-xl">
        <GlobalSearchComponent
          onNavigate={(result) => {
            if (result.url) window.open(result.url, '_blank');
          }}
          placeholder="Search across JARVIS — knowledge, memory, chat, agents, browser..."
        />
      </div>

      <div className="flex shrink-0 items-center gap-1 sm:gap-2">
        {/* Connection State — real backend connectivity */}
        <div role="status" aria-label={`Backend API ${backendStatusLabel.toLowerCase()}`} className="flex items-center gap-1.5 rounded-full border border-white/5 bg-white/[0.02] px-2 py-1 sm:px-3">
          <span aria-hidden="true" className={`inline-flex h-2 w-2 rounded-full ${backendStatusDot}`} />
          <span aria-hidden="true" className="hidden text-xs font-medium text-slate-300 sm:inline">
            API {backendStatusLabel}
          </span>
        </div>

        {/* Security Status */}
        <Button variant="ghost" size="icon" aria-label="Security status" className="hidden h-9 w-9 text-muted-foreground/60 hover:text-foreground sm:inline-flex">
          <Shield aria-hidden="true" className="h-5 w-5" />
        </Button>

        {/* Activity Stream Access */}
        <Button
          variant="ghost"
          size="icon"
          aria-label="Open activity stream"
          className="hidden h-9 w-9 text-muted-foreground/60 hover:text-foreground sm:inline-flex"
          title="Activity stream (⌘+Shift+A)"
          onClick={() => {
            usePlatformStore.getState().setWorkspace({ panelState: { ...usePlatformStore.getState().workspace.panelState, activityPanel: { open: true } } });
          }}
        >
          <Activity aria-hidden="true" className="h-5 w-5" />
        </Button>

        {/* Notifications — from platform store + backend */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label={`Notifications, ${unread} unread`} className="relative h-9 w-9 text-muted-foreground/60 hover:text-foreground">
              <Bell aria-hidden="true" className="h-5 w-5" />
              {unread > 0 && (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-gradient-to-r from-blue-500 to-cyan-400 text-[10px] font-bold text-white">{unread}</span>
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-80 bg-[hsl(222,47%,12%)] border-white/10">
            <DropdownMenuLabel className="flex items-center justify-between">
              <span>Notifications ({unread} unread)</span>
              <button
                className="flex items-center gap-1 text-[11px] text-muted-foreground/60 hover:text-foreground"
                onClick={() => setReadIds(new Set(mergedNotifs.map((n) => n.id)))}
              >
                <CheckCheck className="h-3 w-3" /> Mark all read
              </button>
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-white/5" />
            {mergedNotifs.length === 0 && (
              <div className="px-3 py-4 text-xs text-muted-foreground/60">No notifications</div>
            )}
            {mergedNotifs.map((n) => (
              <DropdownMenuItem
                key={n.id}
                className="flex-col items-start gap-1 py-2.5"
                onClick={() => setReadIds((prev) => new Set(prev).add(n.id))}
              >
                <div className="flex w-full items-center gap-2">
                  {!readIds.has(n.id) && <span className="h-1.5 w-1.5 rounded-full bg-blue-400" />}
                  <span className="text-xs font-medium">{n.title}</span>
                  <span className={`ml-auto text-[10px] ${
                    n.severity === 'critical' ? 'text-red-400' :
                    n.severity === 'high' ? 'text-orange-400' :
                    n.severity === 'medium' ? 'text-yellow-400' :
                    'text-muted-foreground/40'
                  }`}>{n.domain}</span>
                  <span className="text-[10px] text-muted-foreground/40">{n.time}</span>
                </div>
                <span className="text-[11px] text-muted-foreground/70">{n.detail}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Theme Toggle */}
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Switch to ${resolvedTheme === 'dark' ? 'light' : 'dark'} theme`}
          className="h-9 w-9 shrink-0 text-muted-foreground/60 hover:text-foreground transition-all hover:scale-110"
          onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
        >
          <motion.div
            initial={false}
            animate={{ rotate: resolvedTheme === 'dark' ? 0 : 180 }}
            transition={{ duration: 0.3 }}
            suppressHydrationWarning
          >
            {resolvedTheme === 'dark' ? (
              <Sun className="h-5 w-5 text-amber-400" />
            ) : (
              <Moon className="h-5 w-5 text-blue-400" />
            )}
          </motion.div>
        </Button>

        <Separator orientation="vertical" className="hidden h-6 bg-white/5 sm:block" />

        {/* User Menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" aria-label="Open user menu" className="h-9 gap-2 px-1 sm:px-2">
              <Avatar className="h-7 w-7 ring-2 ring-blue-500/20">
                <AvatarImage src={user?.avatar_url || '/avatars/default.png'} alt={user?.full_name || 'User'} />
                <AvatarFallback className="bg-gradient-to-br from-blue-500 to-cyan-400 text-white text-xs font-bold">
                  {user?.full_name?.charAt(0) || user?.email?.charAt(0) || 'A'}
                </AvatarFallback>
              </Avatar>
              <div className="hidden text-left md:block">
                <span className="block text-sm font-medium">{user?.full_name || user?.username || 'Admin'}</span>
                <span className="block text-[10px] text-muted-foreground/50">{user?.email || 'admin@jarvis.local'}</span>
              </div>
              <ChevronDown className="ml-1 h-3 w-3 text-muted-foreground/40 hidden md:block" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56 bg-[hsl(222,47%,12%)] border-white/10">
            <DropdownMenuLabel>
              <div className="flex flex-col">
                <span className="font-medium">{user?.full_name || user?.username || 'Admin'}</span>
                <span className="text-xs text-muted-foreground/50">{user?.email || 'admin@jarvis.local'}</span>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-white/5" />
            <DropdownMenuItem>
              <User className="mr-2 h-4 w-4" />Profile
            </DropdownMenuItem>
            <DropdownMenuItem>
              <Settings className="mr-2 h-4 w-4" />Settings
            </DropdownMenuItem>
            <DropdownMenuItem>
              <Globe className="mr-2 h-4 w-4" />API Docs
            </DropdownMenuItem>
            <DropdownMenuSeparator className="bg-white/5" />
            <DropdownMenuItem
              className="text-red-400 focus:text-red-400 focus:bg-red-500/10"
              onClick={handleLogout}
            >
              <LogOut className="mr-2 h-4 w-4" />Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
