'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { usePathname, useRouter } from 'next/navigation';
import {
  Menu, Bell, Settings,
  LogOut, Globe, ChevronDown, CheckCheck,
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
import { toast } from 'sonner';
import { API_ENDPOINTS } from '@/config/api';
import { apiClient } from '@/lib/api-client';
import {
  useSystemUsage,
  useBackend,
  useNotifications,
  usePlatformStore,
} from '@/stores/platform-store';

// Import the GlobalSearch component (federated search across all domains)
const GlobalSearchComponent = dynamic(() => import('@/components/global-search/GlobalSearch').then(m => ({ default: m.GlobalSearch })), { ssr: false });

const SEARCH_SOURCE_ROUTES: Record<string, string> = {
  knowledge: '/dashboard/knowledge',
  memory: '/dashboard/memory',
  chat: '/dashboard',
  agents: '/dashboard/agents',
  tasks: '/dashboard/agents',
  browser: '/dashboard/embedded-browser',
  notes: '/dashboard/knowledge',
  reminders: '/dashboard',
  research: '/dashboard/search',
  missions: '/dashboard/agents',
  evidence: '/dashboard/embedded-browser',
  learning: '/dashboard/bio-growth',
};

interface NotificationItem {
  id: string;
  title: string;
  detail: string;
  time: string;
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical';
  domain: string;
  read?: boolean;
}

interface BackendNotification {
  id: string;
  title: string;
  detail: string;
  severity: NotificationItem['severity'];
  domain: string;
  created_at: string;
  read: boolean;
}

async function fetchBackendNotifications(): Promise<NotificationItem[] | null> {
  try {
    const response = await apiClient.get<{ notifications: BackendNotification[] }>(
      API_ENDPOINTS.notifications.list,
      { params: { limit: 50 } },
    );
    return response.notifications.map((notification) => ({
      id: notification.id,
      title: notification.title,
      detail: notification.detail,
      time: new Date(notification.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      severity: notification.severity,
      domain: notification.domain,
      read: notification.read,
    }));
  } catch {
    console.error('Could not load user notifications.');
    return null;
  }
}

interface HeaderProps {
  navOpen: boolean;
  onMenuToggle: () => void;
}

export function Header({ navOpen, onMenuToggle }: HeaderProps) {
  const router = useRouter();
  const pathname = usePathname() || '/';
  const [localNotifs, setLocalNotifs] = useState<NotificationItem[]>([]);
  const [notificationState, setNotificationState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [readIds, setReadIds] = useState<Set<string>>(new Set());

  const backend = useBackend();
  const systemUsage = useSystemUsage();
  const platformNotifs = useNotifications();
  const user = useAuthStore((s) => s.user);
  const routeContext = pathname === '/'
    ? 'Conversation'
    : pathname.split('/').filter((segment) => segment && segment !== 'dashboard')
      .map((segment) => segment.replaceAll('-', ' '))
      .join(' / ') || 'Workspace';

  // Merge backend notifications with platform store notifications
  const mergedNotifs = useMemo<NotificationItem[]>(() => [
    ...localNotifs,
    ...platformNotifs.map((n) => ({
      id: n.id,
      title: n.title,
      detail: n.detail,
      time: new Date(n.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      severity: n.severity,
      domain: n.domain,
    })),
  ], [localNotifs, platformNotifs]);

  const refreshNotifications = useCallback(async () => {
    const notifications = await fetchBackendNotifications();
    if (notifications === null) {
      setNotificationState('error');
      return;
    }
    setLocalNotifs(notifications);
    setNotificationState('ready');
  }, []);

  // Initial load + periodic poll of backend notifications
  useEffect(() => {
    const timeout = window.setTimeout(() => void refreshNotifications(), 0);
    const id = setInterval(refreshNotifications, 30000);
    return () => {
      window.clearTimeout(timeout);
      clearInterval(id);
    };
  }, [refreshNotifications]);

  const unread = mergedNotifs.filter((n) => !n.read && !readIds.has(n.id)).length;

  const markNotificationRead = async (notification: NotificationItem) => {
    setReadIds((previous) => new Set(previous).add(notification.id));
    if (notification.id.startsWith('notification-')) {
      setLocalNotifs((items) => items.map((item) =>
        item.id === notification.id ? { ...item, read: true } : item
      ));
      try {
        await apiClient.post(API_ENDPOINTS.notifications.markRead(notification.id));
      } catch {
        console.error('Could not mark notification as read.');
        setReadIds((previous) => {
          const next = new Set(previous);
          next.delete(notification.id);
          return next;
        });
        setLocalNotifs((items) => items.map((item) =>
          item.id === notification.id ? { ...item, read: false } : item
        ));
      }
    }
  };

  const markAllNotificationsRead = async () => {
    setReadIds(new Set(mergedNotifs.map((notification) => notification.id)));
    setLocalNotifs((items) => items.map((item) => ({ ...item, read: true })));
    try {
      await apiClient.post(API_ENDPOINTS.notifications.markAllRead);
    } catch {
      console.error('Could not mark all notifications as read.');
      void refreshNotifications();
    }
  };

  const handleLogout = useCallback(async () => {
    try {
      await useAuthStore.getState().logout();
    } catch {
      // best-effort
    }
    window.location.href = '/login';
  }, []);

  return (
    <header className="sticky top-0 z-30 flex min-h-16 min-w-0 w-full max-w-full flex-wrap items-center gap-2 border-b border-slate-800/80 bg-[#090f1b] px-3 py-2 sm:h-16 sm:flex-nowrap sm:gap-4 sm:px-4 sm:py-0 lg:px-6">
      <Button
        variant="ghost"
        size="icon"
        onClick={onMenuToggle}
        aria-label={navOpen ? 'Close navigation' : 'Open navigation'}
        aria-expanded={navOpen}
        aria-controls="primary-navigation"
        className="h-9 w-9 md:hidden"
      >
        <Menu className="h-5 w-5" />
      </Button>

      {/* Identity + Context Bar */}
      <div className="hidden min-w-0 items-center gap-3 lg:flex">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-indigo-300/15 bg-indigo-300/[0.07]">
          <Brain className="h-4 w-4 text-blue-400" />
        </div>
        <div className="flex min-w-0 flex-col justify-center">
          <span className="text-[12px] font-semibold tracking-[0.08em] text-slate-100">JARVIS</span>
          <span className="max-w-[230px] truncate text-[10px] capitalize tracking-wide text-slate-500">{routeContext}</span>
        </div>
      </div>

      {/* Context: active compute + model/provider */}
      {systemUsage && (
        <div className="hidden items-center gap-3 text-[11px] text-muted-foreground/50 md:flex">
          <span className="flex items-center gap-1">
            <Activity className="h-3 w-3" />
            CPU {systemUsage ? `${Math.round(systemUsage.cpu_percent)}%` : 'CPU not reported'}
          </span>
          <Separator orientation="vertical" className="h-3 bg-white/5" />
          <span className="flex items-center gap-1">
            <Brain className="h-3 w-3" />
            {backend.latencyMs ? `${backend.latencyMs}ms` : '—'}
          </span>
        </div>
      )}

      <div className="order-3 w-full min-w-0 basis-full flex-1 sm:order-none sm:w-auto sm:basis-auto md:max-w-xl">
        <GlobalSearchComponent
          onNavigate={(result) => {
            const candidate = result.route || result.url;
            if (candidate && URL.canParse(candidate, window.location.origin)) {
              const destination = new URL(candidate, window.location.origin);
              if (
                destination.origin === window.location.origin &&
                destination.pathname.startsWith('/dashboard/')
              ) {
                router.push(`${destination.pathname}${destination.search}${destination.hash}`);
                return;
              }
              if (
                destination.origin !== window.location.origin &&
                (destination.protocol === 'http:' || destination.protocol === 'https:')
              ) {
                router.push(`/dashboard/embedded-browser?url=${encodeURIComponent(destination.toString())}`);
                return;
              }
            }
            const fallbackRoute = SEARCH_SOURCE_ROUTES[result.source.toLowerCase()];
            if (fallbackRoute) router.push(fallbackRoute);
            else toast.error('No JARVIS destination is available for this search result.');
          }}
          placeholder="Search across JARVIS — knowledge, memory, chat, agents, browser..."
        />
      </div>

      <div className="ml-auto flex min-w-0 shrink-0 items-center gap-1 sm:gap-2">
        {/* Connection State — real backend connectivity */}
        <div className="flex items-center gap-1.5 rounded-full border border-white/5 bg-white/[0.02] px-2.5 py-1 sm:px-3">
            <span aria-hidden="true" className={`inline-flex h-2 w-2 rounded-full ${
              backend.connected ? 'bg-emerald-500' : backend.status === 'loading' || backend.status === 'idle' || backend.status === 'degraded' ? 'bg-amber-400' : 'bg-rose-400'
            }`} />
            <span className="sr-only">
              Backend {backend.connected ? 'reachable' : backend.status === 'loading' || backend.status === 'idle' ? 'checking' : backend.status === 'degraded' ? 'degraded' : 'unavailable'}
            </span>
          <span className="hidden text-[10px] font-medium text-muted-foreground/60 sm:inline">
            {backend.connected
              ? 'Reachable'
              : backend.status === 'idle' || backend.status === 'loading'
                ? 'Checking'
                : backend.status === 'degraded'
                  ? 'Degraded'
                  : 'Unavailable'}
          </span>
        </div>

        {/* Security Status */}
        <Button
          variant="ghost"
          size="icon"
          aria-label="Open security"
          onClick={() => router.push('/dashboard/security')}
          className="hidden h-9 w-9 text-muted-foreground/60 hover:text-foreground md:inline-flex"
        >
          <Shield className="h-5 w-5" />
        </Button>

        {/* Activity Stream Access */}
        <Button
          variant="ghost"
          size="icon"
          aria-label="Open activity stream"
          className="h-9 w-9 text-muted-foreground/60 hover:text-foreground"
          title="Recent activity (⌘+Shift+A)"
          onClick={() => {
            usePlatformStore.getState().setWorkspace({ panelState: { ...usePlatformStore.getState().workspace.panelState, activityPanel: { open: true } } });
          }}
        >
          <Activity className="h-5 w-5" />
        </Button>

        {/* Notifications — from platform store + backend */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label={`Notifications${unread > 0 ? `, ${unread} unread` : ''}`} className="relative h-9 w-9 text-muted-foreground/60 hover:text-foreground">
              <Bell className="h-5 w-5" />
              {unread > 0 && (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-gradient-to-r from-blue-500 to-cyan-400 text-[10px] font-bold text-white">{unread}</span>
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-80 bg-[hsl(222,47%,12%)] border-white/10">
            <DropdownMenuLabel className="flex items-center justify-between">
              <span>Notifications ({unread} unread)</span>
              <button
                type="button"
                disabled={unread === 0}
                className="flex items-center gap-1 text-[11px] text-muted-foreground/60 hover:text-foreground"
                onClick={() => void markAllNotificationsRead()}
              >
                <CheckCheck className="h-3 w-3" /> Mark all read
              </button>
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-white/5" />
            {notificationState === 'error' && (
              <div role="status" className="px-3 py-3 text-xs text-amber-200/80">
                Backend notifications could not be loaded.
              </div>
            )}
            {mergedNotifs.length === 0 && notificationState === 'loading' && (
              <div role="status" className="px-3 py-4 text-xs text-muted-foreground/60">Loading notifications…</div>
            )}
            {mergedNotifs.length === 0 && notificationState === 'ready' && (
              <div className="px-3 py-4 text-xs text-muted-foreground/60">No notifications reported.</div>
            )}
            {mergedNotifs.map((n) => (
              <DropdownMenuItem
                key={n.id}
                className="flex-col items-start gap-1 py-2.5"
                onClick={() => void markNotificationRead(n)}
              >
                <div className="flex w-full items-center gap-2">
                  {!n.read && !readIds.has(n.id) && <span className="h-1.5 w-1.5 rounded-full bg-blue-400" />}
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

        <Separator orientation="vertical" className="h-6 bg-white/5" />

        {/* User Menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              className="h-9 gap-2 px-2"
              aria-label={`Account menu for ${user?.full_name || user?.username || user?.email || 'account'}`}
            >
              <Avatar className="h-7 w-7 ring-2 ring-blue-500/20">
                {user?.avatar_url && <AvatarImage src={user.avatar_url} alt={user.full_name || 'Account'} />}
                <AvatarFallback className="bg-gradient-to-br from-blue-500 to-cyan-400 text-white text-xs font-bold">
                  {user?.full_name?.charAt(0) || user?.email?.charAt(0) || 'J'}
                </AvatarFallback>
              </Avatar>
              <div className="hidden text-left md:block">
                <span className="block text-sm font-medium">{user?.full_name || user?.username || user?.email || 'Account'}</span>
                <span className="block text-[10px] text-muted-foreground/50">{user?.email || 'Signed-in account'}</span>
              </div>
              <ChevronDown className="ml-1 h-3 w-3 text-muted-foreground/40 hidden md:block" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56 bg-[hsl(222,47%,12%)] border-white/10">
            <DropdownMenuLabel>
              <div className="flex flex-col">
                <span className="font-medium">{user?.full_name || user?.username || user?.email || 'Account'}</span>
                <span className="text-xs text-muted-foreground/50">{user?.email || 'Signed-in account'}</span>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-white/5" />
            <DropdownMenuItem onSelect={() => router.push('/dashboard/settings')}>
              <Settings className="mr-2 h-4 w-4" />Settings
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => router.push('/dashboard/capabilities')}>
              <Globe className="mr-2 h-4 w-4" />Capabilities
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
