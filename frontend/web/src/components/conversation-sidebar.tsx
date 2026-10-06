"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus,
  Trash2,
  Edit3,
  Check,
  X,
  Clock,
  MessageSquare,
  MoreHorizontal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useChatStore } from "@/features/chat/store";
import type { SessionInfo } from "@/features/chat/types";
import { formatDistanceToNow } from "date-fns";

interface ConversationSidebarProps {
  /** Whether the sidebar is visible (mobile drawer control). */
  open: boolean;
  /** Toggle visibility — used by mobile hamburger / overlay. */
  onOpenChange: (open: boolean) => void;
  /** Optional explicit width override. */
  className?: string;
}

/**
 * ConversationHistorySidebar
 *
 * A collapsible / overlay sidebar that lists chat sessions fetched from
 * `/api/chat/sessions`, lets the user start a new conversation, switch to an
 * existing session (loads full message history), rename sessions inline,
 * and delete sessions.
 *
 * All session state lives in the Zustand `useChatStore` so the sidebar and
 * the chat view stay in sync without prop-drilling.
 */
export default function ConversationHistorySidebar({
  open,
  onOpenChange,
  className = "",
}: ConversationSidebarProps) {
  const {
    sessions,
    currentSessionId,
    loadSessions,
    loadSession,
    newSession,
    deleteSession,
    renameSession,
  } = useChatStore((state) => ({
    sessions: state.sessions,
    currentSessionId: state.currentSessionId,
    loadSessions: state.loadSessions,
    loadSession: state.loadSession,
    newSession: state.newSession,
    deleteSession: state.deleteSession,
    renameSession: state.renameSession,
  }));

  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editTitle, setEditTitle] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // Fetch sessions on mount and when the component becomes visible.
  React.useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  // Focus the edit input when entering edit mode.
  React.useEffect(() => {
    if (editingId) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editingId]);

  const handleNewSession = async () => {
    newSession();
    // The backend generates a session lazily on first message, so we don't
    // need an API call here — just reset local state.
    onOpenChange(false);
  };

  const handleSelectSession = async (session: SessionInfo) => {
    if (session.archived) return;
    setIsLoading(true);
    try {
      await loadSession(session.session_id);
      onOpenChange(false);
    } catch (e) {
      console.error("Failed to load session:", e);
    } finally {
      setIsLoading(false);
    }
  };

  const startRename = (session: SessionInfo) => {
    setEditingId(session.session_id);
    setEditTitle(session.preview || "New conversation");
  };

  const confirmRename = () => {
    if (!editingId) return;

    const trimmed = editTitle.trim() || "Untitled";
    void renameSession(editingId, trimmed);

    setEditingId(null);
    setEditTitle("");
  };

  const cancelRename = () => {
    setEditingId(null);
    setEditTitle("");
  };

  const handleDelete = async (session: SessionInfo) => {
    await deleteSession(session.session_id);
    if (currentSessionId === session.session_id) {
      newSession();
    }
  };

  const sortedSessions = React.useMemo(() => {
    return [...sessions].sort(
      (a, b) =>
        new Date(b.last_active || b.started).getTime() -
        new Date(a.last_active || a.started).getTime()
    );
  }, [sessions]);

  const SessionRow = ({ session }: { session: SessionInfo }) => {
    const isCurrent = currentSessionId === session.session_id;
    const isActive = !session.archived;
    const lastActive = session.last_active || session.started;

    return (
      <div
        className={`
          group relative flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm cursor-pointer
          transition-all duration-150
          ${
            isCurrent
              ? "bg-cyan-500/10 border border-cyan-500/30 text-cyan-100"
              : "hover:bg-white/[0.04] border border-transparent text-gray-300"
          }
          ${!isActive ? "opacity-50" : ""}
        `}
        onClick={() => isActive && editingId !== session.session_id && handleSelectSession(session)}
        onKeyDown={(e) => e.key === "Enter" && isActive && handleSelectSession(session)}
      >
        <MessageSquare className="h-4 w-4 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          {editingId === session.session_id ? (
            <Input
              ref={inputRef}
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") confirmRename();
                if (e.key === "Escape") cancelRename();
              }}
              className="h-6 text-sm bg-white/[0.05] border-white/10 focus:border-cyan-500/40"
              onClick={(e) => e.stopPropagation()}
              size={20}
            />
          ) : (
            <>
              <div className="font-medium truncate">
                {session.preview || "Untitled conversation"}
              </div>
              <div className="flex items-center gap-1.5 text-xs text-gray-500">
                <Clock className="h-3 w-3" />
                {formatDistanceToNow(new Date(lastActive), {
                  addSuffix: true,
                })}
                {session.message_count && session.message_count > 0 && (
                  <>
                    <span>•</span>
                    <span>{session.message_count} msgs</span>
                  </>
                )}
              </div>
            </>
          )}
        </div>

        {editingId !== session.session_id && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-5 w-5 opacity-0 group-hover:opacity-100 p-0 hover:bg-white/[0.05]"
                onClick={(e) => e.stopPropagation()}
              >
                <MoreHorizontal className="h-3 w-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="end"
              className="bg-gray-900 border-white/10 text-gray-200"
            >
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation();
                  startRename(session);
                }}
              >
                <Edit3 className="h-3 w-3 mr-2" /> Rename
              </DropdownMenuItem>
              <DropdownMenuSeparator className="bg-white/10" />
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation();
                  handleDelete(session);
                }}
                className="text-red-400 focus:text-red-400"
              >
                <Trash2 className="h-3 w-3 mr-2" /> Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}

        {editingId === session.session_id && (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-5 w-5 p-0"
              onClick={(e) => {
                e.stopPropagation();
                confirmRename();
              }}
            >
              <Check className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-5 w-5 p-0"
              onClick={(e) => {
                e.stopPropagation();
                cancelRename();
              }}
            >
              <X className="h-3 w-3" />
            </Button>
          </div>
        )}
      </div>
    );
  };

  return (
    <>
      {/* Desktop: always-visible sidebar with overlay for mobile */}
      <AnimatePresence>
        {open && (
          <>
            {/* Mobile overlay */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/50 lg:hidden"
              onClick={() => onOpenChange(false)}
            />

            {/* Sidebar */}
            <motion.aside
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "tween", duration: 0.2 }}
              className={`
                fixed top-0 left-0 z-50 h-full flex flex-col
                w-72 border-r border-white/10
                bg-[hsl(222,47%,10%)]/95 backdrop-blur-xl
                lg:relative lg:translate-x-0 lg:z-auto
                ${className}
              `}
            >
              <div className="flex items-center justify-between p-3 border-b border-white/10">
                <h2 className="text-sm font-semibold text-gray-300">
                  Conversations
                </h2>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 w-6 p-0 hover:bg-white/[0.05]"
                    onClick={handleNewSession}
                    title="New conversation"
                  >
                    <Plus className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 w-6 p-0 hover:bg-white/[0.05]"
                    onClick={() => void loadSessions()}
                    title="Refresh"
                  >
                    <AnimatePresence>
                      {isLoading && (
                        <motion.div
                          animate={{ rotate: 360 }}
                          transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                        >
                          <Clock className="h-3.5 w-3.5" />
                        </motion.div>
                      )}
                    </AnimatePresence>
                    {!isLoading && <Clock className="h-3.5 w-3.5" />}
                  </Button>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto py-2 space-y-1 px-2">
                {sortedSessions.length === 0 ? (
                  <div className="text-center py-8 text-gray-500">
                    <MessageSquare className="h-10 w-10 mx-auto mb-3 opacity-30" />
                    <p className="text-sm">No conversations yet</p>
                    <p className="text-xs mt-1 opacity-50">
                      Start a new conversation to begin
                    </p>
                  </div>
                ) : (
                  sortedSessions.map((session) => (
                    <SessionRow key={session.session_id} session={session} />
                  ))
                )}
              </div>

              <div className="p-2 border-t border-white/10">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full justify-start gap-2 border-white/10 text-gray-300 hover:bg-white/[0.05]"
                  onClick={handleNewSession}
                >
                  <Plus className="h-4 w-4" />
                  New conversation
                </Button>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
