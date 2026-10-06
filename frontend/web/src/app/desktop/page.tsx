'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { Desktop } from '@/components/desktop/Desktop';

export default function DesktopPage() {
  const [view, setView] = useState<'desktop' | 'chat'>('desktop');

  return (
    <div className="relative w-full h-screen overflow-hidden bg-[#0a0d12]">
      {/* View Toggle */}
      <div className="fixed top-4 right-4 z-[9999] flex items-center gap-2 bg-black/50 backdrop-blur-xl rounded-xl border border-white/10 p-1">
        <button
          onClick={() => setView('desktop')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            view === 'desktop'
              ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
              : 'text-gray-400 hover:text-white hover:bg-white/5'
          }`}
        >
          🖥️ Desktop
        </button>
        <button
          onClick={() => setView('chat')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            view === 'chat'
              ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
              : 'text-gray-400 hover:text-white hover:bg-white/5'
          }`}
        >
          💬 Chat
        </button>
      </div>

      {/* Desktop View */}
      {view === 'desktop' && <Desktop />}

      {/* Chat View */}
      {view === 'chat' && (
        <div className="flex items-center justify-center h-full pt-16 text-gray-400">
          <p>Use the main Neural Chat at /dashboard</p>
        </div>
      )}
    </div>
  );
}
