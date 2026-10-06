'use client';

import React, { useCallback, useState } from 'react';
import { useDesktop, APP_REGISTRY } from './DesktopProvider';
import { motion } from 'framer-motion';
import {
  MessageSquare,
  Bot,
  Activity,
  Network,
  FolderOpen,
  Terminal,
  Globe,
  Settings,
  Search,
  LogOut,
  Settings as SettingsIcon,
  User,
  Power,
  Zap,
  Cpu,
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

const PINNED_APPS = ['chat', 'agents', 'system-monitor', 'knowledge-graph', 'file-manager', 'terminal', 'browser', 'settings'];

export function StartMenu() {
  const { openWindow, closeStartMenu } = useDesktop();
  const [searchQuery, setSearchQuery] = useState('');

  const handleAppClick = useCallback(
    (appId: string) => {
      openWindow(appId);
      closeStartMenu();
    },
    [openWindow, closeStartMenu]
  );

  const filteredApps = PINNED_APPS.filter((appId) => {
    const app = APP_REGISTRY[appId];
    if (!app) return false;
    if (!searchQuery) return true;
    return app.title.toLowerCase().includes(searchQuery.toLowerCase());
  });

  return (
    <motion.div
      className="start-menu fixed bottom-16 left-2 z-[9997]"
      initial={{ opacity: 0, y: 20, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 20, scale: 0.96 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
    >
      <div className="holo-start-menu rounded-xl overflow-hidden w-[580px] max-h-[calc(100vh-8rem)]">
        {/* ===== USER PROFILE ===== */}
        <div className="flex items-center gap-3 p-4 border-b border-cyan-500/20">
          {/* Avatar with arc-reactor glow */}
          <div className="relative">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-cyan-500/30 to-teal-500/20 border border-cyan-500/30 flex items-center justify-center shadow-[0_0_15px_rgba(0,212,255,0.2)]">
              <User className="w-5 h-5 text-cyan-400" />
            </div>
            <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-emerald-400 rounded-full border-2 border-[#030712] shadow-[0_0_6px_rgba(52,211,153,0.5)]" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-cyan-300/90 tracking-wider truncate">STARK INDUSTRIES</h3>
            <div className="flex items-center gap-2">
              <Shield className="w-3 h-3 text-emerald-400/60" />
              <p className="text-[11px] text-cyan-300/40 tracking-wide">Administrator • Secure Session</p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-cyan-500/10 text-cyan-300/40 hover:text-cyan-300 transition-colors"
              title="Settings"
            >
              <SettingsIcon className="w-4 h-4" />
            </button>
            <button
              className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-red-500/10 text-cyan-300/40 hover:text-red-400 transition-colors"
              title="Sign out"
            >
              <Power className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* ===== SEARCH BAR ===== */}
        <div className="p-3 border-b border-cyan-500/20">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-cyan-400/30" />
            <input
              type="text"
              placeholder="Search systems..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full h-9 pl-9 pr-3 bg-cyan-500/5 border border-cyan-500/20 rounded-lg text-sm text-cyan-300/80 placeholder:text-cyan-300/25 focus:outline-none focus:border-cyan-500/40 focus:shadow-[0_0_10px_rgba(0,212,255,0.15)] transition-all tracking-wider"
            />
          </div>
        </div>

        {/* ===== PINNED APPS ===== */}
        <div className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <Cpu className="w-3.5 h-3.5 text-cyan-400/50" />
            <h4 className="text-[10px] font-semibold text-cyan-300/50 uppercase tracking-[0.15em]">
              Active Modules
            </h4>
          </div>
          <div className="grid grid-cols-4 gap-1.5">
            {filteredApps.map((appId) => {
              const app = APP_REGISTRY[appId];
              if (!app) return null;
              const IconComponent = ICON_MAP[app.icon] || FolderOpen;

              return (
                <motion.button
                  key={appId}
                  className="flex flex-col items-center gap-1.5 p-3 rounded-lg hover:bg-cyan-500/5 transition-all group"
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => handleAppClick(appId)}
                >
                  <div className="w-10 h-10 rounded-lg holo-icon flex items-center justify-center group-hover:shadow-[0_0_20px_rgba(0,212,255,0.3)] transition-all">
                    <IconComponent className="w-5 h-5 text-cyan-400 drop-shadow-[0_0_6px_rgba(0,212,255,0.4)]" />
                  </div>
                  <span className="text-[10px] text-cyan-300/50 text-center leading-tight group-hover:text-cyan-300/80 tracking-wide line-clamp-1">
                    {app.title}
                  </span>
                </motion.button>
              );
            })}
          </div>

          {filteredApps.length === 0 && (
            <div className="flex flex-col items-center justify-center py-8 text-cyan-300/30">
              <Search className="w-8 h-8 mb-2" />
              <span className="text-sm tracking-wider">No modules found</span>
            </div>
          )}
        </div>

        {/* ===== FOOTER ===== */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-cyan-500/20 bg-cyan-500/[0.02]">
          <div className="flex items-center gap-2">
            <Zap className="w-3.5 h-3.5 text-cyan-400/50" />
            <span className="text-[10px] text-cyan-300/40 tracking-wider hud-readout">J.A.R.V.I.S. v4.0 • StarkOS</span>
          </div>
          <button
            className="flex items-center gap-1.5 text-[10px] text-cyan-300/40 hover:text-red-400 transition-colors tracking-wider"
            onClick={() => closeStartMenu()}
          >
            <LogOut className="w-3 h-3" />
            <span>LOCK</span>
          </button>
        </div>
      </div>
    </motion.div>
  );
}
