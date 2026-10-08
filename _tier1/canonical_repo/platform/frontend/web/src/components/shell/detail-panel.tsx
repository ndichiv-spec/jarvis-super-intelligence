'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, PanelLeft, PanelLeftClose, Pin, PinOff } from 'lucide-react';
import { usePlatformStore } from '@/stores/platform-store';
import { glassCard, glassBorder } from '@/lib/design-system';

export type PanelMode = 'floating' | 'docked' | 'embedded';
export type PanelAnchor = 'left' | 'right' | 'bottom' | 'top';

export interface DetailPanelConfig<T> {
  id: string;
  title: string;
  icon?: React.ElementType;
  render: (data: T) => React.ReactNode;
  /** Persist this panel's open/collapsed state in workspace */
  persistKey?: string;
}

interface DetailPanelProps<T> {
  data: T | null;
  config: DetailPanelConfig<T>;
  defaultOpen?: boolean;
  defaultMode?: PanelMode;
  defaultWidth?: number;
  defaultHeight?: number;
  anchor?: PanelAnchor;
  onClose?: () => void;
}

/**
 * A reusable context panel that supports:
 * - floating (overlay that can be dragged conceptually)
 * - docked (side or bottom dock, persists in workspace state)
 * - embedded (inline within parent layout)
 * - collapse / expand
 * - pin (keep open while navigating)
 * - close
 *
 * State (open, mode, width, height, collapsed, pinned) is persisted
 * to the workspace store so users return to their preferred arrangement.
 */
export function DetailPanel<T>({
  data,
  config,
  defaultOpen = false,
  defaultMode = 'floating',
  defaultWidth = 360,
  defaultHeight = 300,
  anchor = 'right',
  onClose,
}: DetailPanelProps<T>) {
  const [open, setOpen] = useState(defaultOpen);
  const [mode, setMode] = useState<PanelMode>(defaultMode);
  const [width, setWidth] = useState(defaultWidth);
  const [collapsed, setCollapsed] = useState(false);
  const [pinned, setPinned] = useState(false);

  const workspace = usePlatformStore((s) => s.workspace);
  const setWorkspace = usePlatformStore((s) => s.setWorkspace);

  const persistKey = config.persistKey || config.id;

  // Load persisted state
  useEffect(() => {
    const saved = workspace.panelState[persistKey];
    if (saved) {
      if (saved.collapsed !== undefined) setCollapsed(saved.collapsed);
      if (saved.width !== undefined) setWidth(saved.width);
    }
  }, [workspace.panelState, persistKey]);

  const handleClose = () => {
    setOpen(false);
    setWorkspace({ panelState: { ...workspace.panelState, [persistKey]: { ...workspace.panelState[persistKey], collapsed: false } } });
    onClose?.();
  };

  const handleToggleCollapse = () => {
    setCollapsed((c) => {
      const next = !c;
      setWorkspace({ panelState: { ...workspace.panelState, [persistKey]: { ...workspace.panelState[persistKey], collapsed: next } } });
      return next;
    });
  };

  const handleTogglePin = () => {
    setPinned((p) => !p);
  };

  if (!open || !data) {
    // Show a floating toggle button when closed
    if (!defaultOpen) {
      return (
        <button
          onClick={() => setOpen(true)}
          className={`fixed z-30 flex h-10 w-10 items-center justify-center rounded-full border ${glassCard} ${glassBorder} text-muted-foreground/60 hover:text-foreground hover:bg-white/[0.05] transition-all`}
          style={anchor === 'right' ? { right: 16, top: 80 } : { left: 16, top: 80 }}
        >
          {config.icon && <config.icon className="h-5 w-5" />}
        </button>
      );
    }
    return null;
  }

  const panelContent = (
    <div className={`flex flex-col overflow-hidden rounded-2xl border ${glassCard} ${glassBorder}`}>
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-white/5">
        <div className="flex items-center gap-2">
          {config.icon && <config.icon className="h-4 w-4 text-muted-foreground/60" />}
          <span className="text-sm font-medium">{config.title}</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={handleTogglePin}
            className={`p-1 rounded text-muted-foreground/40 hover:text-foreground transition-colors`}
            title={pinned ? 'Unpin' : 'Pin'}
          >
            {pinned ? <PinOff className="h-3 w-3" /> : <Pin className="h-3 w-3" />}
          </button>
          <button
            onClick={handleToggleCollapse}
            className="p-1 rounded text-muted-foreground/40 hover:text-foreground transition-colors"
            title={collapsed ? 'Expand' : 'Collapse'}
          >
            {collapsed ? <PanelLeftClose className="h-3 w-3" /> : <PanelLeft className="h-3 w-3" />}
          </button>
          <button
            onClick={handleClose}
            className="p-1 rounded text-muted-foreground/40 hover:text-foreground transition-colors"
            title="Close"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      </div>

      {/* Body */}
      <AnimatePresence>
        {!collapsed && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="flex-1 overflow-auto"
          >
            <div className="p-4">{config.render(data)}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );

  // Position based on mode and anchor
  if (mode === 'floating') {
    return (
      <motion.div
        className="fixed z-50"
        style={anchor === 'right' ? { right: 16, top: 80, maxHeight: 'calc(100vh - 100px)' } : { left: 16, top: 80, maxHeight: 'calc(100vh - 100px)' }}
        initial={{ x: anchor === 'right' ? 100 : -100, opacity: 0, scale: 0.95 }}
        animate={{ x: 0, opacity: 1, scale: 1 }}
        exit={{ x: anchor === 'right' ? 100 : -100, opacity: 0, scale: 0.95 }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
      >
        {panelContent}
      </motion.div>
    );
  }

  if (mode === 'docked') {
    return (
      <motion.div
        className="z-30 flex flex-col"
        style={{ width: collapsed ? 48 : width, maxHeight: 'calc(100vh - 100px)' }}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 20 }}
      >
        {panelContent}
      </motion.div>
    );
  }

  // Embedded mode — just render the panel content inline
  return panelContent;
}

export default DetailPanel;
