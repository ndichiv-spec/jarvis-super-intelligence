'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useChatStore } from '@/stores/chat-store';
import { jarvisAPI, ChatMessage } from '@/lib/api';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Send, Bot, User, Sparkles, Trash2, Cpu, Zap,
  MessageSquare, Brain, Shield, Activity,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Holographic typing indicator
function TypingIndicator() {
  return (
    <div className="flex gap-1.5 px-4 py-3">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(0,212,255,0.5)]"
          style={{
            animation: 'typing 1.4s infinite',
            animationDelay: `${i * 0.2}s`,
          }}
        />
      ))}
    </div>
  );
}

export default function ChatApp() {
  const { messages, isLoading, isStreaming, streamingContent, setMessages, setLoading, setStreaming, updateStreamingContent } = useChatStore();
  const [input, setInput] = useState('');
  const [model, setModel] = useState<'local' | 'openai' | 'gemini'>('local');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      role: 'user',
      content: input.trim(),
      timestamp: new Date().toISOString(),
    };

    setMessages([...messages, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await jarvisAPI.chat(userMessage.content, model);
      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: response.response || response.message || 'No response',
        timestamp: new Date().toISOString(),
        confidence: response.confidence,
        sources: response.sources,
        model: response.model,
      };
      setMessages([...messages, userMessage, assistantMessage]);
    } catch (error) {
      const errorMessage: ChatMessage = {
        role: 'assistant',
        content: `Error: ${error instanceof Error ? error.message : 'Failed to get response'}`,
        timestamp: new Date().toISOString(),
      };
      setMessages([...messages, userMessage, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    // Auto-resize
    const t = e.target;
    t.style.height = '40px';
    t.style.height = Math.min(t.scrollHeight, 120) + 'px';
  };

  const clearChat = () => {
    setMessages([]);
  };

  // Quick prompts
  const quickPrompts = [
    { icon: Brain, label: 'Analyze', prompt: 'Analyze this data and provide insights:' },
    { icon: Cpu, label: 'Code', prompt: 'Write production-ready code for:' },
    { icon: Sparkles, label: 'Create', prompt: 'Help me create something amazing:' },
    { icon: Zap, label: 'Automate', prompt: 'Help me automate this task:' },
  ];

  return (
    <div className="flex flex-col h-full" style={{ background: 'rgba(3, 7, 18, 0.85)' }}>
      {/* ===== HEADER (Holographic) ===== */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-cyan-500/20 holo-titlebar">
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <Sparkles className="w-4 h-4 text-cyan-400 drop-shadow-[0_0_6px_rgba(0,212,255,0.5)]" />
          </div>
          <span className="text-xs font-medium tracking-wider text-holo">J.A.R.V.I.S. NEURAL LINK</span>
          <div className="flex items-center gap-1 ml-2">
            <Shield className="w-3 h-3 text-emerald-400/50" />
            <span className="text-[9px] text-emerald-400/50 tracking-wider hud-readout">SECURE</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Model Selector */}
          <div className="flex items-center gap-1">
            {[
              { id: 'local' as const, label: 'LOCAL' },
              { id: 'openai' as const, label: 'GPT-4' },
              { id: 'gemini' as const, label: 'GEMINI' },
            ].map((m) => (
              <button
                key={m.id}
                onClick={() => setModel(m.id)}
                className={`px-2 py-1 rounded text-[9px] tracking-wider transition-all hud-readout ${
                  model === m.id
                    ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 shadow-[0_0_8px_rgba(0,212,255,0.2)]'
                    : 'text-cyan-300/40 hover:text-cyan-300/60 hover:bg-cyan-500/5'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>

          {/* Clear */}
          <button
            onClick={clearChat}
            className="flex items-center gap-1 text-[9px] text-cyan-300/40 hover:text-red-400 transition-colors px-2 py-1 rounded-lg hover:bg-red-500/10 tracking-wider hud-readout"
          >
            <Trash2 className="w-3 h-3" />
            CLEAR
          </button>
        </div>
      </div>

      {/* ===== STATUS BAR ===== */}
      <div className="flex items-center justify-between px-4 py-1.5 border-b border-cyan-500/10 bg-cyan-500/[0.02]">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <Activity className="w-3 h-3 text-cyan-400/50" />
            <span className="text-[9px] text-cyan-300/40 tracking-wider hud-readout">
              {messages.length} MESSAGES
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <Cpu className="w-3 h-3 text-cyan-400/50" />
            <span className="text-[9px] text-cyan-300/40 tracking-wider hud-readout">
              {model === 'local' ? 'OLLAMA' : model === 'openai' ? 'OPENAI' : 'GOOGLE'}
            </span>
          </div>
        </div>
        {isLoading && (
          <div className="flex items-center gap-1.5">
            <div className="holo-spinner w-3.5 h-3.5" />
            <span className="text-[9px] text-cyan-400/50 tracking-wider hud-readout animate-pulse">PROCESSING</span>
          </div>
        )}
      </div>

      {/* ===== MESSAGES ===== */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
        {/* Empty state */}
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            {/* Arc Reactor Centerpiece */}
            <div className="relative mb-6">
              <div className="w-20 h-20 rounded-full bg-gradient-to-br from-cyan-500/20 to-teal-500/10 border border-cyan-500/30 flex items-center justify-center shadow-[0_0_30px_rgba(0,212,255,0.2)]">
                <Brain className="w-10 h-10 text-cyan-400 drop-shadow-[0_0_12px_rgba(0,212,255,0.5)]" />
              </div>
              {/* Outer ring */}
              <div className="absolute -inset-3 rounded-full border border-cyan-500/10 animate-pulse" />
              <div className="absolute -inset-6 rounded-full border border-cyan-500/5" />
            </div>

            <h2 className="text-lg font-semibold text-holo tracking-wider mb-2">
              NEURAL CORE ONLINE
            </h2>
            <p className="text-sm text-cyan-300/40 tracking-wide max-w-xs mb-6">
              J.A.R.V.I.S. is ready. How may I assist you, sir?
            </p>

            {/* Quick Prompts */}
            <div className="grid grid-cols-2 gap-2 w-full max-w-sm">
              {quickPrompts.map((qp) => {
                const Ic = qp.icon;
                return (
                  <button
                    key={qp.label}
                    onClick={() => {
                      setInput(qp.prompt);
                      inputRef.current?.focus();
                    }}
                    className="flex items-center gap-2 px-3 py-2.5 rounded-lg holo-button text-left group"
                  >
                    <Ic className="w-4 h-4 text-cyan-400 group-hover:drop-shadow-[0_0_6px_rgba(0,212,255,0.5)] transition-all" />
                    <span className="text-xs text-cyan-300/70 group-hover:text-cyan-300 tracking-wider">{qp.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Messages */}
        <AnimatePresence>
          {messages.map((msg, idx) => {
            const isUser = msg.role === 'user';
            return (
              <motion.div
                key={idx}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25 }}
                className={`flex gap-3 ${isUser ? 'justify-end' : ''}`}
              >
                {!isUser && (
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500/20 to-teal-500/10 border border-cyan-500/30 flex items-center justify-center shrink-0 shadow-[0_0_10px_rgba(0,212,255,0.15)]">
                    <Bot className="w-4 h-4 text-cyan-400 drop-shadow-[0_0_4px_rgba(0,212,255,0.4)]" />
                  </div>
                )}

                <div
                  className={`max-w-[75%] rounded-lg px-4 py-3 ${
                    isUser ? 'msg-user' : 'msg-assistant'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className={`text-[9px] tracking-wider hud-readout ${isUser ? 'text-blue-400/70' : 'text-cyan-400/70'}`}>
                      {isUser ? 'USER' : 'J.A.R.V.I.S.'}
                    </span>
                    {msg.model && (
                      <span className="text-[8px] text-cyan-300/30 tracking-wider hud-readout">
                        [{msg.model.toUpperCase()}]
                      </span>
                    )}
                  </div>

                  {isUser ? (
                    <p className="text-sm text-cyan-100/90 whitespace-pre-wrap">{msg.content}</p>
                  ) : (
                    <ReactMarkdown remarkPlugins={[remarkGfm]} className="prose prose-sm max-w-none">
                      {msg.content}
                    </ReactMarkdown>
                  )}

                  {msg.confidence !== undefined && !isUser && (
                    <div className="mt-2 flex items-center gap-2">
                      <div className="w-16 h-1 holo-progress rounded-full overflow-hidden">
                        <div
                          className="h-full holo-progress-bar rounded-full"
                          style={{ width: `${Math.round(msg.confidence * 100)}%` }}
                        />
                      </div>
                      <span className="text-[8px] text-cyan-300/40 tracking-wider hud-readout">
                        {Math.round(msg.confidence * 100)}%
                      </span>
                    </div>
                  )}
                </div>

                {isUser && (
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500/20 to-indigo-500/10 border border-blue-500/30 flex items-center justify-center shrink-0 shadow-[0_0_10px_rgba(59,130,246,0.15)]">
                    <User className="w-4 h-4 text-blue-400" />
                  </div>
                )}
              </motion.div>
            );
          })}
        </AnimatePresence>

        {/* Streaming content */}
        {isStreaming && streamingContent && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex gap-3"
          >
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500/20 to-teal-500/10 border border-cyan-500/30 flex items-center justify-center shrink-0">
              <Bot className="w-4 h-4 text-cyan-400" />
            </div>
            <div className="max-w-[75%] rounded-lg px-4 py-3 msg-assistant">
              <ReactMarkdown remarkPlugins={[remarkGfm]} className="prose prose-sm max-w-none">
                {streamingContent}
              </ReactMarkdown>
              <span className="typing-cursor" />
            </div>
          </motion.div>
        )}

        {/* Loading indicator */}
        {isLoading && !isStreaming && messages.length > 0 && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500/20 to-teal-500/10 border border-cyan-500/30 flex items-center justify-center shrink-0">
              <Bot className="w-4 h-4 text-cyan-400" />
            </div>
            <div className="rounded-lg msg-assistant">
              <TypingIndicator />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* ===== INPUT BAR (Holographic) ===== */}
      <form onSubmit={handleSubmit} className="p-3 border-t border-cyan-500/20 bg-cyan-500/[0.02]">
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Enter command..."
            rows={1}
            className="flex-1 resize-none holo-input rounded-lg px-4 py-2.5 text-sm tracking-wider placeholder:text-cyan-300/25 custom-scrollbar"
            style={{ minHeight: 40, maxHeight: 120 }}
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="h-10 w-10 flex items-center justify-center rounded-lg holo-button disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          >
            <Send className="w-4 h-4 text-cyan-400 drop-shadow-[0_0_4px_rgba(0,212,255,0.4)]" />
          </button>
        </div>
      </form>
    </div>
  );
}
