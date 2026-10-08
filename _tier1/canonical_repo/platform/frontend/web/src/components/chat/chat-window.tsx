'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import {
  Bot,
  ChevronDown,
  MessageSquare,
  RefreshCw,
  AlertTriangle,
  Loader2,
  XCircle,
  CheckCircle
} from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ChatMessageBubble } from './chat-message';
import { ChatInput } from './chat-input';
import { SessionList } from './session-list';
import { useChatStore } from '@/features/chat/store';
import type { ChatMessage, ProviderInfo } from '@/features/chat/types';

// Human-readable display names for known providers
const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  google: 'Google Gemini',
  aws: 'AWS Bedrock',
  hf: 'Hugging Face',
  nvidia: 'NVIDIA NIM',
  'jarvis-brain': 'JARVIS Brain',
  silverwing: 'Silverwing',
  claude: 'Claude (Anthropic)',
  anthropic: 'Claude (Anthropic)',
  gemini: 'Google Gemini',
  ollama: 'Local LLM',
};

interface ChatWindowProps {
  className?: string;
  showSidebar?: boolean;
  onVoiceClick?: () => void;
}

function ProviderStatusIcon({ provider }: { provider: ProviderInfo }) {
  if (!provider.available) {
    return <XCircle className="h-3 w-3 text-red-400" />;
  }
  if (provider.healthy === false) {
    return <AlertTriangle className="h-3 w-3 text-amber-400" />;
  }
  return <CheckCircle className="h-3 w-3 text-green-400" />;
}

