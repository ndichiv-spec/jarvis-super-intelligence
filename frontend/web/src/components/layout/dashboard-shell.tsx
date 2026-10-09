'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  MessageSquare, Brain, Settings, Cpu, Globe,
  Mail, Puzzle, Mic, Image as ImageIcon, Search,
  Key, FlaskConical,
  Shield, ShieldCheck, Layers, Crown, Terminal,
  Workflow, MonitorPlay, Code2, Library, Activity,
  ArrowUpCircle, Sparkles, BookOpen, X, Plus,
} from 'lucide-react';
import { Sidebar } from './sidebar';
import { Header } from './header';
import EmbeddedBrowser from '@/components/embedded-browser/EmbeddedBrowser';
import { useChatStore } from '@/features/chat/store';
import { usePlatformStore } from '@/stores/platform-store';
import { ActivityFabric } from '@/components/shell/activity-fabric';
import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput,
  CommandItem, CommandList,
} from '@/components/ui/command';
import { DialogTitle } from '@/components/ui/dialog';

interface DashboardShellProps {
  children: React.ReactNode;
}

export function DashboardShell({ children }: DashboardShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const [isCompact, setIsCompact] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [browserPanelOpen, setBrowserPanelOpen] = useState(false);
  const router = useRouter();
  const newSession = useChatStore((s) => s.newSession);

  // Subscribe to the unified platform store for shell-level data
  const platformRefreshAll = usePlatformStore((s) => s.refreshAll);
  const platformRefreshSystem = usePlatformStore((s) => s.refreshSystem);
  const platformRefreshBackend = usePlatformStore((s) => s.refreshBackend);
  const subscribeToEvents = usePlatformStore((s) => s.subscribeToEvents);
  const activityPanelOpen = usePlatformStore((s) => s.workspace.panelState?.activityPanel?.open ?? false);
  const setWorkspace = usePlatformStore((s) => s.setWorkspace);

  // The shell owns platform polling and event subscriptions for every dashboard route.
  useEffect(() => {
    void platformRefreshAll();
    const unsubscribe = subscribeToEvents();
    const interval = setInterval(() => {
      platformRefreshSystem();
      platformRefreshBackend();
    }, 30000);
    return () => {
      clearInterval(interval);
      unsubscribe();
    };
  }, [platformRefreshAll, platformRefreshBackend, platformRefreshSystem, subscribeToEvents]);

  const SIDEBAR_WIDTH = isCompact ? 76 : 272;

  const runCommand = useCallback((fn: () => void) => {
    setCommandOpen(false);
    fn();
  }, []);

  const toggleBrowserPanel = useCallback(() => {
    setBrowserPanelOpen((o) => !o);
    if (!browserPanelOpen) {
      import('@/features/browser/store').then(({ useBrowserStore }) => {
        const store = useBrowserStore.getState();
        if (!store.initialized) void store.init();
        if (!store.activeSessionId && store.sessions.length === 0) {
          void store.createSession('Browser Session').then((sess) => {
            if (sess) void store.createTab(sess.id, 'about:blank');
          });
        } else if (store.activeSessionId && !store.activeTabId) {
          void store.createTab(store.activeSessionId, 'about:blank');
        }
      });
    }
  }, [browserPanelOpen]);

  const openBrowserNewTab = useCallback(() => {
    import('@/features/browser/store').then(({ useBrowserStore }) => {
      const store = useBrowserStore.getState();
      if (!store.activeSessionId) {
        void store.createSession('Browser Session').then((sess) => {
          if (sess) void store.createTab(sess.id, 'about:blank');
        });
      } else {
        void store.createTab(store.activeSessionId, 'about:blank');
      }
    });
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Cmd/Ctrl+K → open command palette
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setCommandOpen((o) => !o);
        return;
      }
      // Cmd/Ctrl+Shift+F → open search
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        router.push('/dashboard/search');
        return;
      }
      // Escape → close panels / command palette
      if (e.key === 'Escape') {
        if (commandOpen) setCommandOpen(false);
        if (browserPanelOpen) setBrowserPanelOpen(false);
        if (activityPanelOpen) setWorkspace({ panelState: { activityPanel: { open: false } } });
        if (isMobile && sidebarOpen) setSidebarOpen(false);
        return;
      }
      // Cmd/Ctrl+1-9 → navigate to dashboard tabs
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && /^\d$/.test(e.key)) {
        const index = parseInt(e.key, 10);
        const map: Record<number, string> = {
          1: '/dashboard',
          2: '/dashboard/agents',
          3: '/dashboard/knowledge',
          4: '/dashboard/memory',
          5: '/dashboard/connections',
          6: '/dashboard/security',
          7: '/dashboard/monitoring',
          8: '/dashboard/system',
          9: '/dashboard/settings',
        };
        if (map[index]) {
          e.preventDefault();
          router.push(map[index]);
        }
        return;
      }
      // Cmd/Ctrl+B → toggle browser panel
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        toggleBrowserPanel();
        return;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [router, commandOpen, toggleBrowserPanel, isMobile, sidebarOpen, browserPanelOpen, activityPanelOpen, setWorkspace]);

  // Keep a compact icon rail at tablet widths and use a dismissible sheet on phones.
  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth < 768;
      const compact = window.innerWidth >= 768 && window.innerWidth < 1280;
      setIsMobile(mobile);
      setIsCompact(compact);
      if (mobile) setSidebarOpen(false);
      else setSidebarOpen(!compact);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  return (
    <div className="relative flex min-h-screen min-w-0 w-full max-w-full bg-[#080d17] text-slate-100">
      <Sidebar
        isMobile={isMobile}
        isCompact={isCompact}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div
        className="flex min-w-0 flex-1 flex-col transition-all duration-300"
        style={{ marginLeft: isMobile ? 0 : (isCompact ? SIDEBAR_WIDTH : sidebarOpen ? SIDEBAR_WIDTH : 0) }}
        suppressHydrationWarning
      >
        <Header
          navOpen={sidebarOpen}
          onMenuToggle={() => setSidebarOpen((o) => !o)}
        />

        <main className="min-w-0 flex-1 overflow-auto bg-grid">
          <motion.div
            key="content"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="h-full min-w-0 max-w-full"
          >
            {children}
          </motion.div>
        </main>
      </div>

      <CommandDialog open={commandOpen} onOpenChange={setCommandOpen}>
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <CommandInput placeholder="Search commands, navigate rooms..." />
        <CommandList>
          <CommandEmpty>No results found.</CommandEmpty>
          <CommandGroup heading="AI Core">
            <CommandItem onSelect={() => runCommand(() => { newSession(); router.push('/dashboard'); })}>
              <MessageSquare className="mr-2 h-4 w-4" /> Neural Chat
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/copilot'))}>
              <Sparkles className="mr-2 h-4 w-4" /> JARVIS Copilot
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/agents'))}>
              <Brain className="mr-2 h-4 w-4" /> Agent Orchestration
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/bio-growth'))}>
              <FlaskConical className="mr-2 h-4 w-4" /> Bio-Growth Lab
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/omega'))}>
              <Layers className="mr-2 h-4 w-4" /> OMEGA Control
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/supreme'))}>
              <Crown className="mr-2 h-4 w-4" /> Supreme Intelligence
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/voice'))}>
              <Mic className="mr-2 h-4 w-4" /> Voice Interface
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/image-generation'))}>
              <ImageIcon className="mr-2 h-4 w-4" /> Image Generation
            </CommandItem>
          </CommandGroup>
          <CommandGroup heading="Workspace">
            <CommandItem onSelect={() => runCommand(() => router.push('/desktop'))}>
              <MonitorPlay className="mr-2 h-4 w-4" /> Virtual Desktop
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/embedded-browser'))}>
              <Globe className="mr-2 h-4 w-4" /> Embedded Browser
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => { router.push('/dashboard/embedded-browser'); openBrowserNewTab(); })}>
              <Plus className="mr-2 h-4 w-4" /> New Browser Tab
            </CommandItem>
            <CommandItem onSelect={() => runCommand(toggleBrowserPanel)}>
              <Globe className="mr-2 h-4 w-4" /> Toggle Browser Panel
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/workflows'))}>
              <Workflow className="mr-2 h-4 w-4" /> Workflows
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/runtime-status'))}>
              <Activity className="mr-2 h-4 w-4" /> Runtime Status
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/self-reliant'))}>
              <Code2 className="mr-2 h-4 w-4" /> Self-Reliant IDE
            </CommandItem>
          </CommandGroup>
          <CommandGroup heading="Infrastructure">
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/monitoring'))}>
              <Activity className="mr-2 h-4 w-4" /> Monitoring
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/commands'))}>
              <Workflow className="mr-2 h-4 w-4" /> Command Center
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/system'))}>
              <Cpu className="mr-2 h-4 w-4" /> System Control
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/knowledge'))}>
              <BookOpen className="mr-2 h-4 w-4" /> Knowledge Studio
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/memory'))}>
              <Library className="mr-2 h-4 w-4" /> Memory Inspector
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/connections'))}>
              <Mail className="mr-2 h-4 w-4" /> Connections
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/stark-control'))}>
              <Terminal className="mr-2 h-4 w-4" /> Stark Control
            </CommandItem>
          </CommandGroup>
          <CommandGroup heading="System">
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/settings'))}>
              <Settings className="mr-2 h-4 w-4" /> Settings
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/search'))}>
              <Search className="mr-2 h-4 w-4" /> Research & Discovery
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/extensions'))}>
              <Puzzle className="mr-2 h-4 w-4" /> Extensions
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/admin'))}>
              <ShieldCheck className="mr-2 h-4 w-4" /> Admin Console
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/upgrade'))}>
              <ArrowUpCircle className="mr-2 h-4 w-4" /> Self-Upgrade
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/api-keys'))}>
              <Key className="mr-2 h-4 w-4" /> API Keys
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/security'))}>
              <Shield className="mr-2 h-4 w-4" /> Security Dashboard
            </CommandItem>
          </CommandGroup>
          <CommandGroup heading="Quick Actions">
            <CommandItem onSelect={() => runCommand(() => { newSession(); router.push('/dashboard'); })}>
              <MessageSquare className="mr-2 h-4 w-4" /> New Chat Session
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/monitoring'))}>
              <Activity className="mr-2 h-4 w-4" /> View System Health
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/dashboard/memory'))}>
              <Library className="mr-2 h-4 w-4" /> Search Memories
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => router.push('/workflows'))}>
              <Workflow className="mr-2 h-4 w-4" /> Create Workflow
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </CommandDialog>

      {/* Floating Activity Panel (toggled from header / ⌘+Shift+A) */}
      <AnimatePresence>
        {activityPanelOpen && (
          <motion.div
            className="fixed right-4 top-16 bottom-4 z-40 flex w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-slate-700/80 bg-[#0b1220] sm:w-80"
            initial={{ x: 320, opacity: 0, scale: 0.97 }}
            animate={{ x: 0, opacity: 1, scale: 1 }}
            exit={{ x: 320, opacity: 0, scale: 0.97 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          >
            <div className="flex items-center justify-between p-3 border-b border-white/5">
              <div>
                <h3 className="flex items-center gap-2 text-sm font-semibold">
                  <Activity className="h-4 w-4 text-indigo-300" />
                  Recent activity
                </h3>
                <p className="mt-1 text-[10px] text-slate-500">Recorded workspace actions; live server events are not configured.</p>
              </div>
              <button
                type="button"
                aria-label="Close recent activity"
                onClick={() => setWorkspace({ panelState: { activityPanel: { open: false } } })}
                className="p-1 rounded text-muted-foreground/50 hover:text-foreground transition-colors"
                title="Close activity panel"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1">
              <ActivityFabric maxItems={50} showFilters />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Floating Browser Panel (toggled via ⌘/Ctrl+B or command palette) */}
      <AnimatePresence>
        {browserPanelOpen && (
          <motion.div
            className="fixed right-4 top-16 bottom-4 z-40 flex w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-slate-700/80 bg-[#0b1220] sm:w-1/3 sm:min-w-[480px]"
            initial={{ x: 480, opacity: 0, scale: 0.97 }}
            animate={{ x: 0, opacity: 1, scale: 1 }}
            exit={{ x: 480, opacity: 0, scale: 0.97 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          >
            <div className="flex items-center justify-between p-3 border-b border-white/5">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <Globe className="h-4 w-4 text-blue-400" />
                JARVIS Browser
              </h3>
              <button
                type="button"
                aria-label="Close browser panel"
                onClick={() => setBrowserPanelOpen(false)}
                className="p-1 rounded text-muted-foreground/50 hover:text-foreground transition-colors"
                title="Close browser panel"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              <EmbeddedBrowser
                compact={true}
                onEvent={(evt) => {
                  if (evt.type === 'close') setBrowserPanelOpen(false);
                }}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
