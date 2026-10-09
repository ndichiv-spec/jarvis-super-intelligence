'use client';

import { useMemo, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { Clock, MessageSquare, Plus, Search, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { SessionInfo } from '@/features/chat/types';

interface SessionListProps {
  sessions: SessionInfo[];
  currentSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
  onNew: () => void;
}

export function SessionList({
  sessions,
  currentSessionId,
  onSelect,
  onDelete,
  onNew,
}: SessionListProps) {
  const [query, setQuery] = useState('');
  const prefersReducedMotion = useReducedMotion();
  const filteredSessions = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    if (!term) return sessions;
    return sessions.filter((session) => session.preview.toLocaleLowerCase().includes(term));
  }, [query, sessions]);

  return (
    <div className="flex h-full flex-col gap-2">
      <Button
        type="button"
        onClick={onNew}
        className="min-h-10 w-full justify-start gap-2 rounded-lg border border-indigo-300/15 bg-indigo-500/15 text-slate-50 shadow-[0_0_0_1px_rgba(99,102,241,0.08)] transition-colors hover:border-indigo-200/45 hover:bg-indigo-500 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-300"
        variant="ghost"
      >
        <Plus aria-hidden="true" className="h-4 w-4" />
        New conversation
      </Button>

      <label className="relative block shrink-0">
        <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
        <input
          type="search"
          aria-label="Search conversations"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search conversations"
          className="h-9 w-full rounded-lg border border-white/[0.08] bg-black/15 pl-9 pr-3 text-xs text-slate-200 placeholder:text-slate-500 focus:border-indigo-300/40 focus:outline-none focus:ring-2 focus:ring-indigo-300/15"
        />
      </label>

      <ScrollArea className="flex-1">
        <div className="space-y-1 pr-2" aria-live="polite">
          <AnimatePresence initial={false}>
            {filteredSessions.map((session) => {
              const title = session.preview || 'New conversation';
              const date = new Date(session.started).toLocaleDateString();
              const selected = currentSessionId === session.session_id;

              return (
                <motion.div
                  key={session.session_id}
                  initial={prefersReducedMotion ? false : { opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 8 }}
                  transition={{ duration: prefersReducedMotion ? 0 : 0.15 }}
                  className={`group flex items-center gap-1 rounded-lg text-sm transition-colors ${
                    selected
                      ? 'bg-indigo-400/[0.1] text-indigo-100'
                      : 'text-slate-400 hover:bg-white/[0.04] hover:text-slate-100'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(session.session_id)}
                    aria-current={selected ? 'page' : undefined}
                    aria-label={`${title}, ${date}`}
                    className="flex min-h-12 min-w-0 flex-1 items-center gap-2 rounded-lg px-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-300"
                  >
                    <MessageSquare aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-500" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-medium">{title}</span>
                      <span className="mt-1 flex items-center gap-1 text-[10px] text-slate-500">
                        <Clock aria-hidden="true" className="h-3 w-3" />
                        {date}
                      </span>
                    </span>
                  </button>
                  <Button
                    variant="ghost"
                    size="icon"
                    type="button"
                    aria-label={`Delete ${title}`}
                    className="h-8 w-8 shrink-0 rounded-lg text-slate-500 opacity-70 transition-opacity hover:bg-rose-400/10 hover:text-rose-200 focus-visible:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-rose-200 group-hover:opacity-100"
                    onClick={() => onDelete(session.session_id)}
                  >
                    <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />
                  </Button>
                </motion.div>
              );
            })}
          </AnimatePresence>
          {filteredSessions.length === 0 && (
            <p role="status" className="px-2 py-5 text-center text-xs leading-relaxed text-slate-500">
              {query.trim()
                ? 'No saved conversations match your search.'
                : 'Your saved conversations will appear here.'}
            </p>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