export function ChatWindow({ className = '', showSidebar = true, onVoiceClick }: ChatWindowProps) {
  const {
    messages,
    sessions,
    currentSessionId,
    isLoading,
    isStreaming,
    streamingContent,
    activeModel,
    modelCatalog,
    sendMessage,
    sendStreamMessage,
    loadSessions,
    loadSession,
    deleteSession,
    newSession,
    switchModel,
    loadModelCatalog,
    error,
    clearError,
  } = useChatStore();

  const messagesScrollAreaRef = useRef<HTMLDivElement>(null);
  const [useStreaming, setUseStreaming] = useState(true);
  const [mobileSessionsOpen, setMobileSessionsOpen] = useState(false);

  useEffect(() => {
    loadSessions();
    loadModelCatalog();
  }, [loadSessions, loadModelCatalog]);

  useEffect(() => {
    const viewport = messagesScrollAreaRef.current?.querySelector<HTMLElement>(
      '[data-radix-scroll-area-viewport]',
    );
    viewport?.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' });
  }, [messages, streamingContent]);

  const handleSend = useCallback(
    (content: string) => {
      if (useStreaming) {
        sendStreamMessage(content);
      } else {
        sendMessage(content);
      }
    },
    [sendMessage, sendStreamMessage, useStreaming]
  );

  // Show streaming content as a temporary message
  const displayMessages: ChatMessage[] = isStreaming && streamingContent
    ? [
        ...messages,
        {
          id: 'streaming',
          role: 'assistant',
          content: streamingContent,
          timestamp: new Date().toISOString(),
          model: activeModel,
        },
      ]
    : messages;
  const latestMessage = messages[messages.length - 1];
  const retryMessage = latestMessage?.role === 'user'
    ? latestMessage
    : latestMessage?.role === 'assistant'
      && !latestMessage.content
      && messages[messages.length - 2]?.role === 'user'
      ? messages[messages.length - 2]
      : undefined;

  // Resolve the human-readable label for the currently active model
  const getActiveModelLabel = (): string => {
    if (activeModel === 'auto' || !modelCatalog) {
      return 'Auto-Select';
    }
    // If it's a provider:model format, find the matching provider
    const colonIdx = activeModel.indexOf(':');
    if (colonIdx > 0) {
      const prov = activeModel.slice(0, colonIdx);
      const model = activeModel.slice(colonIdx + 1);
      const provider = modelCatalog.providers.find((p) => p.provider === prov);
      const label = PROVIDER_LABELS[prov] || provider?.display_name || prov;
      return `${label} · ${model}`;
    }
    // Legacy simple provider names
    const label = PROVIDER_LABELS[activeModel] || activeModel;
    return label;
  };

  // Get the currently selected provider entry (for status display)
  const getCurrentProvider = (): ProviderInfo | undefined => {
    if (!modelCatalog || activeModel === 'auto') return undefined;
    const colonIdx = activeModel.indexOf(':');
    const provName = colonIdx > 0 ? activeModel.slice(0, colonIdx) : activeModel;
    return modelCatalog.providers.find(
      (p) => p.provider === provName
    );
  };

  return (
    <div className={`flex h-full min-w-0 gap-0 ${className}`}>
      {/* Session Sidebar */}
      {showSidebar && (
        <div className="hidden w-64 shrink-0 border-r border-white/5 bg-white/[0.02] p-3 lg:flex lg:flex-col">
          <SessionList
            sessions={sessions}
            currentSessionId={currentSessionId}
            onSelect={loadSession}
            onDelete={deleteSession}
            onNew={newSession}
          />
        </div>
      )}

      {/* Main Chat Area */}
      <div className="flex min-w-0 flex-1 flex-col">
        {showSidebar && (
          <div className="border-b border-white/5 lg:hidden">
            <button
              type="button"
              aria-expanded={mobileSessionsOpen}
              aria-controls="mobile-chat-sessions"
              onClick={() => setMobileSessionsOpen((open) => !open)}
              className="flex w-full items-center justify-between px-4 py-2.5 text-xs text-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cyan-300/50"
            >
              <span className="flex items-center gap-2">
                <MessageSquare aria-hidden="true" className="h-3.5 w-3.5 text-cyan-100/70" />
                Conversation history
                <span className="text-slate-500">({sessions.length})</span>
              </span>
              <ChevronDown className={`h-3.5 w-3.5 text-slate-500 transition-transform ${mobileSessionsOpen ? 'rotate-180' : ''}`} />
            </button>
            {mobileSessionsOpen && (
              <div id="mobile-chat-sessions" className="h-48 px-3 pb-3">
                <SessionList
                  sessions={sessions}
                  currentSessionId={currentSessionId}
                  onSelect={(sessionId) => {
                    void loadSession(sessionId);
                    setMobileSessionsOpen(false);
                  }}
                  onDelete={deleteSession}
                  onNew={() => {
                    newSession();
                    setMobileSessionsOpen(false);
                  }}
                />
              </div>
            )}
          </div>
        )}

        {/* Model Selector Bar */}
        <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-2 border-b border-white/5 px-3 py-2 sm:px-4">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <Bot className="h-4 w-4 text-cyan-400" />
            <span className="hidden text-xs font-medium text-slate-300 sm:inline">
              Active Model:
            </span>
            {modelCatalog === null ? (
              <Loader2 role="status" aria-label="Loading model catalog" className="h-3.5 w-3.5 animate-spin text-slate-400" />
            ) : (
              <select
                value={activeModel}
                onChange={(e) => switchModel(e.target.value)}
                aria-label="Select chat model"
                className="max-w-[180px] rounded-lg border border-white/10 bg-white/[0.03] px-2 py-1 text-xs text-foreground outline-none focus:border-cyan-200/40"
              >
                <option value="auto">Auto-Select</option>
                {modelCatalog?.providers
                  .filter((p) => p.available || p.authorized || p.configured)
                  .map((p) => {
                    const label = PROVIDER_LABELS[p.provider] || p.display_name || p.provider;
                    const optionValue = p.models && p.models.length > 0
                      ? p.models.map((m) => `${p.provider}:${m}`)
                      : [`${p.provider}:${p.model || 'default'}`];
                    return (
                      <optgroup key={p.provider} label={label}>
                        {optionValue.map((val) => (
                          <option key={val} value={val} disabled={!p.available}>
                            {val.split(':')[1]} {p.available ? '' : '(unavailable)'}
                          </option>
                        ))}
                      </optgroup>
                    );
                  })}
              </select>
            )}
            {/* Refresh catalog button */}
            <button
              type="button"
              onClick={loadModelCatalog}
              aria-label="Refresh model catalog"
              className="rounded-md p-1 text-xs text-slate-400 hover:bg-white/[0.05] hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200/50"
              title="Refresh provider list"
            >
              <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Current model with status indicator */}
          <div className="hidden min-w-0 items-center gap-2 text-xs text-slate-300 md:flex">
            <span>{getActiveModelLabel()}</span>
            {(() => {
              const current = getCurrentProvider();
              return current ? <ProviderStatusIcon provider={current} /> : null;
            })()}
          </div>

          <label className="flex items-center gap-2 text-xs text-slate-300">
            <input
              type="checkbox"
              checked={useStreaming}
              onChange={(e) => setUseStreaming(e.target.checked)}
              className="rounded border-white/20 bg-white/5"
            />
            Stream
          </label>
        </div>

        {/* Messages */}
        <ScrollArea ref={messagesScrollAreaRef} className="flex-1 px-4 py-4">
          {displayMessages.length === 0 && !isLoading ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-xl border border-cyan-200/10 bg-cyan-200/[0.04]">
                <Bot aria-hidden="true" className="h-8 w-8 text-cyan-100/80" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-slate-100">
                  How can I help you today?
                </h3>
                <p className="mt-1 text-sm text-slate-400">
                  Ask me anything or give me a task to accomplish
                </p>
              </div>
            </div>
          ) : (
            <div className="mx-auto flex max-w-3xl flex-col gap-4">
              {displayMessages.map((message, index) => (
                <ChatMessageBubble
                  key={message.id || index}
                  message={message}
                  isStreaming={isStreaming && message.id === 'streaming'}
                />
              ))}
            </div>
          )}

          {isLoading && !isStreaming && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-cyan-400" />
            </div>
          )}

          {error && (
            <div role="alert" aria-live="assertive" className="mx-auto mt-4 max-w-3xl rounded-lg border border-rose-300/15 bg-rose-300/[0.05] px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-rose-100">Chat request could not be completed</p>
                  <p className="mt-1 text-xs leading-relaxed text-slate-300">
                    Check the runtime status above, then try again. The chat service may be unavailable.
                  </p>
                </div>
                <div className="ml-auto flex shrink-0 items-center gap-3">
                  {retryMessage && !isLoading && !isStreaming && (
                    <button
                      type="button"
                      onClick={() => handleSend(retryMessage.content)}
                      className="rounded px-1 py-0.5 text-xs font-medium text-cyan-100 underline underline-offset-2 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200/50"
                    >
                      Retry message
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={clearError}
                    aria-label="Dismiss chat error"
                    className="rounded px-1 py-0.5 text-xs text-slate-300 underline underline-offset-2 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200/50"
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            </div>
          )}
        </ScrollArea>

        {/* Input */}
        <div className="border-t border-white/5 p-3 sm:p-4">
          <div className="mx-auto max-w-3xl">
            <ChatInput
              onSend={handleSend}
              onStartVoice={onVoiceClick}
              disabled={isLoading}
              isStreaming={isStreaming}
              onStopStreaming={() => useChatStore.setState({ isStreaming: false })}
            />
            <p className="mt-2 text-center text-xs text-slate-400">
              JARVIS may produce inaccurate information. Verify critical facts.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
