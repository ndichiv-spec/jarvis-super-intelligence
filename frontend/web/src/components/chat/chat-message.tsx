'use client';

import { memo, useMemo, type ReactNode } from 'react';
import { AlertTriangle, Brain, Loader2, User } from 'lucide-react';

import { cn } from '@/lib/utils';
import { MarkdownMessage } from '@/components/chat/markdown-message';
import { ToolCallList } from '@/components/chat/tool-call-card';
import type { ChatMessage } from '@/features/chat/types';

/**
 * Chat message bubble.
 *
 * Renders one turn of the transcript: role affordance, model attribution,
 * streamed markdown body, and any capabilities the agent invoked while
 * producing it.
 */

interface ChatMessageBubbleProps {
  message: ChatMessage;
  /** This message is still receiving tokens. */
  isStreaming?: boolean;
  className?: string;
}

/** Metadata rows shown under the bubble, when present. */
function MessageMeta({ message }: { message: ChatMessage }) {
  const rows: Array<[string, ReactNode]> = [];

  if (message.confidence !== undefined && message.confidence !== null) {
    const pct = Math.round(message.confidence * 100);
    rows.push(['Confidence', `${pct}%`]);
  }
  if (message.latency_ms !== undefined && message.latency_ms !== null) {
    rows.push(['Latency', `${(message.latency_ms / 1000).toFixed(2)}s`]);
  }
  if (message.skill_used) {
    rows.push(['Skill', message.skill_used]);
  }
  if (message.sources?.length) {
    rows.push(['Sources', String(message.sources.length)]);
  }

  if (!rows.length) return null;

  return (
    <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] uppercase tracking-wider text-muted-foreground/50">
      {rows.map(([label, value]) => (
        <div key={label} className="flex gap-1.5">
          <dt>{label}</dt>
          <dd className="text-foreground/60">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Sources rendered as a compact list of chips. */
function Sources({ sources }: { sources: string[] }) {
  return (
    <div className="mt-2">
      <span className="text-[10px] uppercase tracking-widest text-muted-foreground/50">
        Sources
      </span>
      <ul className="mt-1 flex flex-wrap gap-1.5">
        {sources.map((source, index) => (
          <li
            key={`${source}-${index}`}
            className="max-w-[280px] truncate rounded border border-white/10 bg-white/[0.03] px-1.5 py-0.5 text-[10.5px] text-muted-foreground/70"
          >
            {source}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ChatMessageBubbleImpl({ message, isStreaming = false, className }: ChatMessageBubbleProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const hasError = Boolean(message.error);

  const errorText = useMemo(() => {
    if (!message.error) return null;
    if (typeof message.error === 'string') return message.error;
    return message.error.message ?? 'Request failed';
  }, [message.error]);

  if (isSystem) {
    return (
      <div className={cn('flex justify-center', className)}>
        <p className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[11px] text-muted-foreground/70">
          {message.content}
        </p>
      </div>
    );
  }

  return (
    <div className={cn('flex gap-3', isUser && 'flex-row-reverse', className)}>
      {/* Role affordance */}
      <div
        className={cn(
          'mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border',
          isUser
            ? 'border-blue-500/25 bg-blue-500/10'
            : 'border-cyan-400/25 bg-cyan-400/10 shadow-[0_0_12px_rgba(0,212,255,0.15)]'
        )}
      >
        {isUser ? (
          <User className="h-3.5 w-3.5 text-blue-300" />
        ) : (
          <Brain className="h-3.5 w-3.5 text-cyan-400" />
        )}
      </div>

      <div className={cn('min-w-0 flex-1', isUser && 'flex flex-col items-end')}>
        {/* Attribution */}
        <div
          className={cn(
            'mb-1 flex items-center gap-2 text-[10px] uppercase tracking-widest text-muted-foreground/50',
            isUser && 'flex-row-reverse'
          )}
        >
          <span>{isUser ? 'You' : 'JARVIS'}</span>
          {!isUser && message.model && (
            <>
              <span aria-hidden="true" className="text-white/15">
                /
              </span>
              <span className="truncate">{message.model}</span>
            </>
          )}
          {message.timestamp && (
            <time className="font-normal normal-case tracking-normal opacity-60">
              {new Date(message.timestamp).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </time>
          )}
        </div>

        {/* Body */}
        <div
          className={cn(
            'w-fit max-w-full rounded-xl border px-3.5 py-2.5',
            isUser
              ? 'border-blue-500/20 bg-blue-500/[0.08]'
              : 'border-white/[0.07] bg-white/[0.02] backdrop-blur-sm'
          )}
        >
          {message.content ? (
            isUser ? (
              <p className="whitespace-pre-wrap break-words text-[13.5px] leading-relaxed text-foreground/90">
                {message.content}
              </p>
            ) : (
              <MarkdownMessage streaming={isStreaming}>{message.content}</MarkdownMessage>
            )
          ) : isStreaming ? null : (
            <p className="text-[13.5px] italic text-muted-foreground/50">No content</p>
          )}

          {/* Capabilities invoked to produce this turn */}
          {!isUser && message.tool_calls && message.tool_calls.length > 0 && (
            <ToolCallList tools={message.tool_calls} className="mb-1" />
          )}

          {!isUser && message.runtime_events && message.runtime_events.length > 0 && (
            <ol aria-label="Capability execution activity" className="mt-2 space-y-1 border-l border-cyan-400/20 pl-3">
              {message.runtime_events.map((event) => (
                <li key={event.event_id} className="text-[10.5px] text-muted-foreground/70">
                  <span className={cn(
                    'mr-1.5',
                    event.status === 'completed' ? 'text-emerald-400' :
                      event.status === 'failed' || event.status === 'unavailable' ? 'text-red-400' :
                        'text-cyan-400',
                  )}>
                    {event.status === 'completed' ? '✓' : event.status === 'failed' ? '×' : '●'}
                  </span>
                  <span className="font-medium">{event.capability_id}</span>
                  <span className="mx-1">·</span>
                  <span>{event.message}</span>
                </li>
              ))}
            </ol>
          )}

          {!isUser && message.sources && message.sources.length > 0 && (
            <Sources sources={message.sources} />
          )}

          {!isUser && <MessageMeta message={message} />}
        </div>

        {/* Status line */}
        {isStreaming && (
          <div className="mt-1 flex items-center gap-1.5 text-[10.5px] text-muted-foreground/50">
            <Loader2 className="h-3 w-3 animate-spin text-cyan-400/70" />
            {message.status === 'THINKING' ? 'Thinking' : 'Responding'}
          </div>
        )}

        {message.interrupted && !isStreaming && (
          <p className="mt-1 text-[10.5px] text-amber-400/70">Response interrupted</p>
        )}

        {hasError && (
          <div
            role="alert"
            className="mt-2 flex items-start gap-2 rounded-lg border border-red-400/25 bg-red-500/10 px-3 py-2 text-[12px] text-red-300"
          >
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span className="min-w-0 break-words">{errorText}</span>
          </div>
        )}
      </div>
    </div>
  );
}

export const ChatMessageBubble = memo(ChatMessageBubbleImpl);