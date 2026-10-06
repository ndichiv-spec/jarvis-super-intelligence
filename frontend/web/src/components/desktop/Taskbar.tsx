'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useDesktop, APP_REGISTRY } from './DesktopProvider';
import { motion, AnimatePresence } from 'framer-motion';
import {
  MessageSquare,
  Bot,
  Activity,
  Network,
  FolderOpen,
  Terminal,
  Globe,
  Settings,
  Volume2,
  Wifi,
  Battery,
  LayoutGrid,
  Power,
  Cpu,
  Zap,
  Shield,
} from 'lucide-react';

const ICON_MAP: Record<string, React.ElementType> = {
  MessageSquare,
  Bot,
  Activity,
  Network,
  FolderOpen,
  Terminal,
  Globe,
  Settings,
};

interface TaskbarProps {
  onToggleStartMenu: () => void;
  isStartMenuOpen: boolean;
}

export function Taskbar({ onToggleStartMenu, isStartMenuOpen }: TaskbarProps) {
  const { windows, focusWindow, minimizeWindow, toggleShowDesktop, showDesktop } = useDesktop();
  const [currentTime, setCurrentTime] = useState(new Date());
  const [showSystemTray, setShowSystemTray] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const handleClick = () => setShowSystemTray(false);
    if (showSystemTray) {
      document.addEventListener('click', handleClick);
      return () => document.removeEventListener('click', handleClick);
    }
  }, [showSystemTray]);

  const handleTaskbarClick = useCallback(
    (windowId: string) => {
      const win = windows.find((w) => w.id === windowId);
      if (!win) return;

      if (win.isFocused && !win.minimized) {
        minimizeWindow(windowId);
      } else {
        focusWindow(windowId);
      }
    },
    [windows, focusWindow, minimizeWindow]
  );

  const timeStr = currentTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const dateStr = currentTime.toLocaleDateString([], { month: 'short', day: 'numeric' });

  return (
    <>
      <div className="fixed bottom-0 left-0 right-0 h-14 z-[9998]">
        {/* Holographic background */}
        <div className="absolute inset-0 holo-taskbar" />

        {/* Top edge glow */}
        <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-cyan-500/30 to-transparent" />

        <div className="relative h-full flex items-center px-2 gap-1">
          {/* ===== START BUTTON ===== */}
          <button
            onClick={onToggleStartMenu}
            className={`relative flex items-center gap-2 h-9 px-4 rounded-lg transition-all duration-200 ${
              isStartMenuOpen
                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 shadow-[0_0_15px_rgba(0,212,255,0.2)]'
                : 'hover:bg-cyan-500/10 text-cyan-300/60 hover:text-cyan-300'
            }`}
          >
            <motion.div
              animate={isStartMenuOpen ? { rotate: 90, scale: 1.1 } : { rotate: 0, scale: 1 }}
              transition={{ duration: 0.3 }}
            >
              <div className="relative">
                <Zap className="w-4 h-4" />
                {isStartMenuOpen && (
                  <div className="absolute -inset-1 bg-cyan-400/20 rounded-full blur-sm" />
                )}
              </div>
            </motion.div>
            <span className="text-xs font-semibold tracking-wider hidden sm:inline text-holo">J.A.R.V.I.S.</span>
          </button>

          {/* Separator */}
          <div className="w-px h-5 bg-cyan-500/20 mx-0.5" />

          {/* ===== QUICK LAUNCH ===== */}
          <div className="flex items-center gap-0.5">
            {['chat', 'terminal', 'browser', 'system-monitor'].map((appId) => {
              const app = APP_REGISTRY[appId];
              if (!app) return null;
              const IconComponent = ICON_MAP[app.icon] || FolderOpen;
              const isOpen = windows.some((w) => w.appId === appId && !w.minimized);

              return (
                <button
                  key={appId}
                  onClick={() => {
                    const existing = windows.find((w) => w.appId === appId);
                    if (existing) {
                      handleTaskbarClick(existing.id);
                    } else {
                      useDesktop.getState().openWindow(appId);
                    }
                  }}
                  className="relative h-9 w-9 flex items-center justify-center rounded-lg hover:bg-cyan-500/10 text-cyan-300/50 hover:text-cyan-300 transition-all"
                  title={app.title}
                >
                  <IconComponent className="w-4 h-4" />
                  {isOpen && (
                    <div className="absolute -bottom-0.5 left-1/2 -translate-x-1/2 w-3 h-[2px] bg-cyan-400 rounded-full shadow-[0_0_6px_rgba(0,212,255,0.5)]" />
                  )}
                </button>
              );
            })}
          </div>

          {/* Separator */}
          <div className="w-px h-5 bg-cyan-500/20 mx-0.5" />

          {/* ===== OPEN WINDOWS ===== */}
          <div className="flex items-center gap-0.5 flex-1 overflow-x-auto">
            {windows.map((win) => {
              const IconComponent = ICON_MAP[win.icon] || FolderOpen;
              return (
                <TaskbarItem
                  key={win.id}
                  icon={win.icon}
                  title={win.title}
                  isActive={win.isFocused && !win.minimized}
                  isMinimized={win.minimized}
                  onClick={() => handleTaskbarClick(win.id)}
                />
              );
            })}
          </div>

          {/* ===== SHOW DESKTOP ===== */}
          <button
            onClick={toggleShowDesktop}
            className="h-9 w-9 flex items-center justify-center rounded-lg hover:bg-cyan-500/10 text-cyan-300/30 hover:text-cyan-300/60 transition-colors shrink-0"
            title="Show Desktop"
          >
            <LayoutGrid className="w-3.5 h-3.5" />
          </button>

          {/* ===== SYSTEM TRAY ===== */}
          <div className="relative flex items-center gap-0.5 shrink-0">
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowSystemTray(!showSystemTray);
              }}
              className="h-9 px-2 flex items-center gap-2 rounded-lg hover:bg-cyan-500/10 text-cyan-300/50 transition-colors"
            >
              <Volume2 className="w-3.5 h-3.5" />
              <Wifi className="w-3.5 h-3.5" />
              <Battery className="w-3.5 h-3.5" />
            </button>

            {/* ===== HUD CLOCK ===== */}
            <div className="h-9 px-3 flex flex-col items-center justify-center rounded-lg hover:bg-cyan-500/5 text-cyan-300/60 cursor-default transition-colors">
              <span className="hud-readout text-[11px] text-cyan-400/70 leading-tight">{timeStr}</span>
              <span className="hud-readout text-[8px] text-cyan-400/40 leading-tight">{dateStr}</span>
            </div>

            {/* ===== SYSTEM TRAY POPUP ===== */}
            <AnimatePresence>
              {showSystemTray && (
                <motion.div
                  initial={{ opacity: 0, y: 10, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 10, scale: 0.95 }}
                  transition={{ duration: 0.15 }}
                  className="absolute bottom-full right-0 mb-2 w-72"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="holo-context-menu rounded-xl overflow-hidden p-4">
                    <h3 className="text-sm font-semibold text-cyan-300/90 tracking-wider mb-3">
                      <Cpu className="w-4 h-4 inline mr-1.5" />
                      SYSTEM STATUS
                    </h3>

                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-sm text-cyan-300/60">
                          <Volume2 className="w-4 h-4" />
                          <span>Volume</span>
                        </div>
                        <div className="w-24 h-1.5 holo-progress rounded-full overflow-hidden">
                          <div className="h-full w-3/4 holo-progress-bar rounded-full" />
                        </div>
                      </div>

                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-sm text-cyan-300/60">
                          <Wifi className="w-4 h-4" />
                          <span>Network</span>
                        </div>
                        <span className="text-[10px] text-emerald-400 font-medium tracking-wider hud-readout">CONNECTED</span>
                      </div>

                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-sm text-cyan-300/60">
                          <Battery className="w-4 h-4" />
                          <span>Power</span>
                        </div>
                        <span className="text-[10px] text-cyan-400/70 tracking-wider hud-readout">85%</span>
                      </div>

                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-sm text-cyan-300/60">
                          <Shield className="w-4 h-4" />
                          <span>Security</span>
                        </div>
                        <span className="text-[10px] text-emerald-400 font-medium tracking-wider hud-readout">ACTIVE</span>
                      </div>
                    </div>

                    <div className="mt-4 pt-3 border-t border-cyan-500/20 flex items-center justify-between">
                      <span className="text-[10px] text-cyan-300/40 tracking-wider hud-readout">J.A.R.V.I.S. OS v4.0</span>
                      <button className="flex items-center gap-1.5 text-[10px] text-red-400/70 hover:text-red-400 transition-colors tracking-wider">
                        <Power className="w-3 h-3" />
                        <span>STANDBY</span>
                      </button>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>

      {/* Spacer */}
      <div className="h-14" />
    </>
  );
}

