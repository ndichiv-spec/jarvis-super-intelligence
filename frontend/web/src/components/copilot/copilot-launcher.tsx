'use client';

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { usePathname } from 'next/navigation';
import { MessageSquare, Sparkles, X } from 'lucide-react';

import { ChatWindow } from '@/components/chat/chat-window';
import { useChatStore } from '@/features/chat/store';
import { useAuthStore } from '@/stores/authStore';

const PUBLIC_ROUTES = [
  '/',
  '/login',
  '/register',
  '/forgot-password',
  '/enterprise-sso',
  '/oauth/callback',
];

function subscribeToNothing() {
  return () => undefined;
}

function getClientSnapshot() {
  return true;
}

function getServerSnapshot() {
  return false;
}

function isPublicRoute(pathname: string | null): boolean {
  if (!pathname) return true;
  return PUBLIC_ROUTES.some((route) =>
    route === '/' ? pathname === route : pathname === route || pathname.startsWith(`${route}/`),
  );
}

export function CopilotLauncher() {
  const pathname = usePathname();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const token = useAuthStore((state) => state.token);
  const isReady = useSyncExternalStore(subscribeToNothing, getClientSnapshot, getServerSnapshot);

  if (!isReady || !isAuthenticated || !token || isPublicRoute(pathname)) return null;
  return <CopilotPanel />;
}

function CopilotPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const browserContextError = useChatStore((state) => state.browserContextError);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const hadFocus = useRef(false);

  useEffect(() => {
    void useChatStore.getState().initChat();
    return () => useChatStore.getState().disposeChat();
  }, []);

  useEffect(() => {
    if (isOpen) {
      hadFocus.current = true;
      const frame = window.requestAnimationFrame(() => {
        panelRef.current?.querySelector<HTMLTextAreaElement | HTMLInputElement>('textarea, input')?.focus();
      });
      return () => window.cancelAnimationFrame(frame);
    }

    if (!hadFocus.current) return;
    hadFocus.current = false;
    const frame = window.requestAnimationFrame(() => launcherRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [isOpen]);

  const toggle = useCallback(() => setIsOpen((open) => !open), []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === 'j') {
        event.preventDefault();
        toggle();
      } else if (event.key === 'Escape' && isOpen) {
        event.preventDefault();
        setIsOpen(false);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, toggle]);

  return (
    <>
      {isOpen && (
        <section
          ref={panelRef}
          id="jarvis-copilot-panel"
          aria-labelledby="jarvis-copilot-title"
          className="fixed bottom-24 right-4 z-[60] flex h-[min(42rem,calc(100dvh-8rem))] w-[min(28rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-cyan-300/20 bg-[#06111d]/[0.97] shadow-[0_24px_80px_rgba(0,0,0,0.6),0_0_32px_rgba(0,212,255,0.08)] backdrop-blur-2xl sm:bottom-24 sm:right-6"
        >
          <header className="flex shrink-0 items-center justify-between border-b border-white/[0.08] bg-gradient-to-r from-cyan-400/[0.08] via-transparent to-emerald-400/[0.04] px-4 py-3">
            <div className="flex min-w-0 items-center gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-cyan-300/15 bg-cyan-300/[0.08] text-cyan-200">
                <Sparkles aria-hidden="true" className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <h2 id="jarvis-copilot-title" className="text-sm font-semibold tracking-wide text-foreground">
                  JARVIS Copilot
                </h2>
                <p className="text-[11px] text-muted-foreground">
                  Shared workspace chat
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              aria-label="Close JARVIS Copilot"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-white/[0.07] hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-300"
            >
              <X aria-hidden="true" className="h-4 w-4" />
            </button>
          </header>
          {browserContextError && (
            <div role="status" className="flex items-center justify-between gap-3 border-b border-amber-300/15 bg-amber-300/[0.06] px-4 py-2 text-xs leading-relaxed text-amber-100/80">
              <p className="min-w-0">Browser context is unavailable: {browserContextError}</p>
              <button
                type="button"
                onClick={() => void useChatStore.getState().initChat()}
                className="min-h-9 shrink-0 rounded-md px-2 font-medium text-amber-100 underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-200"
              >
                Retry
              </button>
            </div>
          )}
          <div className="min-h-0 flex-1">
            <ChatWindow showSidebar={false} className="min-h-0" />
          </div>
        </section>
      )}

      <button
        ref={launcherRef}
        type="button"
        onClick={toggle}
        aria-label="JARVIS Copilot"
        aria-expanded={isOpen}
        aria-controls={isOpen ? 'jarvis-copilot-panel' : undefined}
        aria-keyshortcuts="Control+J Meta+J"
        title="JARVIS Copilot · Ctrl/⌘ J"
        className="fixed bottom-5 right-5 z-[60] flex h-14 items-center gap-2.5 rounded-2xl border border-cyan-300/25 bg-[#071522]/95 px-4 text-sm font-semibold text-cyan-50 shadow-[0_12px_40px_rgba(0,0,0,0.45),0_0_24px_rgba(0,212,255,0.12)] backdrop-blur-xl transition-[border-color,background,transform,box-shadow] hover:-translate-y-0.5 hover:border-cyan-200/45 hover:bg-[#0a1c2b] hover:shadow-[0_16px_48px_rgba(0,0,0,0.5),0_0_30px_rgba(0,212,255,0.18)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-300"
      >
        <MessageSquare aria-hidden="true" className="h-4 w-4 text-cyan-300" />
        <span>Ask JARVIS</span>
        <kbd aria-hidden="true" className="ml-1 hidden rounded-md border border-white/10 bg-white/[0.04] px-1.5 py-0.5 text-[10px] font-medium text-cyan-100/70 sm:inline">
          Ctrl / ⌘ J
        </kbd>
      </button>
    </>
  );
}
