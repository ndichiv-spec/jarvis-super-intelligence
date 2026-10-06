'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import {
  Bot,
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
import { newClientMessageId } from '@/features/chat/api';
import type { ChatMessage, ProviderInfo } from '@/features/chat/types';
import { detectAIMood, useNeuralTheme } from '@/lib/neural-theme-engine';

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
    connected,
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

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const lastMoodMessageId = useRef<string | null>(null);
  const [useStreaming, setUseStreaming] = useState(true);
  const { autoThemeEnabled, setMood } = useNeuralTheme();

  useEffect(() => {
    loadSessions();
    loadModelCatalog();
  }, [loadSessions, loadModelCatalog]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  useEffect(() => {
    if (!autoThemeEnabled) return;
    const latestAssistantMessage = [...messages].reverse().find(
      (message) => message.role === 'assistant' && !message.error,
    );
    if (!latestAssistantMessage?.id || latestAssistantMessage.id === lastMoodMessageId.current) return;
    lastMoodMessageId.current = latestAssistantMessage.id;
    setMood(detectAIMood(latestAssistantMessage.content));
  }, [messages, autoThemeEnabled, setMood]);

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

  const retryableMessage = [...messages].reverse().find(
    (message) => message.role === 'user' && message.content.trim().length > 0,
  );
  const handleRetry = useCallback(() => {
    if (!retryableMessage || isLoading || isStreaming) return;
    const retryStartIndex = messages.findIndex((message) => message.id === retryableMessage.id);
    if (retryStartIndex < 0) return;
    const clientMessageId = retryableMessage.client_message_id || newClientMessageId();

    useChatStore.setState({
      messages: messages.slice(0, retryStartIndex),
      error: null,
    });
    if (useStreaming) {
      sendStreamMessage(retryableMessage.content, clientMessageId);
    } else {
      sendMessage(retryableMessage.content, clientMessageId);
    }
  }, [isLoading, isStreaming, messages, retryableMessage, sendMessage, sendStreamMessage, useStreaming]);

  const isNetworkUnavailable = !connected && Boolean(error) &&
    /failed to fetch|fetch failed|network(?:error| request failed)|load failed/i.test(error ?? '');
  const isServiceError = /(?:status|http)\s*(?:code\s*)?5\d{2}|service unavailable|bad gateway|gateway timeout/i
    .test(error ?? '');

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
    <div className={`flex h-full gap-0 ${className}`}>
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
      <div className="flex flex-1 flex-col">
        {/* Model Selector Bar */}
        <div className="flex items-center justify-between border-b border-white/5 px-4 py-2">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-cyan-400" />
            <span className="text-xs font-medium text-muted-foreground/60">
              Active Model:
            </span>
            {modelCatalog === null ? (
              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground/40" />
            ) : (
              <select
                value={activeModel}
                onChange={(e) => switchModel(e.target.value)}
                className="rounded-lg border border-white/10 bg-white/[0.03] px-2 py-1 text-xs text-foreground outline-none focus:border-blue-500/40"
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
              onClick={loadModelCatalog}
              className="rounded-md p-1 text-xs text-muted-foreground/40 hover:text-foreground/70 hover:bg-white/[0.05]"
              title="Refresh provider list"
            >
              <RefreshCw className="h-3 w-3" />
            </button>
          </div>

          {/* Current model with status indicator */}
          <div className="flex items-center gap-2 text-xs text-muted-foreground/60">
            <span>{getActiveModelLabel()}</span>
            {(() => {
              const current = getCurrentProvider();
              return current ? <ProviderStatusIcon provider={current} /> : null;
            })()}
          </div>

          <label className="flex items-center gap-2 text-xs text-muted-foreground/50">
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
        <ScrollArea className="flex-1 px-4 py-4">
          {displayMessages.length === 0 && !isLoading && !error ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500/20 to-cyan-500/20 border border-blue-500/10">
                <Bot className="h-8 w-8 text-cyan-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
                  How can I help you today?
                </h3>
                <p className="mt-1 text-sm text-muted-foreground/50">
                  Ask me anything or give me a task to accomplish
                </p>
              </div>
            </div>
          ) : displayMessages.length > 0 ? (
            <div className="mx-auto flex max-w-3xl flex-col gap-4">
              {displayMessages.map((message, index) => (
                <ChatMessageBubble
                  key={message.id || index}
                  message={message}
                  isStreaming={isStreaming && message.id === 'streaming'}
                />
              ))}
            </div>
          ) : null}

          {isLoading && !isStreaming && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-cyan-400" />
            </div>
          )}

          {error && (
            <div role="alert" className="mx-auto mt-4 max-w-3xl rounded-xl border border-rose-400/20 bg-rose-400/[0.07] p-3.5 text-sm text-rose-100">
              <div className="flex items-start gap-3">
                <AlertTriangle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-rose-300" />
                <div className="min-w-0 flex-1">
                  <p className="font-medium">
                    {isNetworkUnavailable
                      ? 'Unable to reach the JARVIS chat service'
                      : isServiceError
                        ? 'The JARVIS chat service returned an error'
                        : 'JARVIS could not complete that request'}
                  </p>
                  <p className="mt-1 break-words text-xs leading-relaxed text-rose-100/70">
                    {isNetworkUnavailable
                      ? 'The message was not delivered. Check your connection or backend status, then retry.'
                      : isServiceError
                        ? 'The service responded but did not complete the request. Retry in a moment.'
                        : error}
                  </p>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2 pl-7">
                {retryableMessage && (
                  <button
                    type="button"
                    onClick={handleRetry}
                    disabled={isLoading || isStreaming}
                    className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-rose-200/20 bg-rose-200/[0.08] px-3 text-xs font-medium text-rose-50 transition-colors hover:bg-rose-200/[0.14] focus-visible:outline focus-visible:outline-2 focus-visible:outline-rose-200 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
                    Retry last message
                  </button>
                )}
                <button
                  type="button"
                  onClick={clearError}
                  className="min-h-10 rounded-lg px-3 text-xs text-rose-100/65 underline-offset-4 transition-colors hover:text-rose-50 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-rose-200"
                >
                  Dismiss
                </button>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </ScrollArea>

        {/* Input */}
        <div className="border-t border-white/5 p-4">
          <div className="mx-auto max-w-3xl">
            <ChatInput
              onSend={handleSend}
              onStartVoice={onVoiceClick}
              disabled={isLoading}
              isStreaming={isStreaming}
              onStopStreaming={() => useChatStore.setState({ isStreaming: false })}
            />
            <p className="mt-2 text-center text-[10px] text-muted-foreground/30">
              JARVIS may produce inaccurate information. Verify critical facts.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
