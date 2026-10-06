'use client';

import { create } from 'zustand';
import { v4 as uuidv4 } from 'uuid';
import React from 'react';

// ==================== Types ====================

export interface WindowPosition {
  x: number;
  y: number;
}

export interface WindowSize {
  width: number;
  height: number;
}

export interface DesktopWindow {
  id: string;
  appId: string;
  title: string;
  icon: string;
  position: WindowPosition;
  size: WindowSize;
  defaultSize: WindowSize;
  minimized: boolean;
  maximized: boolean;
  zIndex: number;
  isFocused: boolean;
}

export interface DesktopIcon {
  appId: string;
  label: string;
  icon: string;
  position?: WindowPosition;
}

export interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
}

export interface DesktopState {
  // Windows
  windows: DesktopWindow[];
  nextZIndex: number;

  // Desktop
  icons: DesktopIcon[];
  wallpaper: string;

  // UI State
  contextMenu: ContextMenuState;
  startMenuOpen: boolean;
  showDesktop: boolean;

  // Workspaces
  activeWorkspace: number;
  workspaceCount: number;

  // Actions - Windows
  openWindow: (appId: string) => void;
  closeWindow: (windowId: string) => void;
  minimizeWindow: (windowId: string) => void;
  maximizeWindow: (windowId: string) => void;
  focusWindow: (windowId: string) => void;
  resizeWindow: (windowId: string, size: WindowSize) => void;
  moveWindow: (windowId: string, position: WindowPosition) => void;
  restoreWindow: (windowId: string) => void;

  // Actions - Desktop
  setWallpaper: (wallpaper: string) => void;
  setContextMenu: (menu: Partial<ContextMenuState>) => void;
  hideContextMenu: () => void;

  // Actions - UI
  toggleStartMenu: () => void;
  closeStartMenu: () => void;
  toggleShowDesktop: () => void;

  // Actions - Workspaces
  setActiveWorkspace: (workspace: number) => void;
  addWorkspace: () => void;
  removeWorkspace: () => void;
}

// ==================== App Registry ====================

export interface AppRegistryEntry {
  appId: string;
  title: string;
  icon: string;
  defaultSize: WindowSize;
  component: React.LazyExoticComponent<React.ComponentType<any>>;
}

// Lazy load app components
const ChatApp = React.lazy(() => import('./apps/ChatApp'));
const SystemMonitorApp = React.lazy(() => import('./apps/SystemMonitor'));
const FileManagerApp = React.lazy(() => import('./apps/FileManager'));
const TerminalApp = React.lazy(() => import('./apps/TerminalApp'));
const KnowledgeGraphApp = React.lazy(() => import('./apps/KnowledgeGraphApp'));
const BrowserApp = React.lazy(() => import('./apps/EnhancedBrowserApp'));
const SettingsApp = React.lazy(() => import('./apps/SettingsApp'));
const AgentsApp = React.lazy(() => import('./apps/AgentsApp'));
const CascadeAIApp = React.lazy(() => import('./apps/CascadeAIApp'));

export const APP_REGISTRY: Record<string, AppRegistryEntry> = {
  chat: {
    appId: 'chat',
    title: 'JARVIS Chat',
    icon: 'MessageSquare',
    defaultSize: { width: 900, height: 700 },
    component: ChatApp,
  },
  'system-monitor': {
    appId: 'system-monitor',
    title: 'System Monitor',
    icon: 'Activity',
    defaultSize: { width: 850, height: 650 },
    component: SystemMonitorApp,
  },
  'file-manager': {
    appId: 'file-manager',
    title: 'File Manager',
    icon: 'FolderOpen',
    defaultSize: { width: 950, height: 650 },
    component: FileManagerApp,
  },
  terminal: {
    appId: 'terminal',
    title: 'Terminal',
    icon: 'Terminal',
    defaultSize: { width: 800, height: 550 },
    component: TerminalApp,
  },
  'knowledge-graph': {
    appId: 'knowledge-graph',
    title: 'Knowledge Graph',
    icon: 'Network',
    defaultSize: { width: 1000, height: 700 },
    component: KnowledgeGraphApp,
  },
  browser: {
    appId: 'browser',
    title: 'Browser',
    icon: 'Globe',
    defaultSize: { width: 1100, height: 750 },
    component: BrowserApp,
  },
  settings: {
    appId: 'settings',
    title: 'Settings',
    icon: 'Settings',
    defaultSize: { width: 800, height: 650 },
    component: SettingsApp,
  },
  agents: {
    appId: 'agents',
    title: 'Agent Control',
    icon: 'Bot',
    defaultSize: { width: 1000, height: 700 },
    component: AgentsApp,
  },
  'cascade-ai': {
    appId: 'cascade-ai',
    title: 'Cascade AI',
    icon: 'Terminal',
    defaultSize: { width: 1200, height: 800 },
    component: CascadeAIApp,
  },
};

export const DESKTOP_ICONS: DesktopIcon[] = [
  { appId: 'chat', label: 'JARVIS Chat', icon: 'MessageSquare' },
  { appId: 'agents', label: 'Agents', icon: 'Bot' },
  { appId: 'cascade-ai', label: 'Cascade AI', icon: 'Terminal' },
  { appId: 'system-monitor', label: 'System Monitor', icon: 'Activity' },
  { appId: 'knowledge-graph', label: 'Knowledge Graph', icon: 'Network' },
  { appId: 'file-manager', label: 'File Manager', icon: 'FolderOpen' },
  { appId: 'terminal', label: 'Terminal', icon: 'Terminal' },
  { appId: 'browser', label: 'Browser', icon: 'Globe' },
  { appId: 'settings', label: 'Settings', icon: 'Settings' },
];