// ==================== TASKBAR ITEM ====================

interface TaskbarItemProps {
  icon: string;
  title: string;
  isActive: boolean;
  isMinimized: boolean;
  onClick: () => void;
}

function TaskbarItem({ icon, title, isActive, isMinimized, onClick }: TaskbarItemProps) {
  const IconComponent = ICON_MAP[icon] || FolderOpen;

  return (
    <button
      onClick={onClick}
      className={`relative h-9 px-2.5 flex items-center gap-2 rounded-lg transition-all duration-150 min-w-0 max-w-[180px] ${
        isActive && !isMinimized
          ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/25 shadow-[0_0_10px_rgba(0,212,255,0.15)]'
          : isMinimized
            ? 'bg-cyan-500/[0.03] text-cyan-300/30 hover:bg-cyan-500/5 hover:text-cyan-300/50'
            : 'hover:bg-cyan-500/5 text-cyan-300/50 hover:text-cyan-300/70'
      }`}
    >
      <IconComponent className="w-3.5 h-3.5 shrink-0" />
      <span className="text-[11px] truncate tracking-wide">{title}</span>
      {!isMinimized && (
        <div
          className={`absolute -bottom-0.5 left-1/2 -translate-x-1/2 rounded-full transition-all ${
            isActive ? 'w-4 h-[2px] bg-cyan-400 shadow-[0_0_6px_rgba(0,212,255,0.5)]' : 'w-2 h-[1.5px] bg-cyan-300/30'
          }`}
        />
      )}
    </button>
  );
}
