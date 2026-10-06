'use client';

import React, { useCallback, useEffect, useRef, useState, memo } from 'react';
import { motion } from 'framer-motion';
import { useDesktop, DesktopWindow, APP_REGISTRY } from './DesktopProvider';
import {
  X,
  Minus,
  Maximize2,
  Minimize2,
  MessageSquare,
  Bot,
  Activity,
  Network,
  FolderOpen,
  Terminal,
  Globe,
  Settings,
  Cpu,
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

const MIN_WINDOW_WIDTH = 400;
const MIN_WINDOW_HEIGHT = 300;
const TASKBAR_HEIGHT = 56;

interface WindowProps {
  window: DesktopWindow;
}

export const Window = memo(function Window({ window: win }: WindowProps) {
  const { focusWindow, minimizeWindow, maximizeWindow, closeWindow, moveWindow, resizeWindow } =
    useDesktop();

  const windowRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isResizing, setIsResizing] = useState<string | null>(null);
  const dragStart = useRef({ x: 0, y: 0, winX: 0, winY: 0 });
  const resizeStart = useRef({ x: 0, y: 0, width: 0, height: 0 });

  const handleFocus = useCallback(() => {
    if (!win.isFocused) {
      focusWindow(win.id);
    }
  }, [win.id, win.isFocused, focusWindow]);

  const handleMinimize = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      minimizeWindow(win.id);
    },
    [win.id, minimizeWindow]
  );

  const handleMaximize = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      maximizeWindow(win.id);
    },
    [win.id, maximizeWindow]
  );

  const handleClose = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      closeWindow(win.id);
    },
    [win.id, closeWindow]
  );

  // Dragging
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (win.maximized) return;
      if ((e.target as HTMLElement).closest('.window-button')) return;

      e.preventDefault();
      e.stopPropagation();
      handleFocus();

      setIsDragging(true);
      dragStart.current = {
        x: e.clientX,
        y: e.clientY,
        winX: win.position.x,
        winY: win.position.y,
      };
    },
    [win, handleFocus]
  );

  // Resizing
  const handleResizeStart = useCallback(
    (direction: string) => (e: React.MouseEvent) => {
      if (win.maximized) return;
      e.preventDefault();
      e.stopPropagation();
      handleFocus();

      setIsResizing(direction);
      resizeStart.current = {
        x: e.clientX,
        y: e.clientY,
        width: win.size.width,
        height: win.size.height,
      };
    },
    [win, handleFocus]
  );

  // Global mouse move/up for drag and resize
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isDragging) {
        const dx = e.clientX - dragStart.current.x;
        const dy = e.clientY - dragStart.current.y;
        moveWindow(win.id, {
          x: Math.max(0, dragStart.current.winX + dx),
          y: Math.max(0, dragStart.current.winY + dy),
        });
      }

      if (isResizing) {
        const dx = e.clientX - resizeStart.current.x;
        const dy = e.clientY - resizeStart.current.y;
        let newWidth = resizeStart.current.width;
        let newHeight = resizeStart.current.height;

        if (isResizing.includes('e')) newWidth = Math.max(MIN_WINDOW_WIDTH, resizeStart.current.width + dx);
        if (isResizing.includes('w')) newWidth = Math.max(MIN_WINDOW_WIDTH, resizeStart.current.width - dx);
        if (isResizing.includes('s')) newHeight = Math.max(MIN_WINDOW_HEIGHT, resizeStart.current.height + dy);
        if (isResizing.includes('n')) newHeight = Math.max(MIN_WINDOW_HEIGHT, resizeStart.current.height - dy);

        resizeWindow(win.id, { width: newWidth, height: newHeight });
      }
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      setIsResizing(null);
    };

    if (isDragging || isResizing) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      return () => {
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging, isResizing, win.id, moveWindow, resizeWindow]);

  const IconComponent = ICON_MAP[win.icon] || FolderOpen;

  // Compute actual position and size
  const style: React.CSSProperties = win.maximized
    ? {
        left: 0,
        top: 0,
        width: '100%',
        height: `calc(100vh - ${TASKBAR_HEIGHT}px)`,
        zIndex: win.zIndex,
      }
    : {
        left: win.position.x,
        top: win.position.y,
        width: win.size.width,
        height: win.size.height,
        zIndex: win.zIndex,
      };

  return (
    <motion.div
      ref={windowRef}
      className="desktop-window absolute flex flex-col pointer-events-auto"
      style={style}
      initial={{ opacity: 0, scale: 0.92 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.92 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      onClick={handleFocus}
    >
      {/* ===== HOLOGRAPHIC WINDOW CONTAINER ===== */}
      <div
        className={`flex flex-col h-full rounded-lg overflow-hidden ${
          win.isFocused
            ? 'holo-window'
            : 'holo-window opacity-80'
        }`}
      >
        {/* ===== TITLE BAR (Holographic) ===== */}
        <div
          className="flex items-center h-9 px-3 shrink-0 cursor-default holo-titlebar"
          onMouseDown={handleMouseDown}
          onDoubleClick={handleMaximize}
        >
          {/* Icon + Title */}
          <div className="flex items-center gap-2 shrink-0">
            <div className="relative">
              <IconComponent className={`w-3.5 h-3.5 ${win.isFocused ? 'text-cyan-400 drop-shadow-[0_0_6px_rgba(0,212,255,0.5)]' : 'text-cyan-400/40'}`} />
              {win.isFocused && (
                <div className="absolute -inset-1 bg-cyan-400/10 rounded-full blur-sm" />
              )}
            </div>
            <span className={`text-[11px] font-medium tracking-wide truncate max-w-[200px] ${win.isFocused ? 'text-cyan-300/90' : 'text-cyan-300/40'}`}>
              {win.title}
            </span>
          </div>

          {/* Window Controls */}
          <div className="ml-auto flex items-center gap-1 shrink-0">
            <button
              className="window-button w-6 h-6 flex items-center justify-center rounded hover:bg-cyan-500/10 text-cyan-300/50 hover:text-cyan-300 transition-all"
              onClick={handleMinimize}
              title="Minimize"
            >
              <Minus className="w-3 h-3" />
            </button>
            <button
              className="window-button w-6 h-6 flex items-center justify-center rounded hover:bg-cyan-500/10 text-cyan-300/50 hover:text-cyan-300 transition-all"
              onClick={handleMaximize}
              title={win.maximized ? 'Restore' : 'Maximize'}
            >
              {win.maximized ? <Minimize2 className="w-3 h-3" /> : <Maximize2 className="w-3 h-3" />}
            </button>
            <button
              className="window-button w-6 h-6 flex items-center justify-center rounded hover:bg-red-500/20 text-cyan-300/50 hover:text-red-400 transition-all"
              onClick={handleClose}
              title="Close"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* ===== WINDOW CONTENT ===== */}
        <div className="flex-1 overflow-hidden relative" style={{ background: 'rgba(3, 7, 18, 0.7)' }}>
          {/* Resize handles */}
          {!win.maximized && (
            <>
              <div className="absolute top-0 left-0 w-1.5 h-full cursor-w-resize z-10" onMouseDown={handleResizeStart('w')} />
              <div className="absolute top-0 right-0 w-1.5 h-full cursor-e-resize z-10" onMouseDown={handleResizeStart('e')} />
              <div className="absolute top-0 left-0 w-full h-1.5 cursor-n-resize z-10" onMouseDown={handleResizeStart('n')} />
              <div className="absolute bottom-0 left-0 w-full h-1.5 cursor-s-resize z-10" onMouseDown={handleResizeStart('s')} />
              <div className="absolute -top-1 -left-1 w-3 h-3 cursor-nw-resize z-20" onMouseDown={handleResizeStart('nw')} />
              <div className="absolute -top-1 -right-1 w-3 h-3 cursor-ne-resize z-20" onMouseDown={handleResizeStart('ne')} />
              <div className="absolute -bottom-1 -left-1 w-3 h-3 cursor-sw-resize z-20" onMouseDown={handleResizeStart('sw')} />
              <div className="absolute -bottom-1 -right-1 w-3 h-3 cursor-se-resize z-20" onMouseDown={handleResizeStart('se')} />
            </>
          )}

          {/* App Content */}
          <div className="w-full h-full overflow-hidden">
            <React.Suspense
              fallback={
                <div className="flex items-center justify-center h-full">
                  <div className="flex flex-col items-center gap-3">
                    <div className="holo-spinner w-8 h-8" />
                    <span className="text-xs text-cyan-300/50 tracking-wider">INITIALIZING {win.title.toUpperCase()}...</span>
                  </div>
                </div>
              }
            >
              <AppContent appId={win.appId} />
            </React.Suspense>
          </div>
        </div>
      </div>
    </motion.div>
  );
});

// ==================== APP CONTENT RENDERER ====================

function AppContent({ appId }: { appId: string }) {
  const registry = APP_REGISTRY[appId];
  if (!registry) {
    return (
      <div className="flex items-center justify-center h-full text-cyan-300/40 tracking-wider text-sm">
        MODULE NOT FOUND
      </div>
    );
  }

  const AppComponent = registry.component;
  return <AppComponent />;
}
