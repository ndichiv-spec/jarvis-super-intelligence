'use client';

import React, { useState, useRef, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  Globe,
  ArrowLeft,
  ArrowRight,
  RefreshCw,
  Home,
  Plus,
  X,
  Star,
  Shield,
  Lock,
  Search,
} from 'lucide-react';

interface Tab {
  id: string;
  url: string;
  title: string;
  isLoading: boolean;
}

const HOME_URL = 'https://www.google.com/webhp?igu=1';
const BOOKMARKS = [
  { title: 'Google', url: 'https://www.google.com/webhp?igu=1', icon: 'G' },
  { title: 'Wikipedia', url: 'https://www.wikipedia.org', icon: 'W' },
  { title: 'GitHub', url: 'https://github.com', icon: 'GH' },
  { title: 'Stack Overflow', url: 'https://stackoverflow.com', icon: 'SO' },
];

export default function BrowserApp() {
  const [tabs, setTabs] = useState<Tab[]>([
    { id: '1', url: HOME_URL, title: 'New Tab', isLoading: false },
  ]);
  const [activeTabId, setActiveTabId] = useState('1');
  const [urlInput, setUrlInput] = useState(HOME_URL);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const activeTab = tabs.find((t) => t.id === activeTabId);

  const navigateTo = useCallback(
    (url: string) => {
      let normalizedUrl = url;
      if (!url.startsWith('http://') && !url.startsWith('https://')) {
        normalizedUrl = `https://${url}`;
      }

      setTabs((prev) =>
        prev.map((t) =>
          t.id === activeTabId ? { ...t, url: normalizedUrl, title: normalizedUrl, isLoading: true } : t
        )
      );
      setUrlInput(normalizedUrl);

      // Simulate loading
      setTimeout(() => {
        setTabs((prev) =>
          prev.map((t) => (t.id === activeTabId ? { ...t, isLoading: false } : t))
        );
      }, 1000);
    },
    [activeTabId]
  );

  const handleUrlSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (urlInput.trim()) {
      navigateTo(urlInput.trim());
    }
  };

  const addTab = () => {
    const newTab: Tab = {
      id: Date.now().toString(),
      url: HOME_URL,
      title: 'New Tab',
      isLoading: false,
    };
    setTabs((prev) => [...prev, newTab]);
    setActiveTabId(newTab.id);
    setUrlInput(HOME_URL);
  };

  const closeTab = (tabId: string) => {
    setTabs((prev) => {
      const filtered = prev.filter((t) => t.id !== tabId);
      if (filtered.length === 0) {
        // Always keep at least one tab
        const newTab: Tab = {
          id: Date.now().toString(),
          url: HOME_URL,
          title: 'New Tab',
          isLoading: false,
        };
        setActiveTabId(newTab.id);
        setUrlInput(HOME_URL);
        return [newTab];
      }
      if (activeTabId === tabId) {
        setActiveTabId(filtered[filtered.length - 1].id);
        setUrlInput(filtered[filtered.length - 1].url);
      }
      return filtered;
    });
  };

  const refresh = () => {
    if (iframeRef.current) {
      iframeRef.current.src = iframeRef.current.src;
    }
  };

  const goBack = () => {
    if (iframeRef.current) {
      try {
        iframeRef.current.contentWindow?.history.back();
      } catch {
        // Cross-origin restriction
      }
    }
  };

  const goForward = () => {
    if (iframeRef.current) {
      try {
        iframeRef.current.contentWindow?.history.forward();
      } catch {
        // Cross-origin restriction
      }
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Tab Bar */}
      <div className="flex items-end gap-0.5 px-2 pt-2 bg-[#0d1117] border-b border-border/30">
        {tabs.map((tab) => (
          <motion.div
            key={tab.id}
            className={`group flex items-center gap-2 h-8 px-3 rounded-t-lg cursor-pointer transition-all min-w-0 max-w-[200px] ${
              tab.id === activeTabId
                ? 'bg-card/80 text-foreground/80 border-t-2 border-primary'
                : 'bg-white/[0.02] text-foreground/40 hover:bg-white/5 hover:text-foreground/60'
            }`}
            onClick={() => {
              setActiveTabId(tab.id);
              setUrlInput(tab.url);
            }}
            whileHover={{ scale: 1.01 }}
          >
            <Globe className="w-3.5 h-3.5 shrink-0" />
            <span className="text-xs truncate flex-1">{tab.title}</span>
            {tab.isLoading && (
              <RefreshCw className="w-3 h-3 animate-spin shrink-0" />
            )}
            <button
              onClick={(e) => {
                e.stopPropagation();
                closeTab(tab.id);
              }}
              className="w-4 h-4 flex items-center justify-center rounded hover:bg-white/10 text-foreground/30 hover:text-foreground/60 opacity-0 group-hover:opacity-100 transition-all shrink-0"
            >
              <X className="w-3 h-3" />
            </button>
          </motion.div>
        ))}

        <button
          onClick={addTab}
          className="h-8 w-8 flex items-center justify-center rounded-t-lg hover:bg-white/5 text-foreground/30 hover:text-foreground/60 transition-colors shrink-0"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>

      {/* Navigation Bar */}
      <div className="flex items-center gap-1.5 px-3 py-2 bg-card/50 border-b border-border/30">
        <button
          onClick={goBack}
          className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <button
          onClick={goForward}
          className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground transition-colors"
        >
          <ArrowRight className="w-4 h-4" />
        </button>
        <button
          onClick={refresh}
          className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
        <button
          onClick={() => navigateTo(HOME_URL)}
          className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground transition-colors"
        >
          <Home className="w-4 h-4" />
        </button>

        {/* URL Bar */}
        <form onSubmit={handleUrlSubmit} className="flex-1 flex items-center">
          <div className="flex-1 flex items-center h-9 bg-white/5 border border-border/50 rounded-xl px-3 focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/20 transition-all">
            <Lock className="w-3.5 h-3.5 text-emerald-400 mr-2 shrink-0" />
            <input
              type="text"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-foreground/30"
              placeholder="Search or enter URL..."
            />
            {activeTab?.isLoading && (
              <RefreshCw className="w-3.5 h-3.5 text-primary animate-spin ml-2 shrink-0" />
            )}
          </div>
        </form>

        <button className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground transition-colors">
          <Star className="w-4 h-4" />
        </button>
      </div>

      {/* Bookmarks Bar */}
      <div className="flex items-center gap-1 px-3 py-1 bg-card/30 border-b border-border/20">
        {BOOKMARKS.map((bookmark) => (
          <button
            key={bookmark.url}
            onClick={() => navigateTo(bookmark.url)}
            className="flex items-center gap-1.5 h-6 px-2 rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground/70 transition-colors text-xs"
          >
            <div className="w-4 h-4 rounded bg-primary/20 flex items-center justify-center text-[8px] font-bold text-primary">
              {bookmark.icon}
            </div>
            <span>{bookmark.title}</span>
          </button>
        ))}
      </div>

      {/* iframe Content */}
      <div className="flex-1 relative bg-white">
        <iframe
          ref={iframeRef}
          src={activeTab?.url || HOME_URL}
          className="w-full h-full border-0"
          sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
          title="Browser"
        />

        {/* Loading overlay */}
        {activeTab?.isLoading && (
          <div className="absolute inset-0 bg-card/50 backdrop-blur-sm flex items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <RefreshCw className="w-8 h-8 text-primary animate-spin" />
              <span className="text-sm text-foreground/60">Loading page...</span>
            </div>
          </div>
        )}
      </div>

      {/* Status Bar */}
      <div className="flex items-center justify-between px-3 py-1 bg-card/30 border-t border-border/30 text-[10px] text-foreground/40">
        <div className="flex items-center gap-2">
          <Shield className="w-3 h-3 text-emerald-400" />
          <span>Secure connection</span>
        </div>
        <span>{activeTab?.url}</span>
      </div>
    </div>
  );
}
