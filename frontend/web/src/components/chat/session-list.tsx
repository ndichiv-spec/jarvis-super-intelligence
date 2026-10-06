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
                className={`group flex cursor-pointer items-center gap-2 rounded-xl px-3 py-2.5 text-sm transition-all ${
                  currentSessionId === session.session_id
                    ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                    : 'text-muted-foreground/70 hover:bg-white/5 hover:text-foreground'
                }`}
                onClick={() => onSelect(session.session_id)}
              >
                <MessageSquare className="h-4 w-4 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-medium">
                    {session.preview || 'New conversation'}
                  </div>
                  <div className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground/40">
                    <Clock className="h-3 w-3" />
                    {new Date(session.started).toLocaleDateString()}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0 opacity-0 group-hover:opacity-100 rounded-lg text-muted-foreground/40 hover:text-red-400 hover:bg-red-500/10"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(session.session_id);
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </ScrollArea>
    </div>
  );
}
