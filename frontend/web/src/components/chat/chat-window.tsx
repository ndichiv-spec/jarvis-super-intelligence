'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import {
  Activity,
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
import { isCurrentLocationRequest, useChatStore } from '@/features/chat/store';
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

export function ChatWindow({ className = '', showSidebar = true }: ChatWindowProps) {
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
    stopStream,
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
    messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
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
      if (useStreaming && !isCurrentLocationRequest(content)) {
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
    if (useStreaming && !isCurrentLocationRequest(retryableMessage.content)) {
      sendStreamMessage(retryableMessage.content, clientMessageId);
    } else {
      sendMessage(retryableMessage.content, clientMessageId);
    }
  }, [isLoading, isStreaming, messages, retryableMessage, sendMessage, sendStreamMessage, useStreaming]);

  const isNetworkUnavailable = !connected && Boolean(error) &&
    /failed to fetch|fetch failed|network(?:error| request failed)|load failed/i.test(error ?? '');
  const isServiceError = /(?:status|http)\s*(?:code\s*)?5\d{2}|service unavailable|bad gateway|gateway timeout/i
    .test(error ?? '');
  const hasUsableProvider = modelCatalog !== null && modelCatalog.providers.some(
    (provider) => provider.available || provider.authorized || provider.configured,
  );
  const isRoutingLoading = modelCatalog === null;
  const isChatReady = !isRoutingLoading && hasUsableProvider;
  const friendlyError = error
    ? (() => {
        const normalized = error.toLowerCase();
        if (/signal is aborted|signal was aborted|aborted without reason|abort.*reason/i.test(normalized)) {
          return {
            title: 'The request was interrupted before a response arrived',
            detail: 'Retry the message or refresh the provider list. The backend is reachable, but the request did not complete.',
          };
        }
        if (isNetworkUnavailable) {
          return {
            title: 'Unable to reach the JARVIS chat service',
            detail: 'The message was not delivered. Check your connection or backend status, then retry.',
          };
        }
        if (isServiceError) {
          return {
            title: 'The JARVIS chat service returned an error',
            detail: 'The service responded but did not complete the request. Retry in a moment.',
          };
        }
        return {
          title: 'JARVIS could not complete that request',
          detail: error,
        };
      })()
    : null;

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
      <div className="flex min-w-0 flex-1 flex-col bg-[#090e16]">
        {/* Model Selector Bar */}
        <div className="flex min-h-12 flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-white/[0.06] bg-[#0a101a]/75 px-4 py-2 sm:px-6">
          <div className="flex min-w-0 items-center gap-2">
            <span aria-hidden="true" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-indigo-300/15 bg-indigo-400/[0.07] text-indigo-200">
              <Activity className="h-4 w-4" />
            </span>
            <label htmlFor="chat-model" className="sr-only">Chat model</label>
            {modelCatalog === null ? (
              <span role="status" aria-label="Loading chat models" className="inline-flex items-center gap-2 text-xs text-slate-500">
                <Loader2 className="h-3 w-3 animate-spin" />
                Loading routing options
              </span>
            ) : (
              <select
                id="chat-model"
                value={activeModel}
                onChange={(e) => switchModel(e.target.value)}
                aria-label="Choose chat model"
                className="max-w-[min(65vw,20rem)] rounded-lg border border-white/[0.08] bg-[#0c1420] px-2.5 py-1.5 text-xs text-slate-300 outline-none transition hover:border-white/15 focus-visible:border-indigo-300/40 focus-visible:ring-2 focus-visible:ring-indigo-300/15"
              >
                <option value="auto">Automatic routing</option>
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
              aria-label="Refresh provider list"
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-white/[0.05] hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-300"
              title="Refresh provider list"
            >
              <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Current model with status indicator */}
          {modelCatalog && activeModel !== 'auto' && (
            <div className="flex min-w-0 items-center gap-2 text-[11px] text-slate-500">
              <span className="truncate">{getActiveModelLabel()}</span>
              {(() => {
                const current = getCurrentProvider();
                return current ? <ProviderStatusIcon provider={current} /> : null;
              })()}
            </div>
          )}

          <label className="flex items-center gap-2 text-[11px] text-slate-500">
            <input
              type="checkbox"
              checked={useStreaming}
              onChange={(e) => setUseStreaming(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-white/20 bg-white/5 accent-indigo-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-300"
            />
            Stream replies
          </label>
        </div>

        {/* Messages */}
        <ScrollArea className="min-h-0 flex-1 px-4 py-4 sm:px-6">
          {displayMessages.length === 0 && !isLoading ? (
            <div className="mx-auto flex min-h-full max-w-2xl flex-col items-center justify-center gap-5 px-4 py-12 text-center">
              <div className="flex items-center justify-center">
                <div aria-hidden="true" className="flex items-center gap-2 rounded-full border border-white/[0.08] bg-slate-900/70 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.22em] text-indigo-200/80">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  JARVIS // console
                </div>
              </div>
              <div className="space-y-2">
                <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-indigo-200/65">
                  {error ? 'Runtime unavailable' : isRoutingLoading ? 'Checking chat routing' : isChatReady ? 'Your workspace is ready' : 'Awaiting live routing'}
                </p>
                <h2 className="text-2xl font-medium tracking-[-0.035em] text-slate-100 sm:text-3xl">
                  {error
                    ? 'JARVIS cannot answer right now'
                    : isRoutingLoading
                      ? 'Checking the chat routing path'
                      : isChatReady
                        ? 'Where should we start?'
                        : 'No live model is ready yet'}
                </h2>
                <p className="mx-auto max-w-md text-sm leading-6 text-slate-400">
                  {error
                    ? 'The conversation shell is available, but the backend is not ready to answer yet.'
                    : isRoutingLoading
                      ? 'JARVIS is checking the backend and available models before the first response.'
                      : isChatReady
                        ? 'Send a message to begin a conversation. JARVIS will respond through the configured chat service.'
                        : 'The connected backend is running, but no configured chat provider is currently available.'}
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
                  <p className="font-medium text-rose-50">
                    {friendlyError?.title ?? 'JARVIS could not complete that request'}
                  </p>
                  <p className="mt-1 break-words text-xs leading-relaxed text-rose-100/80">
                    {friendlyError?.detail ?? error}
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
        <div className="border-t border-white/[0.06] bg-[#090e16] px-3 py-3 sm:px-6 sm:py-4">
          <div className="mx-auto max-w-3xl">
            <ChatInput
              onSend={handleSend}
              disabled={isLoading}
              isStreaming={isStreaming}
              onStopStreaming={stopStream}
            />
            <p className="mt-2 text-center text-[10px] font-medium leading-relaxed text-slate-400">
              JARVIS may produce inaccurate information. Verify critical facts.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
