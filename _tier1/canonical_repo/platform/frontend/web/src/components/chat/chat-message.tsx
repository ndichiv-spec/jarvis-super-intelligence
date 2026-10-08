'use client';

import { Bot, UserRound } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ChatMessage } from '@/features/chat/types';

interface ChatMessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
}

export function ChatMessageBubble({ message, isStreaming = false }: ChatMessageBubbleProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const messageError = typeof message.error === 'string'
    ? message.error
    : message.error?.message;

  if (isSystem) {
    return (
      <p className="mx-auto max-w-2xl rounded-lg border border-white/[0.07] bg-white/[0.025] px-3 py-2 text-center text-xs text-slate-400">
        {message.content}
      </p>
    );
  }

  return (
    <article className={`flex min-w-0 gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border ${
        isUser
          ? 'border-white/10 bg-white/[0.04] text-slate-300'
          : 'border-cyan-200/10 bg-cyan-200/[0.04] text-cyan-100/80'
      }`}>
        {isUser
          ? <UserRound aria-hidden="true" className="h-3.5 w-3.5" />
          : <Bot aria-hidden="true" className="h-3.5 w-3.5" />}
      </div>
      <div className={`min-w-0 max-w-[min(88%,48rem)] ${isUser ? 'text-right' : ''}`}>
        <div className={`mb-1 flex flex-wrap items-center gap-2 text-xs text-slate-400 ${isUser ? 'justify-end' : ''}`}>
          <span className="font-medium text-slate-400">{isUser ? 'You' : 'JARVIS'}</span>
          {message.model && <span>{message.model}</span>}
          {isStreaming && <span className="text-cyan-100/70">Generating</span>}
          {message.timestamp && (
            <time dateTime={message.timestamp}>
              {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </time>
          )}
        </div>
        <div className={`rounded-xl border px-3.5 py-2.5 text-left text-sm leading-relaxed ${
          isUser
            ? 'border-cyan-200/10 bg-cyan-200/[0.045] text-slate-100'
            : 'border-white/[0.07] bg-white/[0.025] text-slate-200'
        }`}>
          <div className="prose prose-invert prose-sm max-w-none break-words prose-p:my-1.5 prose-headings:my-2 prose-a:text-cyan-200 prose-code:rounded prose-code:bg-black/30 prose-code:px-1 prose-code:py-0.5 prose-code:text-cyan-100 prose-pre:overflow-x-auto prose-pre:border prose-pre:border-white/10 prose-pre:bg-black/30 prose-li:my-0.5">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          </div>
          {messageError && (
            <p role="alert" className="mt-2 border-t border-rose-300/10 pt-2 text-xs text-rose-200">
              {messageError}
            </p>
          )}
        </div>

        {message.tool_calls && message.tool_calls.length > 0 && (
          <ul aria-label="Tool activity" className={`mt-2 space-y-1 ${isUser ? 'text-right' : ''}`}>
            {message.tool_calls.map((tool, index) => (
              <li key={`${tool.name}-${index}`} className="text-xs text-slate-400">
                <span className="font-medium text-slate-400">{tool.name}</span>
                {tool.status && <span> · {tool.status}</span>}
              </li>
            ))}
          </ul>
        )}

        {message.sources && message.sources.length > 0 && (
          <details className="mt-2 text-left">
            <summary className="w-fit cursor-pointer text-xs text-slate-400 transition-colors hover:text-slate-200">
              {message.sources.length} source{message.sources.length === 1 ? '' : 's'}
            </summary>
            <ul className="mt-1 space-y-1 pl-3 text-xs text-slate-400">
              {message.sources.map((source, index) => (
                <li key={`${index}-${source}`} className="break-words">{source}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </article>
  );
}
