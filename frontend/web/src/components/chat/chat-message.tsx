'use client';

import { memo, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import Image from 'next/image';
import { AlertTriangle, Brain, Loader2, Square, User, Volume2 } from 'lucide-react';

import { cn } from '@/lib/utils';
import { MarkdownMessage } from '@/components/chat/markdown-message';
import { ToolCallList } from '@/components/chat/tool-call-card';
import type { ChatMessage } from '@/features/chat/types';
import { getApiUrl } from '@/lib/runtime-url';

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
  if (message.provider) {
    rows.push(['Provider', message.provider]);
  }
  if (message.model) {
    rows.push(['Model', message.model]);
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

interface GeneratedImageArtifact {
  artifact_id: string;
  url: string;
  prompt: string;
  width: number;
  height: number;
}

function getGeneratedImageArtifacts(metadata?: Record<string, unknown>): GeneratedImageArtifact[] {
  const artifacts = metadata?.artifacts;
  if (!Array.isArray(artifacts)) return [];
  return artifacts.filter((artifact): artifact is GeneratedImageArtifact =>
    typeof artifact === 'object' && artifact !== null
    && typeof artifact.artifact_id === 'string'
    && typeof artifact.url === 'string'
    && /^\/api\/v1\/image\/artifacts\/[A-Za-z0-9_-]+$/.test(artifact.url)
    && typeof artifact.prompt === 'string'
    && typeof artifact.width === 'number'
    && typeof artifact.height === 'number'
  );
}

function GeneratedImage({ artifact }: { artifact: GeneratedImageArtifact }) {
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;

    void fetch(getApiUrl(artifact.url), {
      credentials: 'include',
      cache: 'no-store',
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error(`Image artifact request failed with HTTP ${response.status}`);
      const blob = await response.blob();
      if (!blob.type.startsWith('image/')) throw new Error('Image artifact response was not an image');
      objectUrl = URL.createObjectURL(blob);
      setSrc(objectUrl);
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      setError(reason instanceof Error ? reason.message : 'Generated image could not be loaded');
    });

    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [artifact.url]);

  if (error) return <p role="alert" className="mt-2 text-xs text-amber-300">{error}</p>;
  if (!src) return <p role="status" className="mt-2 text-xs text-muted-foreground">Loading generated image…</p>;

  return (
    <a
      href={src}
      download={`jarvis-image-${artifact.artifact_id}`}
      className="mt-3 block w-fit max-w-full overflow-hidden rounded-lg border border-white/10"
      aria-label={`Download generated image for: ${artifact.prompt}`}
    >
      <Image
        src={src}
        alt="Generated image"
        width={artifact.width}
        height={artifact.height}
        unoptimized
        className="max-h-96 max-w-full object-contain"
      />
    </a>
  );
}

function ChatMessageBubbleImpl({ message, isStreaming = false, className }: ChatMessageBubbleProps) {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [speechError, setSpeechError] = useState<string | null>(null);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const hasError = Boolean(message.error);

  const errorText = useMemo(() => {
    if (!message.error) return null;
    if (typeof message.error === 'string') return message.error;
    return message.error.message ?? 'Request failed';
  }, [message.error]);

  useEffect(() => () => {
    if (utteranceRef.current) {
      window.speechSynthesis?.cancel();
    }
  }, []);

  const toggleSpeech = () => {
    if (isSpeaking) {
      window.speechSynthesis.cancel();
      utteranceRef.current = null;
      setIsSpeaking(false);
      return;
    }
    if (!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) {
      setSpeechError('Spoken playback is not supported by this browser.');
      return;
    }

    setSpeechError(null);
    const utterance = new SpeechSynthesisUtterance(message.content);
    utteranceRef.current = utterance;
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => {
      utteranceRef.current = null;
      setIsSpeaking(false);
    };
    utterance.onerror = () => {
      utteranceRef.current = null;
      setIsSpeaking(false);
      setSpeechError('Browser speech playback failed.');
    };
    window.speechSynthesis.speak(utterance);
  };

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

          {!isUser && getGeneratedImageArtifacts(message.metadata).map((artifact) => (
            <GeneratedImage key={artifact.artifact_id} artifact={artifact} />
          ))}

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

        {!isUser && !isStreaming && message.content && message.status === 'COMPLETED' && (
          <div className="mt-1 flex items-center gap-2">
            <button
              type="button"
              onClick={toggleSpeech}
              className="inline-flex min-h-8 items-center gap-1.5 rounded-md px-2 text-[11px] text-muted-foreground/60 hover:bg-white/[0.05] hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400"
              aria-label={isSpeaking ? 'Stop spoken response' : 'Speak response'}
              title="Spoken playback uses your browser voice"
            >
              {isSpeaking ? <Square className="h-3 w-3" /> : <Volume2 className="h-3 w-3" />}
              {isSpeaking ? 'Stop' : 'Speak'}
            </button>
            {speechError && <span role="status" className="text-[11px] text-amber-300">{speechError}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

export const ChatMessageBubble = memo(ChatMessageBubbleImpl);