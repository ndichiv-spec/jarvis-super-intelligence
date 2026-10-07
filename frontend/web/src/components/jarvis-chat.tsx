'use client';

import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, MessageSquare, User, Bot, Trash2, Plus, Settings } from 'lucide-react';
import { getApiUrl } from '@/lib/runtime-url';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  model?: string;
  skill_used?: string;
}

interface Session {
  session_id: string;
  preview: string;
  started: string;
}

export default function JarvisChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSession, setCurrentSession] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [activeModel, setActiveModel] = useState('claude');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadSessions();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadSessions = async () => {
    try {
      const response = await fetch(getApiUrl('/api/chat/sessions'), { credentials: 'include' });
      const data = await response.json();
      setSessions(data);
    } catch (error) {
      console.error('Failed to load sessions:', error);
    }
  };

  const loadSession = async (sessionId: string) => {
    try {
      const response = await fetch(getApiUrl(`/api/chat/history/${encodeURIComponent(sessionId)}`), {
        credentials: 'include',
      });
      const data = await response.json();
      setMessages(data.messages);
      setCurrentSession(sessionId);
    } catch (error) {
      console.error('Failed to load session:', error);
    }
  };

  const sendMessage = async (stream = false) => {
    if (!input.trim()) return;

    const userMessage = input;
    setInput('');
    setLoading(true);

    try {
      if (stream) {
        await sendStreamingMessage(userMessage);
      } else {
        await sendRegularMessage(userMessage);
      }
    } catch (error) {
      console.error('Failed to send message:', error);
    } finally {
      setLoading(false);
    }
  };

  const sendRegularMessage = async (message: string) => {
    const response = await fetch(getApiUrl('/api/chat'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        message,
        session_id: currentSession,
        stream: false
      })
    });

    const data = await response.json();
    setCurrentSession(data.session_id);
    
    setMessages(prev => [
      ...prev,
      { id: Date.now().toString(), role: 'user', content: message, created_at: new Date().toISOString() },
      { id: (Date.now() + 1).toString(), role: 'assistant', content: data.reply, created_at: new Date().toISOString(), model: data.model, skill_used: data.skill_used }
    ]);

    loadSessions();
  };

  const sendStreamingMessage = async (message: string) => {
    setStreaming(true);
    const response = await fetch(getApiUrl('/api/chat/stream'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        message,
        session_id: currentSession,
        stream: true
      })
    });

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let assistantMessage = '';

    setMessages(prev => [
      ...prev,
      { id: Date.now().toString(), role: 'user', content: message, created_at: new Date().toISOString() }
    ]);

    const assistantId = (Date.now() + 1).toString();
    setMessages(prev => [
      ...prev,
      { id: assistantId, role: 'assistant', content: '', created_at: new Date().toISOString() }
    ]);

    if (reader) {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6));
            
            if (data.type === 'meta' && data.session_id) {
              setCurrentSession(data.session_id);
            } else if (data.type === 'chunk') {
              assistantMessage += data.text;
              setMessages(prev => prev.map(msg => 
                msg.id === assistantId ? { ...msg, content: assistantMessage } : msg
              ));
            } else if (data.type === 'done') {
              setStreaming(false);
              loadSessions();
            }
          }
        }
      }
    }
  };

  const switchModel = async (model: string) => {
    try {
      const response = await fetch(getApiUrl('/api/chat/switch'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ model })
      });
      const data = await response.json();
      setActiveModel(data.active_model);
    } catch (error) {
      console.error('Failed to switch model:', error);
    }
  };

  const newSession = () => {
    setMessages([]);
    setCurrentSession(null);
  };

  const deleteSession = async (sessionId: string) => {
    try {
      await fetch(getApiUrl(`/api/chat/history/${encodeURIComponent(sessionId)}`), {
        method: 'DELETE',
        credentials: 'include',
      });
      if (currentSession === sessionId) {
        newSession();
      }
      loadSessions();
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  };

  return (
    <div className="flex h-screen bg-gray-900">
      {/* Sidebar */}
      <div className="w-64 bg-gray-800 p-4 flex flex-col">
        <button
          onClick={newSession}
          className="mb-4 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center"
        >
          <Plus className="mr-2 w-4 h-4" />
          New Chat
        </button>

        <div className="flex-1 overflow-y-auto">
          <h3 className="text-gray-400 text-sm mb-2">Sessions</h3>
          {sessions.map((session) => (
            <div
              key={session.session_id}
              className={`p-2 rounded mb-2 cursor-pointer ${
                currentSession === session.session_id ? 'bg-gray-700' : 'hover:bg-gray-700'
              }`}
              onClick={() => loadSession(session.session_id)}
            >
              <div className="text-white text-sm truncate">{session.preview}</div>
              <div className="text-gray-500 text-xs">{new Date(session.started).toLocaleDateString()}</div>
            </div>
          ))}
        </div>

        <div className="mt-4 pt-4 border-t border-gray-700">
          <h3 className="text-gray-400 text-sm mb-2">Model</h3>
          <select
            value={activeModel}
            onChange={(e) => switchModel(e.target.value)}
            className="w-full bg-gray-700 text-white px-3 py-2 rounded"
          >
            <option value="claude">Claude</option>
            <option value="openai">OpenAI</option>
            <option value="gemini">Gemini</option>
            <option value="ollama">Ollama</option>
          </select>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        <div className="flex-1 overflow-y-auto p-4">
          <AnimatePresence>
            {messages.map((message) => (
              <motion.div
                key={message.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className={`mb-4 ${message.role === 'user' ? 'text-right' : 'text-left'}`}
              >
                <div
                  className={`inline-block max-w-2xl p-4 rounded-lg ${
                    message.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-700 text-white'
                  }`}
                >
                  <div className="flex items-center mb-2">
                    {message.role === 'user' ? (
                      <User className="w-4 h-4 mr-2" />
                    ) : (
                      <Bot className="w-4 h-4 mr-2" />
                    )}
                    <span className="text-sm font-semibold">
                      {message.role === 'user' ? 'You' : 'JARVIS'}
                    </span>
                    {message.model && (
                      <span className="ml-2 text-xs bg-gray-600 px-2 py-1 rounded">
                        {message.model}
                      </span>
                    )}
                    {message.skill_used && (
                      <span className="ml-2 text-xs bg-purple-600 px-2 py-1 rounded">
                        {message.skill_used}
                      </span>
                    )}
                  </div>
                  <div className="whitespace-pre-wrap">{message.content}</div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
          {loading && (
            <div className="text-center text-gray-400">
              <div className="animate-spin inline-block w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full" />
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="p-4 bg-gray-800">
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && sendMessage(false)}
              placeholder="Type your message..."
              className="flex-1 bg-gray-700 text-white px-4 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
              disabled={loading}
            />
            <button
              onClick={() => sendMessage(false)}
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg disabled:opacity-50"
            >
              <Send className="w-5 h-5" />
            </button>
            <button
              onClick={() => sendMessage(true)}
              disabled={loading}
              className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg disabled:opacity-50"
            >
              Stream
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