// ==================== Store ====================

// Generate a random position offset for new windows
const getRandomOffset = (): WindowPosition => ({
  x: 80 + Math.random() * 200,
  y: 40 + Math.random() * 100,
});

export const useDesktop = create<DesktopState>((set, get) => ({
  // Initial state
  windows: [],
  nextZIndex: 1,

  icons: DESKTOP_ICONS,
  wallpaper: 'default',

  contextMenu: { visible: false, x: 0, y: 0 },
  startMenuOpen: false,
  showDesktop: false,

  activeWorkspace: 0,
  workspaceCount: 1,

  // Window actions
  openWindow: (appId: string) => {
    const state = get();
    const registry = APP_REGISTRY[appId];
    if (!registry) return;

    // Check if window already exists for single-instance apps
    const existing = state.windows.find((w) => w.appId === appId);
    if (existing) {
      if (existing.minimized) {
        get().restoreWindow(existing.id);
      } else {
        get().focusWindow(existing.id);
      }
      return;
    }

    const newWindow: DesktopWindow = {
      id: uuidv4(),
      appId,
      title: registry.title,
      icon: registry.icon,
      position: getRandomOffset(),
      size: { ...registry.defaultSize },
      defaultSize: { ...registry.defaultSize },
      minimized: false,
      maximized: false,
      zIndex: state.nextZIndex,
      isFocused: true,
    };

    set((s) => ({
      windows: [...s.windows.map((w) => ({ ...w, isFocused: false })), newWindow],
      nextZIndex: s.nextZIndex + 1,
      showDesktop: false,
    }));
  },

  closeWindow: (windowId: string) => {
    set((s) => ({
      windows: s.windows.filter((w) => w.id !== windowId),
    }));
  },

  minimizeWindow: (windowId: string) => {
    set((s) => ({
      windows: s.windows.map((w) =>
        w.id === windowId ? { ...w, minimized: true, isFocused: false } : w,
      ),
    }));
  },

  maximizeWindow: (windowId: string) => {
    set((s) => ({
      windows: s.windows.map((w) =>
        w.id === windowId
          ? { ...w, maximized: !w.maximized, position: w.maximized ? w.position : { x: 0, y: 0 } }
          : w,
      ),
    }));
  },

  focusWindow: (windowId: string) => {
    const state = get();
    set({
      windows: state.windows.map((w) => ({
        ...w,
        isFocused: w.id === windowId,
        zIndex: w.id === windowId ? state.nextZIndex : w.zIndex,
        minimized: w.id === windowId ? false : w.minimized,
      })),
      nextZIndex: state.nextZIndex + 1,
      showDesktop: false,
    });
  },

  resizeWindow: (windowId: string, size: WindowSize) => {
    set((s) => ({
      windows: s.windows.map((w) => (w.id === windowId ? { ...w, size } : w)),
    }));
  },

  moveWindow: (windowId: string, position: WindowPosition) => {
    set((s) => ({
      windows: s.windows.map((w) => (w.id === windowId ? { ...w, position } : w)),
    }));
  },

  restoreWindow: (windowId: string) => {
    const state = get();
    set({
      windows: state.windows.map((w) =>
        w.id === windowId ? { ...w, minimized: false, isFocused: true, zIndex: state.nextZIndex } : { ...w, isFocused: false },
      ),
      nextZIndex: state.nextZIndex + 1,
      showDesktop: false,
    });
  },

  // Desktop actions
  setWallpaper: (wallpaper: string) => {
    set({ wallpaper });
  },

  setContextMenu: (menu: Partial<ContextMenuState>) => {
    set((s) => ({
      contextMenu: { ...s.contextMenu, ...menu },
    }));
  },

  hideContextMenu: () => {
    set((s) => ({
      contextMenu: { ...s.contextMenu, visible: false },
    }));
  },

  // UI actions
  toggleStartMenu: () => {
    set((s) => ({ startMenuOpen: !s.startMenuOpen }));
  },

  closeStartMenu: () => {
    set({ startMenuOpen: false });
  },

  toggleShowDesktop: () => {
    const state = get();
    if (state.showDesktop) {
      // Restore all minimized windows
      set({
        windows: state.windows.map((w) => ({ ...w, minimized: false })),
        showDesktop: false,
      });
    } else {
      // Minimize all windows
      set({
        windows: state.windows.map((w) => ({ ...w, minimized: true, isFocused: false })),
        showDesktop: true,
      });
    }
  },

  // Workspace actions
  setActiveWorkspace: (workspace: number) => {
    set({ activeWorkspace: workspace });
  },

  addWorkspace: () => {
    set((s) => ({ workspaceCount: s.workspaceCount + 1 }));
  },

  removeWorkspace: () => {
    const state = get();
    if (state.workspaceCount <= 1) return;
    set({
      workspaceCount: state.workspaceCount - 1,
      activeWorkspace: Math.max(0, state.activeWorkspace - 1),
    });
  },
}));
