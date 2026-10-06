'use client';

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
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
  Brain,
  Cpu,
  Zap,
  Sparkles,
  Monitor,
  Settings,
  Play,
  Pause,
  ChevronRight,
  Activity,
  Network,
  Code,
  Bot,
  Terminal,
  Eye,
  EyeOff,
  Maximize2,
  Minimize2,
} from 'lucide-react';

interface BrowserConfig {
  id: string;
  name: string;
  icon: React.ElementType;
  color: string;
  aiAssistant: {
    name: string;
    model: string;
    capabilities: string[];
    description: string;
    icon: React.ElementType;
    color: string;
  };
  features: string[];
  homeUrl: string;
  privacy: 'standard' | 'enhanced' | 'maximum';
  performance: 'basic' | 'standard' | 'enhanced';
}

interface Tab {
  id: string;
  url: string;
  title: string;
  isLoading: boolean;
  browserId: string;
}

const BROWSER_CONFIGS: BrowserConfig[] = [
  {
    id: 'jarvis-chrome',
    name: 'JARVIS Chrome',
    icon: Globe,
    color: 'bg-blue-500',
    aiAssistant: {
      name: 'Gemini Pro',
      model: 'google-gemini',
      capabilities: ['Web Search', 'Content Analysis', 'Code Generation', 'Real-time Translation'],
      description: 'Advanced AI assistant with Google integration',
      icon: Brain,
      color: 'text-blue-400'
    },
    features: ['AI-Powered Search', 'Smart Content Analysis', 'Code Assistant', 'Auto-Translation'],
    homeUrl: 'https://www.google.com/webhp?igu=1',
    privacy: 'standard',
    performance: 'enhanced'
  },
  {
    id: 'jarvis-edge',
    name: 'JARVIS Edge',
    icon: Monitor,
    color: 'bg-purple-500',
    aiAssistant: {
      name: 'GPT-4',
      model: 'openai-gpt4',
      capabilities: ['Advanced Reasoning', 'Code Completion', 'Document Analysis', 'Creative Writing'],
      description: 'OpenAI GPT-4 with enhanced reasoning capabilities',
      icon: Cpu,
      color: 'text-purple-400'
    },
    features: ['Advanced Reasoning', 'Code Completion', 'Document Analysis', 'Creative Writing'],
    homeUrl: 'https://www.bing.com',
    privacy: 'enhanced',
    performance: 'standard'
  },
  {
    id: 'jarvis-firefox',
    name: 'JARVIS Firefox',
    icon: Sparkles,
    color: 'bg-orange-500',
    aiAssistant: {
      name: 'Claude',
      model: 'anthropic-claude',
      capabilities: ['Privacy Protection', 'Secure Browsing', 'Content Filtering', 'Anti-Tracking'],
      description: 'Privacy-focused AI assistant with security features',
      icon: Shield,
      color: 'text-orange-400'
    },
    features: ['Privacy Protection', 'Secure Browsing', 'Content Filtering', 'Anti-Tracking'],
    homeUrl: 'https://www.mozilla.org',
    privacy: 'maximum',
    performance: 'standard'
  },
  {
    id: 'jarvis-safari',
    name: 'JARVIS Safari',
    icon: Terminal,
    color: 'bg-gray-600',
    aiAssistant: {
      name: 'Llama 3',
      model: 'meta-llama',
      capabilities: ['Fast Processing', 'Local AI', 'Privacy First', 'Lightweight'],
      description: 'Local AI assistant with fast processing',
      icon: Zap,
      color: 'text-gray-400'
    },
    features: ['Fast Processing', 'Local AI', 'Privacy First', 'Lightweight'],
    homeUrl: 'https://www.apple.com',
    privacy: 'maximum',
    performance: 'basic'
  },
  {
    id: 'jarvis-tor',
    name: 'JARVIS Tor',
    icon: EyeOff,
    color: 'bg-red-600',
    aiAssistant: {
      name: 'Stealth AI',
      model: 'custom-stealth',
      capabilities: ['Anonymous Browsing', 'Anti-Surveillance', 'Secure Communications', 'Privacy Shield'],
      description: 'Anonymous AI assistant for secure browsing',
      icon: EyeOff,
      color: 'text-red-400'
    },
    features: ['Anonymous Browsing', 'Anti-Surveillance', 'Secure Communications', 'Privacy Shield'],
    homeUrl: 'https://check.torproject.org',
    privacy: 'maximum',
    performance: 'basic'
  },
  {
    id: 'jarvis-quantum',
    name: 'JARVIS Quantum',
    icon: Network,
    color: 'bg-cyan-500',
    aiAssistant: {
      name: 'Quantum AI',
      model: 'quantum-neural',
      capabilities: ['Quantum Computing', 'Advanced Analytics', 'Future Tech', 'Research Mode'],
      description: 'Experimental quantum AI for advanced research',
      icon: Activity,
      color: 'text-cyan-400'
    },
    features: ['Quantum Computing', 'Advanced Analytics', 'Future Tech', 'Research Mode'],
    homeUrl: 'https://www.quantum-computing.ibm.com',
    privacy: 'enhanced',
    performance: 'enhanced'
  }
];

