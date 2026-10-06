'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Send, Mic, Paperclip, Brain, Zap, Sparkles, User,
  Shield, Network, Database, Terminal, Code2, FileSearch, Globe,
  Activity, Cpu, HardDrive, MemoryStick, MessageSquare,
  TrendingUp, Clock, ChevronDown, X
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useChatStore } from '@/stores/chat-store';
import { jarvisAPI } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import ParticleSystem from '@/components/supreme-ui/ParticleSystem';
import NeuralNetworkViz from '@/components/supreme-ui/NeuralNetworkViz';

const MODELS = [
  { id: 'local', name: 'Neural Core', desc: 'Ollama Local LLM', icon: Brain },
  { id: 'openai', name: 'GPT-4 Ultra', desc: 'OpenAI Advanced', icon: Zap },
  { id: 'gemini', name: 'Gemini Pro', desc: 'Google AI', icon: Sparkles },
];

const SUGGESTIONS = [
  { icon: Brain, label: 'Analyze Data', prompt: 'Analyze this data and provide insights:' },
  { icon: Code2, label: 'Write Code', prompt: 'Write production-ready code for:' },
  { icon: Sparkles, label: 'Creative', prompt: 'Help me create something amazing:' },
  { icon: Zap, label: 'Automate', prompt: 'Help me automate this task:' },
  { icon: Globe, label: 'Research', prompt: 'Research and summarize:' },
  { icon: Shield, label: 'Security Audit', prompt: 'Perform a security audit on:' },
];

const SYSTEM_STATS = [
  { icon: Cpu, label: 'CPU Usage', value: '23%', trend: 'down', color: '#10b981' },
  { icon: MemoryStick, label: 'Memory', value: '4.2 GB', trend: 'stable', color: '#3b82f6' },
  { icon: HardDrive, label: 'Models', value: '12', trend: 'up', color: '#a855f7' },
  { icon: Database, label: 'Knowledge', value: '2.4K', trend: 'up', color: '#f59e0b' },
];

const ACTIVITY_FEED = [
  { id: 1, type: 'info', message: 'Neural core initialized', time: '2s ago', icon: Brain },
  { id: 2, type: 'success', message: 'Knowledge base synced', time: '15s ago', icon: Database },
  { id: 3, type: 'warning', message: 'API rate limit at 80%', time: '1m ago', icon: Activity },
  { id: 4, type: 'success', message: 'Model cache refreshed', time: '2m ago', icon: Zap },
  { id: 5, type: 'info', message: 'New session started', time: '5m ago', icon: Globe },
  { id: 6, type: 'success', message: 'Security scan complete', time: '8m ago', icon: Shield },
  { id: 7, type: 'info', message: 'Agent pool expanded to 8', time: '12m ago', icon: Network },
  { id: 8, type: 'warning', message: 'Memory threshold approaching', time: '15m ago', icon: HardDrive },
];

const RECENT_CONVERSATIONS = [
  { id: 1, title: 'API Architecture Review', messages: 24, time: '2h ago' },
  { id: 2, title: 'Database Optimization', messages: 18, time: '5h ago' },
  { id: 3, title: 'Security Best Practices', messages: 32, time: '1d ago' },
  { id: 4, title: 'ML Model Training', messages: 45, time: '2d ago' },
];

