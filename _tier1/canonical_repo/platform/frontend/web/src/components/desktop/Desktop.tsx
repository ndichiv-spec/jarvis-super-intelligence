'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useDesktop, APP_REGISTRY } from './DesktopProvider';
import { Window } from './Window';
import { Taskbar } from './Taskbar';
import { StartMenu } from './StartMenu';
import { AnimatePresence, motion } from 'framer-motion';
import {
  MessageSquare,
  Bot,
  Activity,
  Network,
  FolderOpen,
  Terminal,
  Globe,
  Settings,
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

const WALLPAPERS: Record<string, string> = {
  default: 'bg-[#030712]',
  ocean: 'bg-gradient-to-br from-[#020810] via-[#0a1628] to-[#031020]',
  aurora: 'bg-gradient-to-br from-[#0a0520] via-[#0f0a1a] to-[#051a10]',
  nebula: 'bg-gradient-to-br from-[#08061a] via-[#120a28] to-[#1a0510]',
  midnight: 'bg-gradient-to-br from-[#050508] via-[#080810] to-[#0a0d12]',
};

export function Desktop() {
  const {
    windows,
    icons,
    wallpaper,
    contextMenu,
    startMenuOpen,
    openWindow,
    setContextMenu,
    hideContextMenu,
    closeStartMenu,
    toggleStartMenu,
    setWallpaper,
  } = useDesktop();

  const desktopRef = useRef<HTMLDivElement>(null);
  const [showWallpaperPicker, setShowWallpaperPicker] = useState(false);
  const [systemTime, setSystemTime] = useState<Date | null>(null);
  const [arcReactorPulse, setArcReactorPulse] = useState(0);

  // Clock — seeded on mount to avoid SSR/client time mismatch
  useEffect(() => {
    setSystemTime(new Date());
    const timer = setInterval(() => setSystemTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Arc reactor pulse animation
  useEffect(() => {
    const interval = setInterval(() => {
      setArcReactorPulse((p) => (p + 1) % 360);
    }, 50);
    return () => clearInterval(interval);
  }, []);

  const handleDesktopContextMenu = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      if ((e.target as HTMLElement).closest('.desktop-icon') || (e.target as HTMLElement).closest('.desktop-window')) {
        return;
      }
      setContextMenu({ visible: true, x: e.clientX, y: e.clientY });
    },
    [setContextMenu]
  );

  const handleDesktopClick = useCallback(
    (e: React.MouseEvent) => {
      if (!(e.target as HTMLElement).closest('.context-menu') && !(e.target as HTMLElement).closest('.start-menu')) {
        hideContextMenu();
        closeStartMenu();
      }
    },
    [hideContextMenu, closeStartMenu]
  );

  const handleIconDoubleClick = useCallback(
    (appId: string) => {
      openWindow(appId);
    },
    [openWindow]
  );

  const handleWallpaperSelect = useCallback(
    (wp: string) => {
      setWallpaper(wp);
      setShowWallpaperPicker(false);
      hideContextMenu();
    },
    [setWallpaper, hideContextMenu]
  );

  useEffect(() => {
    const handleClick = () => setShowWallpaperPicker(false);
    if (showWallpaperPicker) {
      document.addEventListener('click', handleClick);
      return () => document.removeEventListener('click', handleClick);
    }
  }, [showWallpaperPicker]);

  const currentWallpaper = WALLPAPERS[wallpaper] || WALLPAPERS.default;

  return (
    <div
      ref={desktopRef}
      className={`relative w-full h-screen overflow-hidden ${currentWallpaper} select-none`}
      onContextMenu={handleDesktopContextMenu}
      onClick={handleDesktopClick}
    >
      {/* ===== HOLOGRAPHIC GRID ===== */}
      <div className="absolute inset-0 holo-grid opacity-40 pointer-events-none" />

      {/* ===== SCAN LINES ===== */}
      <div className="absolute inset-0 pointer-events-none scanlines opacity-30" />

      {/* ===== CYBER AMBIENT GLOW ===== */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        {/* Arc Reactor - Center */}
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full"
          style={{
            background: `radial-gradient(circle, rgba(0,212,255,${0.06 + Math.sin(arcReactorPulse * 0.05) * 0.03}), transparent 70%)`,
            filter: 'blur(60px)',
          }}
        />
        {/* Corner accents */}
        <div className="absolute top-1/4 left-1/4 w-64 h-64 bg-cyan-500/5 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-1/4 right-1/4 w-56 h-56 bg-teal-500/5 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
        <div className="absolute top-1/3 right-1/3 w-48 h-48 bg-blue-500/3 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '2s' }} />
      </div>

      {/* ===== HUD CORNER BRACKETS (decorative) ===== */}
      <div className="absolute top-3 left-3 w-8 h-8 pointer-events-none opacity-40">
        <div className="absolute top-0 left-0 w-full h-[2px] bg-cyan-400" />
        <div className="absolute top-0 left-0 w-[2px] h-full bg-cyan-400" />
      </div>
      <div className="absolute top-3 right-3 w-8 h-8 pointer-events-none opacity-40">
        <div className="absolute top-0 right-0 w-full h-[2px] bg-cyan-400" />
        <div className="absolute top-0 right-0 w-[2px] h-full bg-cyan-400" />
      </div>
      <div className="absolute bottom-16 left-3 w-8 h-8 pointer-events-none opacity-40">
        <div className="absolute bottom-0 left-0 w-full h-[2px] bg-cyan-400" />
        <div className="absolute bottom-0 left-0 w-[2px] h-full bg-cyan-400" />
      </div>
      <div className="absolute bottom-16 right-3 w-8 h-8 pointer-events-none opacity-40">
        <div className="absolute bottom-0 right-0 w-full h-[2px] bg-cyan-400" />
        <div className="absolute bottom-0 right-0 w-[2px] h-full bg-cyan-400" />
      </div>

      {/* ===== HUD SYSTEM INFO (top-right) ===== */}
      <div className="absolute top-4 right-16 z-20 pointer-events-none">
        <div className="text-right space-y-0.5">
          <div className="hud-readout text-[10px] text-cyan-400/60 tracking-widest">
            J.A.R.V.I.S. OS v4.0
          </div>
          <div className="hud-readout text-[9px] text-cyan-400/40 tracking-wider">
            {systemTime ? systemTime.toLocaleTimeString() : '\u00A0'}
          </div>
          <div className="flex items-center gap-1.5 justify-end">
            <Shield className="w-3 h-3 text-emerald-400/50" />
            <span className="hud-readout text-[8px] text-emerald-400/50 tracking-wider">SECURE</span>
          </div>
          <div className="flex items-center gap-1.5 justify-end">
            <Zap className="w-3 h-3 text-cyan-400/50" />
            <span className="hud-readout text-[8px] text-cyan-400/50 tracking-wider">ONLINE</span>
          </div>
        </div>
      </div>

      {/* ===== DESKTOP ICONS ===== */}
      <div className="absolute top-4 left-4 grid grid-cols-1 gap-2 z-10">
        {icons.map((icon) => {
          const IconComponent = ICON_MAP[icon.icon] || FolderOpen;
          return (
            <DesktopIcon
              key={icon.appId}
              icon={icon.icon}
              label={icon.label}
              onDoubleClick={() => handleIconDoubleClick(icon.appId)}
            />
          );
        })}
      </div>

      {/* ===== WINDOWS LAYER ===== */}
      <div className="absolute inset-0 pointer-events-none">
        <AnimatePresence>
          {windows.map(
            (win) =>
              !win.minimized && (
                <Window key={win.id} window={win} />
              )
          )}
        </AnimatePresence>
      </div>

      {/* ===== CONTEXT MENU ===== */}
      <AnimatePresence>
        {contextMenu.visible && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.1 }}
            className="context-menu fixed z-[9999] min-w-[200px]"
            style={{ left: contextMenu.x, top: contextMenu.y }}
          >
            <div className="holo-context-menu rounded-xl overflow-hidden py-2">
              <ContextMenuItem
                icon={Cpu}
                label="System Diagnostics"
                onClick={() => {
                  hideContextMenu();
                  openWindow('system-monitor');
                }}
              />
              <ContextMenuItem
                icon={Network}
                label="Knowledge Graph"
                onClick={() => {
                  hideContextMenu();
                  openWindow('knowledge-graph');
                }}
              />
              <div className="my-1 border-t border-cyan-500/20" />
              <div
                className="relative px-3 py-2 hover:bg-cyan-500/10 cursor-pointer flex items-center gap-3 text-sm text-cyan-300/80"
                onClick={(e) => {
                  e.stopPropagation();
                  setShowWallpaperPicker(!showWallpaperPicker);
                }}
              >
                <Globe className="w-4 h-4" />
                <span>Holographic Theme</span>
              </div>

              {showWallpaperPicker && (
                <motion.div
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="absolute left-full top-0 ml-1 holo-context-menu rounded-xl overflow-hidden py-2 min-w-[160px]"
                  onClick={(e) => e.stopPropagation()}
                >
                  {Object.keys(WALLPAPERS).map((wp) => (
                    <div
                      key={wp}
                      className="px-3 py-2 hover:bg-cyan-500/10 cursor-pointer flex items-center gap-2 text-sm text-cyan-300/80 capitalize"
                      onClick={() => handleWallpaperSelect(wp)}
                    >
                      <Activity className="w-3.5 h-3.5" />
                      {wp}
                    </div>
                  ))}
                </motion.div>
              )}

              <div className="my-1 border-t border-cyan-500/20" />
              <ContextMenuItem
                icon={Settings}
                label="System Settings"
                onClick={() => {
                  hideContextMenu();
                  openWindow('settings');
                }}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ===== START MENU ===== */}
      <AnimatePresence>
        {startMenuOpen && <StartMenu />}
      </AnimatePresence>

      {/* ===== TASKBAR ===== */}
      <Taskbar onToggleStartMenu={toggleStartMenu} isStartMenuOpen={startMenuOpen} />
    </div>
  );
}

// ==================== DESKTOP ICON ====================

interface DesktopIconProps {
  icon: string;
  label: string;
  onDoubleClick: () => void;
}

function DesktopIcon({ icon, label, onDoubleClick }: DesktopIconProps) {
  const IconComponent = ICON_MAP[icon] || FolderOpen;

  return (
    <motion.button
      className="desktop-icon group flex flex-col items-center gap-1.5 p-3 rounded-lg hover:bg-cyan-500/5 w-24 transition-all duration-150"
      onDoubleClick={onDoubleClick}
      whileHover={{ scale: 1.08 }}
      whileTap={{ scale: 0.95 }}
    >
      <div className="relative">
        <div className="w-12 h-12 rounded-lg holo-icon flex items-center justify-center group-hover:scale-110 transition-all duration-150">
          <IconComponent className="w-6 h-6 text-cyan-400 drop-shadow-[0_0_8px_rgba(0,212,255,0.5)]" />
        </div>
        {/* Glow dot */}
        <div className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 bg-cyan-400 rounded-full border border-[#030712] opacity-0 group-hover:opacity-100 transition-all shadow-[0_0_8px_rgba(0,212,255,0.6)]" />
      </div>
      <span className="text-[11px] text-cyan-300/60 text-center leading-tight group-hover:text-cyan-300/90 line-clamp-2 drop-shadow-[0_0_4px_rgba(0,212,255,0.3)]">
        {label}
      </span>
    </motion.button>
  );
}

// ==================== CONTEXT MENU ITEM ====================

interface ContextMenuItemProps {
  icon: React.ElementType;
  label: string;
  onClick: () => void;
}

function ContextMenuItem({ icon: Icon, label, onClick }: ContextMenuItemProps) {
  return (
    <div
      className="px-3 py-2 hover:bg-cyan-500/10 cursor-pointer flex items-center gap-3 text-sm text-cyan-300/80"
      onClick={onClick}
    >
      <Icon className="w-4 h-4 text-cyan-400" />
      <span>{label}</span>
    </div>
  );
}