interface BrowserAppProps {
  appId: string;
  onClose: () => void;
  onMinimize: () => void;
  onMaximize: () => void;
}

export default function EnhancedBrowserApp({ appId, onClose, onMinimize, onMaximize }: BrowserAppProps) {
  const [selectedBrowser, setSelectedBrowser] = useState<BrowserConfig>(BROWSER_CONFIGS[0]);
  const [showBrowserSelection, setShowBrowserSelection] = useState(false);
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string>('');
  const [urlInput, setUrlInput] = useState('');
  const [showAIAssistant, setShowAIAssistant] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const activeTab = tabs.find((t) => t.id === activeTabId);

  const createNewTab = useCallback((browserId: string) => {
    const browser = BROWSER_CONFIGS.find(b => b.id === browserId);
    const newTab: Tab = {
      id: `${browserId}_${Date.now()}`,
      url: browser?.homeUrl || 'https://www.google.com',
      title: `New Tab - ${browser?.name}`,
      isLoading: false,
      browserId
    };
    
    setTabs(prev => [...prev, newTab]);
    setActiveTabId(newTab.id);
    setUrlInput(newTab.url);
  }, []);

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

  const closeTab = (tabId: string) => {
    setTabs((prev) => {
      const filtered = prev.filter((t) => t.id !== tabId);
      if (filtered.length === 0) {
        // Always keep at least one tab
        const browser = BROWSER_CONFIGS[0];
        const newTab: Tab = {
          id: `${browser.id}_${Date.now()}`,
          url: browser.homeUrl,
          title: `New Tab - ${browser.name}`,
          isLoading: false,
          browserId: browser.id
        };
        setActiveTabId(newTab.id);
        setUrlInput(newTab.url);
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

  const switchBrowser = (browser: BrowserConfig) => {
    setSelectedBrowser(browser);
    createNewTab(browser.id);
    setShowBrowserSelection(false);
  };

  // Initialize with first browser tab
  useEffect(() => {
    if (tabs.length === 0) {
      createNewTab(BROWSER_CONFIGS[0].id);
    }
  }, [tabs.length, createNewTab]);

  const currentBrowserConfig = BROWSER_CONFIGS.find(b => b.id === selectedBrowser.id);

  return (
    <div className="flex flex-col h-full bg-gray-900 text-white">
      {/* Browser Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-700">
        <div className="flex items-center space-x-3">
          <div className={`w-10 h-10 rounded-lg ${selectedBrowser.color} flex items-center justify-center`}>
            <selectedBrowser.icon className="w-6 h-6 text-white" />
          </div>
          <div>
            <h2 className="text-lg font-semibold">{selectedBrowser.name}</h2>
            <div className="flex items-center space-x-2">
              <selectedBrowser.aiAssistant.icon className={`w-4 h-4 ${selectedBrowser.aiAssistant.color}`} />
              <span className="text-sm text-gray-400">{selectedBrowser.aiAssistant.name}</span>
              <Badge variant="outline" className="text-xs">
                {selectedBrowser.privacy}
              </Badge>
            </div>
          </div>
        </div>
        
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setShowBrowserSelection(!showBrowserSelection)}
            className="px-3 py-2 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors flex items-center space-x-2"
          >
            <Globe className="w-4 h-4" />
            <span className="text-sm">Switch Browser</span>
            <ChevronRight className="w-4 h-4" />
          </button>
          
          <button
            onClick={() => setShowAIAssistant(!showAIAssistant)}
            className="px-3 py-2 bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2"
          >
            <Brain className="w-4 h-4" />
            <span className="text-sm">AI Assistant</span>
          </button>
          
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-2 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors"
          >
            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
          
          <button className="p-2 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors" onClick={onMinimize}>
            <Pause className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Browser Selection Panel */}
      <AnimatePresence>
        {showBrowserSelection && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="border-b border-gray-700 bg-gray-800"
          >
            <div className="p-4">
              <h3 className="text-lg font-semibold mb-4">Select Browser</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                {BROWSER_CONFIGS.map((browser) => (
                  <motion.button
                    key={browser.id}
                    onClick={() => switchBrowser(browser)}
                    className={`p-4 rounded-lg border transition-all ${
                      selectedBrowser.id === browser.id
                        ? 'border-blue-500 bg-blue-500/10'
                        : 'border-gray-600 hover:border-gray-500 hover:bg-gray-700'
                    }`}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    <div className="flex items-center space-x-3 mb-3">
                      <div className={`w-8 h-8 rounded ${browser.color} flex items-center justify-center`}>
                        <browser.icon className="w-4 h-4 text-white" />
                      </div>
                      <div className="text-left">
                        <h4 className="font-medium">{browser.name}</h4>
                        <div className="flex items-center space-x-1">
                          <browser.aiAssistant.icon className={`w-3 h-3 ${browser.aiAssistant.color}`} />
                          <span className="text-xs text-gray-400">{browser.aiAssistant.name}</span>
                        </div>
                      </div>
                    </div>
                    
                    <div className="text-left space-y-2">
                      <div className="flex flex-wrap gap-1">
                        {browser.features.slice(0, 2).map((feature, index) => (
                          <span key={index} className="text-xs bg-gray-700 px-2 py-1 rounded">
                            {feature}
                          </span>
                        ))}
                        {browser.features.length > 2 && (
                          <span className="text-xs text-gray-500">+{browser.features.length - 2} more</span>
                        )}
                      </div>
                      
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-gray-400">Privacy: {browser.privacy}</span>
                        <span className="text-gray-400">Performance: {browser.performance}</span>
                      </div>
                    </div>
                  </motion.button>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* AI Assistant Panel */}
      <AnimatePresence>
        {showAIAssistant && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="border-b border-gray-700 bg-gray-800"
          >
            <div className="p-4">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-3">
                  <div className={`w-8 h-8 rounded ${selectedBrowser.color} flex items-center justify-center`}>
                    <selectedBrowser.aiAssistant.icon className={`w-4 h-4 text-white`} />
                  </div>
                  <div>
                    <h3 className="font-semibold">{selectedBrowser.aiAssistant.name}</h3>
                    <p className="text-sm text-gray-400">{selectedBrowser.aiAssistant.description}</p>
                  </div>
                </div>
                
                <div className="flex items-center space-x-2">
                  <Badge variant="outline" className="text-xs">
                    {selectedBrowser.aiAssistant.model}
                  </Badge>
                  <button
                    onClick={() => setShowAIAssistant(false)}
                    className="p-1 hover:bg-gray-700 rounded"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
              
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {selectedBrowser.aiAssistant.capabilities.map((capability, index) => (
                  <div key={index} className="flex items-center space-x-2 p-2 bg-gray-700 rounded-lg">
                    <Sparkles className="w-3 h-3 text-blue-400" />
                    <span className="text-sm">{capability}</span>
                  </div>
                ))}
              </div>
              
              <div className="mt-4">
                <div className="bg-gray-700 rounded-lg p-3">
                  <div className="flex items-center space-x-2 mb-2">
                    <Activity className="w-4 h-4 text-green-400" />
                    <span className="text-sm font-medium">AI Status: Active</span>
                  </div>
                  <p className="text-xs text-gray-400">
                    AI assistant is ready to help with browsing, research, and content analysis.
                  </p>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Tab Bar */}
      <div className="flex items-end gap-0.5 px-2 pt-2 bg-[#0d1117] border-b border-border/30">
        {tabs.map((tab) => {
          const tabBrowser = BROWSER_CONFIGS.find(b => b.id === tab.browserId);
          return (
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
                setSelectedBrowser(tabBrowser || BROWSER_CONFIGS[0]);
              }}
              whileHover={{ scale: 1.01 }}
            >
              {tabBrowser?.icon ? <tabBrowser.icon className="w-3.5 h-3.5 shrink-0" /> : <Globe className="w-3.5 h-3.5 shrink-0" />}
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
          );
        })}

        <button
          onClick={() => createNewTab(selectedBrowser.id)}
          className="h-8 w-8 flex items-center justify-center rounded-t-lg hover:bg-white/5 text-foreground/30 hover:text-foreground/60 transition-colors shrink-0"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>

      {/* Navigation Bar */}
      <div className="flex items-center gap-1.5 px-3 py-2 bg-card/50 border-b border-border/30">
        <button
          onClick={() => navigateTo(currentBrowserConfig?.homeUrl || 'https://www.google.com')}
          className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground transition-colors"
        >
          <Home className="w-4 h-4" />
        </button>

        {/* URL Bar */}
        <form onSubmit={handleUrlSubmit} className="flex-1 flex items-center">
          <div className="flex-1 flex items-center h-9 bg-white/5 border border-border/50 rounded-xl px-3 focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/20 transition-all">
            <div className={`w-3.5 h-3.5 rounded ${selectedBrowser.color} mr-2 shrink-0`} />
            <Lock className="w-3.5 h-3.5 text-emerald-400 mr-2 shrink-0" />
            <input
              type="text"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-foreground/30"
              placeholder={`Search or enter URL in ${selectedBrowser.name}...`}
            />
            {activeTab?.isLoading && (
              <RefreshCw className="w-3.5 h-3.5 text-primary animate-spin ml-2 shrink-0" />
            )}
          </div>
        </form>

        <button
          onClick={refresh}
          className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
        
        <button className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground transition-colors">
          <Star className="w-4 h-4" />
        </button>
      </div>

      {/* Browser Content */}
      <div className="flex-1 relative bg-white">
        <iframe
          ref={iframeRef}
          src={activeTab?.url || currentBrowserConfig?.homeUrl}
          className="w-full h-full border-0"
          sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
          title={`${selectedBrowser.name} Browser`}
        />

        {/* Loading overlay */}
        {activeTab?.isLoading && (
          <div className="absolute inset-0 bg-card/50 backdrop-blur-sm flex items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <RefreshCw className="w-8 h-8 text-primary animate-spin" />
              <span className="text-sm text-foreground/60">Loading {selectedBrowser.name}...</span>
            </div>
          </div>
        )}

        {/* AI Assistant Indicator */}
        {!showAIAssistant && (
          <div className="absolute top-4 right-4">
            <button
              onClick={() => setShowAIAssistant(true)}
              className="p-2 bg-blue-600 rounded-full hover:bg-blue-700 transition-colors shadow-lg"
            >
              <selectedBrowser.aiAssistant.icon className="w-4 h-4 text-white" />
            </button>
          </div>
        )}
      </div>

      {/* Status Bar */}
      <div className="flex items-center justify-between px-3 py-1 bg-card/30 border-t border-border/30 text-[10px] text-foreground/40">
        <div className="flex items-center gap-2">
          <Shield className="w-3 h-3 text-emerald-400" />
          <span>{selectedBrowser.name} - Secure connection</span>
        </div>
        <div className="flex items-center gap-4">
          <span>{selectedBrowser.aiAssistant.name}</span>
          <span>{activeTab?.url}</span>
        </div>
      </div>
    </div>
  );
}

// Helper Badge component
interface BadgeProps {
  variant?: string;
  className?: string;
  children: React.ReactNode;
}

const Badge = ({ variant, className, children }: BadgeProps) => (
  <span className={`px-2 py-1 rounded text-xs ${className}`}>
    {children}
  </span>
);