export default function SupremePage() {
  const { messages, addMessage, setLoading } = useChatStore();
  const [input, setInput] = useState('');
  const [model, setModel] = useState('local');
  const [isLoading, setIsLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [showModelDropdown, setShowModelDropdown] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowModelDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const send = async (messageText?: string) => {
    const text = messageText || input;
    if (!text.trim() || isLoading) return;
    addMessage({ role: 'user', content: text.trim(), timestamp: new Date().toISOString() });
    const q = text.trim();
    setInput('');
    setShowSuggestions(false);
    setIsLoading(true);
    setLoading(true);
    if (taRef.current) taRef.current.style.height = '48px';
    try {
      const r = await jarvisAPI.chat(q, model);
      addMessage({
        role: 'assistant',
        content: r.response || r.message || 'No response.',
        timestamp: new Date().toISOString(),
        confidence: r.confidence,
        model: r.model,
      });
    } catch (e: any) {
      toast.error(e.message);
      addMessage({ role: 'assistant', content: 'Error: ' + e.message, timestamp: new Date().toISOString() });
    } finally {
      setIsLoading(false);
      setLoading(false);
    }
  };

  const selectedModel = MODELS.find((m) => m.id === model) || MODELS[0];

  return (
    <div className="relative flex h-screen overflow-hidden bg-[#0a0d12]">
      {/* Particle Background */}
      <ParticleSystem />

      {/* ===== LEFT PANEL ===== */}
      <motion.div
        initial={{ x: -300, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        className="relative z-10 hidden lg:flex w-1/4 min-w-[300px] max-w-[400px] flex-col border-r border-white/5"
        style={{ background: 'rgba(10, 13, 18, 0.85)', backdropFilter: 'blur(20px)' }}
      >
        {/* Neural Network Visualization */}
        <div className="flex-shrink-0 p-4 border-b border-white/5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <Brain size={16} className="text-cyan-400" />
              Neural Network
            </h2>
            <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-xs">
              Active
            </Badge>
          </div>
          <div className="rounded-xl overflow-hidden border border-white/10">
            <NeuralNetworkViz state="processing" className="w-full" />
          </div>
        </div>

        {/* System Status Cards */}
        <div className="flex-1 overflow-y-auto custom-scrollbar p-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">System Status</h3>
          <div className="grid grid-cols-2 gap-3 mb-6">
            {SYSTEM_STATS.map((stat) => {
              const Icon = stat.icon;
              return (
                <motion.div
                  key={stat.label}
                  whileHover={{ scale: 1.02, y: -2 }}
                  className="rounded-xl p-3 border border-white/5"
                  style={{ background: 'rgba(255,255,255,0.02)' }}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <Icon size={14} style={{ color: stat.color }} />
                    <span className="text-xs text-gray-400">{stat.label}</span>
                  </div>
                  <div className="flex items-end justify-between">
                    <span className="text-lg font-bold text-white">{stat.value}</span>
                    {stat.trend === 'up' && <TrendingUp size={12} className="text-emerald-400" />}
                    {stat.trend === 'down' && <TrendingUp size={12} className="text-emerald-400 rotate-180" />}
                    {stat.trend === 'stable' && <div className="w-2 h-2 rounded-full bg-blue-400" />}
                  </div>
                </motion.div>
              );
            })}
          </div>

          {/* Quick Actions */}
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Quick Actions</h3>
          <div className="space-y-2">
            {[
              { icon: Terminal, label: 'Open Terminal', color: '#ef4444' },
              { icon: FileSearch, label: 'Search Files', color: '#14b8a6' },
              { icon: Code2, label: 'Code Review', color: '#6366f1' },
              { icon: Activity, label: 'System Diagnostics', color: '#f59e0b' },
            ].map((action) => {
              const Icon = action.icon;
              return (
                <motion.button
                  key={action.label}
                  whileHover={{ x: 4, background: 'rgba(255,255,255,0.05)' }}
                  whileTap={{ scale: 0.98 }}
                  className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all"
                  style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}
                >
                  <div
                    className="flex items-center justify-center rounded-lg"
                    style={{ width: 32, height: 32, background: `${action.color}20` }}
                  >
                    <Icon size={16} style={{ color: action.color }} />
                  </div>
                  <span className="text-sm text-gray-300">{action.label}</span>
                </motion.button>
              );
            })}
          </div>
        </div>
      </motion.div>

      {/* ===== CENTER PANEL (Chat) ===== */}
      <div className="flex-1 flex flex-col relative z-10">
        {/* Header */}
        <motion.div
          initial={{ y: -50, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.4 }}
          className="flex-shrink-0 px-6 py-4 border-b border-white/5 flex items-center justify-between"
          style={{ background: 'rgba(15, 18, 24, 0.9)', backdropFilter: 'blur(12px)' }}
        >
          <div className="flex items-center gap-4">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl"
              style={{ background: 'linear-gradient(135deg, #3b82f6, #22d3ee)', boxShadow: '0 0 20px rgba(59,130,246,0.3)' }}>
              <Brain size={22} color="white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">JARVIS Neural Chat</h1>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-xs text-gray-400">Online • Ready to assist</span>
              </div>
            </div>
          </div>

          {/* Model Selector */}
          <div ref={dropdownRef} className="relative">
            <button
              onClick={() => setShowModelDropdown(!showModelDropdown)}
              className="flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 hover:bg-white/5 transition-all"
              style={{ background: 'rgba(255,255,255,0.02)' }}
            >
              {(() => { const M = selectedModel.icon; return <M size={16} color="#60a5fa" />; })()}
              <span className="text-sm text-white">{selectedModel.name}</span>
              <ChevronDown size={14} className="text-gray-400" />
            </button>
            <AnimatePresence>
              {showModelDropdown && (
                <motion.div
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="absolute right-0 top-full mt-2 w-56 rounded-xl border border-white/10 overflow-hidden shadow-2xl"
                  style={{ background: 'rgba(15, 18, 24, 0.95)', backdropFilter: 'blur(20px)' }}
                >
                  {MODELS.map((m) => {
                    const Ic = m.icon;
                    const isSelected = m.id === model;
                    return (
                      <button
                        key={m.id}
                        onClick={() => { setModel(m.id); setShowModelDropdown(false); }}
                        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/5 transition-all"
                      >
                        <Ic size={18} color={isSelected ? '#60a5fa' : '#6b7280'} />
                        <div className="text-left flex-1">
                          <div className={`text-sm font-medium ${isSelected ? 'text-blue-400' : 'text-white'}`}>{m.name}</div>
                          <div className="text-xs text-gray-500">{m.desc}</div>
                        </div>
                        {isSelected && <div className="w-2 h-2 rounded-full bg-blue-400" />}
                      </button>
                    );
                  })}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </motion.div>

        {/* Chat Messages Area */}
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 24px' }}>
            {/* Hero Section (shown when no messages) */}
            {messages.length === 0 && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="text-center mb-12"
              >
                <div className="inline-block relative mb-6">
                  <div
                    className="w-20 h-20 mx-auto rounded-2xl flex items-center justify-center"
                    style={{
                      background: 'linear-gradient(135deg, #3b82f6, #22d3ee, #3b82f6)',
                      boxShadow: '0 0 60px rgba(59,130,246,0.3)',
                    }}
                  >
                    <Brain size={40} color="white" />
                  </div>
                </div>
                <h1
                  className="text-4xl font-extrabold mb-4"
                  style={{
                    background: 'linear-gradient(to right, #60a5fa, #67e8f9, #60a5fa)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                  }}
                >
                  JARVIS Neural Interface
                </h1>
                <p className="text-gray-400 text-lg max-w-lg mx-auto mb-6">
                  Autonomous intelligence with self-healing, real-time learning, and enterprise-grade security.
                </p>
                <div className="flex flex-wrap justify-center gap-2 mb-8">
                  <Badge className="px-3 py-1 bg-blue-500/10 text-blue-400 border-blue-500/20">Phase 5</Badge>
                  <Badge className="px-3 py-1 bg-emerald-500/10 text-emerald-400 border-emerald-500/20">Self-Healing</Badge>
                  <Badge className="px-3 py-1 bg-purple-500/10 text-purple-400 border-purple-500/20">Multi-Modal</Badge>
                  <Badge className="px-3 py-1 bg-amber-500/10 text-amber-400 border-amber-500/20">OMEGA Core</Badge>
                </div>
              </motion.div>
            )}

            {/* Messages */}
            <AnimatePresence>
              {messages.map((msg, idx) => {
                const isUser = msg.role === 'user';
                return (
                  <motion.div
                    key={idx}
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3 }}
                    className="flex gap-4 mb-6"
                    style={{ flexDirection: isUser ? 'row-reverse' : 'row' }}
                  >
                    <div
                      className="flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center"
                      style={{
                        background: isUser
                          ? 'linear-gradient(135deg, #a855f7, #ec4899)'
                          : 'linear-gradient(135deg, #3b82f6, #06b6d4)',
                      }}
                    >
                      <User size={18} color="white" />
                    </div>
                    <div className="flex-1" style={{ maxWidth: '80%' }}>
                      <div className="flex items-center gap-2 mb-1" style={{ justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
                        <span className="text-sm font-semibold" style={{ color: isUser ? '#a855f7' : '#60a5fa' }}>
                          {isUser ? 'You' : 'JARVIS'}
                        </span>
                        {msg.model && (
                          <Badge className="h-4 px-1.5 text-[9px] bg-gray-800/50 text-gray-400 border-gray-700/50">
                            {msg.model}
                          </Badge>
                        )}
                      </div>
                      <div
                        className="rounded-2xl px-4 py-3"
                        style={{
                          background: isUser ? 'rgba(168,85,247,0.15)' : 'rgba(255,255,255,0.02)',
                          border: `1px solid ${isUser ? 'rgba(168,85,247,0.1)' : 'rgba(255,255,255,0.05)'}`,
                        }}
                      >
                        <p className="text-sm text-white whitespace-pre-wrap">{msg.content}</p>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>

            {/* Typing Indicator */}
            {isLoading && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex gap-4 mb-6"
              >
                <div
                  className="flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center"
                  style={{ background: 'linear-gradient(135deg, #3b82f6, #06b6d4)' }}
                >
                  <Brain size={18} color="white" />
                </div>
                <div className="flex items-center gap-1 px-4 py-3 rounded-2xl" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
                  {[0, 1, 2].map((i) => (
                    <div
                      key={i}
                      className="w-2 h-2 rounded-full bg-cyan-400 typing-dot"
                      style={{ animationDelay: `${i * 0.2}s` }}
                    />
                  ))}
                </div>
              </motion.div>
            )}

            <div ref={endRef} />
          </div>
        </div>

        {/* Input Bar */}
        <div className="flex-shrink-0 border-t border-white/5 px-6 py-4"
          style={{ background: 'rgba(15,18,24,0.9)', backdropFilter: 'blur(12px)' }}
        >
          <div style={{ maxWidth: 900, margin: '0 auto' }}>
            {/* Suggestions Chips */}
            <AnimatePresence>
              {showSuggestions && messages.length === 0 && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 8 }}
                  className="flex flex-wrap gap-2 mb-3"
                >
                  {SUGGESTIONS.map((s) => {
                    const Ic = s.icon;
                    return (
                      <motion.button
                        key={s.label}
                        whileHover={{ scale: 1.05, y: -2 }}
                        whileTap={{ scale: 0.95 }}
                        onClick={() => send(s.prompt)}
                        className="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm transition-all"
                        style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', color: '#9ca3af' }}
                      >
                        <Ic size={14} className="text-cyan-400" />
                        {s.label}
                      </motion.button>
                    );
                  })}
                </motion.div>
              )}
            </AnimatePresence>

            {/* Input Row */}
            <div className="flex items-end gap-2">
              <input type="file" ref={fileRef} className="hidden" multiple accept="image/*,.pdf,.txt" />
              <div className="flex-1 relative">
                <textarea
                  ref={taRef}
                  value={input}
                  onChange={(e) => {
                    setInput(e.target.value);
                    const t = e.target;
                    t.style.height = '48px';
                    t.style.height = Math.min(t.scrollHeight, 160) + 'px';
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      send();
                    }
                  }}
                  placeholder="Ask JARVIS anything..."
                  rows={1}
                  className="w-full text-white placeholder-gray-500 rounded-xl px-4 py-3 resize-none focus:outline-none focus:ring-1 focus:ring-blue-500/50"
                  style={{
                    background: 'rgba(18,22,32,1)',
                    border: '1px solid rgba(255,255,255,0.05)',
                    minHeight: 48,
                    maxHeight: 160,
                    fontSize: 14,
                  }}
                  disabled={isLoading}
                />
              </div>
              <Button
                size="icon"
                variant="ghost"
                className="flex-shrink-0 rounded-xl text-gray-400 hover:text-white"
                style={{ height: 44, width: 44, background: 'transparent' }}
                onClick={() => fileRef.current?.click()}
                disabled={isLoading}
              >
                <Paperclip size={20} />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="flex-shrink-0 rounded-xl"
                style={{
                  height: 44,
                  width: 44,
                  color: recording ? '#f87171' : '#9ca3af',
                  background: recording ? 'rgba(239,68,68,0.1)' : 'transparent',
                }}
                onClick={() => setRecording(!recording)}
                disabled={isLoading}
              >
                <Mic size={20} />
              </Button>
              <Button
                size="icon"
                className="flex-shrink-0 rounded-xl text-white"
                style={{
                  height: 44,
                  width: 44,
                  background: 'linear-gradient(to right, #3b82f6, #22d3ee)',
                  boxShadow: '0 0 20px rgba(59,130,246,0.2)',
                }}
                onClick={() => send()}
                disabled={isLoading || !input.trim()}
              >
                {isLoading ? (
                  <motion.span animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}>
                    ⟳
                  </motion.span>
                ) : (
                  <Send size={20} />
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* ===== RIGHT PANEL ===== */}
      <motion.div
        initial={{ x: 300, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.5, ease: 'easeOut', delay: 0.1 }}
        className="relative z-10 hidden lg:flex w-1/4 min-w-[280px] max-w-[360px] flex-col border-l border-white/5"
        style={{ background: 'rgba(10, 13, 18, 0.85)', backdropFilter: 'blur(20px)' }}
      >
        {/* Live Activity Feed */}
        <div className="flex-1 overflow-y-auto custom-scrollbar p-4 border-b border-white/5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <Activity size={16} className="text-cyan-400" />
              Live Activity
            </h3>
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-xs text-gray-500">Live</span>
            </div>
          </div>
          <div className="space-y-2">
            {ACTIVITY_FEED.map((item, idx) => {
              const Icon = item.icon;
              const colorMap: Record<string, string> = {
                info: '#3b82f6',
                success: '#10b981',
                warning: '#f59e0b',
              };
              const bgColorMap: Record<string, string> = {
                info: 'rgba(59,130,246,0.1)',
                success: 'rgba(16,185,129,0.1)',
                warning: 'rgba(245,158,11,0.1)',
              };
              return (
                <motion.div
                  key={item.id}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.05 }}
                  className="flex items-start gap-3 p-2.5 rounded-lg"
                  style={{ background: 'rgba(255,255,255,0.02)' }}
                >
                  <div
                    className="flex-shrink-0 w-7 h-7 rounded-md flex items-center justify-center"
                    style={{ background: bgColorMap[item.type] }}
                  >
                    <Icon size={14} style={{ color: colorMap[item.type] }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-gray-300 truncate">{item.message}</p>
                    <p className="text-[10px] text-gray-500 mt-0.5">{item.time}</p>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>

        {/* Smart Suggestions */}
        <div className="flex-shrink-0 p-4 border-b border-white/5">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
            <Sparkles size={16} className="text-amber-400" />
            Smart Suggestions
          </h3>
          <div className="space-y-2">
            {[
              { icon: Zap, text: 'Optimize database queries', priority: 'high' },
              { icon: Shield, text: 'Run security audit', priority: 'medium' },
              { icon: Brain, text: 'Review model performance', priority: 'low' },
            ].map((s) => {
              const Ic = s.icon;
              const priorityColors: Record<string, string> = {
                high: '#ef4444',
                medium: '#f59e0b',
                low: '#10b981',
              };
              return (
                <motion.button
                  key={s.text}
                  whileHover={{ x: 4, background: 'rgba(255,255,255,0.05)' }}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left transition-all"
                  style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}
                >
                  <Ic size={14} className="text-gray-400" />
                  <span className="text-xs text-gray-300 flex-1">{s.text}</span>
                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: priorityColors[s.priority] }} />
                </motion.button>
              );
            })}
          </div>
        </div>

        {/* Recent Conversations */}
        <div className="flex-shrink-0 p-4">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
            <MessageSquare size={16} className="text-purple-400" />
            Recent Conversations
          </h3>
          <div className="space-y-2">
            {RECENT_CONVERSATIONS.map((conv) => (
              <motion.button
                key={conv.id}
                whileHover={{ background: 'rgba(255,255,255,0.05)' }}
                className="w-full px-3 py-2.5 rounded-lg text-left transition-all"
                style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-white font-medium truncate">{conv.title}</span>
                  <span className="text-[10px] text-gray-500 flex-shrink-0 ml-2">{conv.time}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Clock size={10} className="text-gray-500" />
                  <span className="text-[10px] text-gray-500">{conv.messages} messages</span>
                </div>
              </motion.button>
            ))}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
