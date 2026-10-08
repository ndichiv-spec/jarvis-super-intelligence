'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { MessageSquare, Trash2, Plus, Clock } from 'lucide-react';
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
  return (
    <div className="flex h-full flex-col gap-2">
      <Button
        onClick={onNew}
        className="w-full gap-2 rounded-xl bg-gradient-to-r from-blue-500/20 to-cyan-500/20 text-blue-400 hover:from-blue-500/30 hover:to-cyan-500/30 border border-blue-500/20"
        variant="ghost"
      >
        <Plus className="h-4 w-4" />
        New Chat
      </Button>

      <ScrollArea className="flex-1">
        <div className="space-y-1 pr-2">
          <AnimatePresence initial={false}>
            {sessions.map((session) => (
              <motion.div
                key={session.session_id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 10 }}
                className={`group flex min-w-0 items-center gap-1 rounded-xl px-1.5 py-1.5 text-sm transition-all ${
                  currentSessionId === session.session_id
                    ? 'bg-cyan-200/[0.06] text-cyan-100 border border-cyan-200/15'
                    : 'text-slate-300 hover:bg-white/5 hover:text-foreground'
                }`}
              >
                <button
                  type="button"
                  aria-pressed={currentSessionId === session.session_id}
                  onClick={() => onSelect(session.session_id)}
                  className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-1.5 py-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200/50"
                >
                  <MessageSquare aria-hidden="true" className="h-4 w-4 shrink-0" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-medium">
                      {session.preview || 'New conversation'}
                    </span>
                    <span className="mt-0.5 flex items-center gap-1 text-xs text-slate-400">
                      <Clock aria-hidden="true" className="h-3 w-3" />
                      {new Date(session.started).toLocaleDateString()}
                    </span>
                  </span>
                </button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Delete conversation ${session.preview || 'New conversation'}`}
                  title="Delete conversation"
                  className="h-8 w-8 shrink-0 rounded-lg text-slate-400 hover:bg-rose-300/10 hover:text-rose-200 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(session.session_id);
                  }}
                >
                  <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />
                </Button>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </ScrollArea>
    </div>
  );
}
