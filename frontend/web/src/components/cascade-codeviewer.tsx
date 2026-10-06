'use client';

import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Code, Copy, Check, Download, Maximize2, Minimize2, 
  Play, Pause, RefreshCw, Search, Settings, Terminal,
  FileCode, Zap, Sparkles, ChevronDown, ChevronUp,
  X, Eye, EyeOff, Layers, Grid, List, Monitor
} from 'lucide-react';

interface CodeViewerProps {
  code?: string;
  language?: string;
  filename?: string;
  readOnly?: boolean;
  theme?: 'dark' | 'light' | 'neon' | 'cyberpunk';
  autoRun?: boolean;
  showLineNumbers?: boolean;
  enableSyntaxHighlighting?: boolean;
}

const DEFAULT_CODE = `// JARVIS Cascade AI Code Viewer
// Limitless Code Execution & Visualization

import { JARVIS } from '@jarvis/core';

class CascadeAI {
  constructor() {
    this.capabilities = {
      swarmIntelligence: true,
      multimodalFusion: true,
      causalReasoning: true,
      quantumSimulation: true,
      neuroSymbolic: true
    };
    this.performance = {
      accuracy: 99.9,
      speed: 'quantum',
      scalability: 'infinite'
    };
  }

  async execute(code: string) {
    // Limitless code execution
    const result = await this.quantumProcess(code);
    return this.optimizeResult(result);
  }

  private async quantumProcess(code: string) {
    // Quantum processing pipeline
    return {
      status: 'success',
      data: code,
      timestamp: Date.now()
    };
  }

  private optimizeResult(result: any) {
    // Auto-optimization
    return {
      ...result,
      optimized: true,
      confidence: 1.0
    };
  }
}

// Initialize Cascade AI
const cascade = new CascadeAI();
console.log('Cascade AI initialized - Limitless capabilities ready');

export default cascade;`;

const THEMES = {
  dark: {
    bg: 'bg-gray-900',
    text: 'text-gray-100',
    accent: 'bg-blue-600',
    border: 'border-gray-700',
    code: 'bg-gray-800',
    lineNumbers: 'text-gray-500'
  },
  light: {
    bg: 'bg-gray-50',
    text: 'text-gray-900',
    accent: 'bg-blue-500',
    border: 'border-gray-300',
    code: 'bg-white',
    lineNumbers: 'text-gray-400'
  },
  neon: {
    bg: 'bg-black',
    text: 'text-green-400',
    accent: 'bg-green-600',
    border: 'border-green-500',
    code: 'bg-gray-900',
    lineNumbers: 'text-green-600'
  },
  cyberpunk: {
    bg: 'bg-purple-950',
    text: 'text-pink-400',
    accent: 'bg-pink-600',
    border: 'border-pink-500',
    code: 'bg-purple-900',
    lineNumbers: 'text-pink-600'
  }
};

export default function CascadeCodeViewer({
  code = DEFAULT_CODE,
  language = 'typescript',
  filename = 'cascade_ai.ts',
  readOnly = false,
  theme = 'dark',
  autoRun = false,
  showLineNumbers = true,
  enableSyntaxHighlighting = true
}: CodeViewerProps) {
  const [currentCode, setCurrentCode] = useState(code);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [output, setOutput] = useState<string>('');
  const [copied, setCopied] = useState(false);
  const [showOutput, setShowOutput] = useState(true);
  const [lineCount, setLineCount] = useState(0);
  const [selectedTheme, setSelectedTheme] = useState(theme);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<number[]>([]);
  const [currentSearchIndex, setCurrentSearchIndex] = useState(0);
  const codeRef = useRef<HTMLTextAreaElement>(null);
  const outputRef = useRef<HTMLDivElement>(null);

  const currentTheme = THEMES[selectedTheme];

  useEffect(() => {
    setLineCount(currentCode.split('\n').length);
  }, [currentCode]);

  useEffect(() => {
    if (autoRun && !isRunning) {
      handleRun();
    }
  }, [autoRun]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(currentCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([currentCode], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleRun = async () => {
    setIsRunning(true);
    setOutput('Executing code...\n');
    
    // Simulate code execution
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    try {
      // Limitless execution simulation
      const result = {
        status: 'success',
        executionTime: Math.random() * 100 + 'ms',
        output: 'Cascade AI execution complete',
        metrics: {
          operations: Math.floor(Math.random() * 1000000),
          memory: (Math.random() * 100).toFixed(2) + 'MB',
          quantumAdvantage: (Math.random() * 100).toFixed(1) + '%'
        }
      };
      
      setOutput(JSON.stringify(result, null, 2));
    } catch (error) {
      setOutput(`Error: ${error}`);
    }
    
    setIsRunning(false);
  };

  const handleSearch = () => {
    if (!searchQuery) {
      setSearchResults([]);
      return;
    }
    
    const lines = currentCode.split('\n');
    const results: number[] = [];
    
    lines.forEach((line, index) => {
      if (line.toLowerCase().includes(searchQuery.toLowerCase())) {
        results.push(index + 1);
      }
    });
    
    setSearchResults(results);
    setCurrentSearchIndex(0);
  };

  const highlightSyntax = (code: string) => {
    if (!enableSyntaxHighlighting) return code;
    
    // Escape HTML entities first to prevent script tag injection
    let escaped = code
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
    
    // Simple syntax highlighting on escaped code
    let highlighted = escaped
      .replace(/\/\/.*$/gm, '<span class="text-gray-500">$&</span>')
      .replace(/\/\*[\s\S]*?\*\//g, '<span class="text-gray-500">$&</span>')
      .replace(/\b(import|export|from|class|const|let|var|function|return|if|else|for|while|async|await|new|this|private|public|protected|static)\b/g, '<span class="text-purple-400">$1</span>')
      .replace(/\b(true|false|null|undefined)\b/g, '<span class="text-blue-400">$1</span>')
      .replace(/\b(\d+)\b/g, '<span class="text-green-400">$1</span>')
      .replace(/(['"`])(.*?)\1/g, '<span class="text-yellow-400">$1$2$1</span>');
    
    return highlighted;
  };

  const lines = currentCode.split('\n');

  return (
    <div className={`${currentTheme.bg} ${currentTheme.text} rounded-xl overflow-hidden shadow-2xl border ${currentTheme.border} ${isFullscreen ? 'fixed inset-0 z-50' : ''}`}>
      {/* Header */}
      <div className={`${currentTheme.code} p-4 border-b ${currentTheme.border}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="flex space-x-2">
              <div className="w-3 h-3 rounded-full bg-red-500"></div>
              <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
              <div className="w-3 h-3 rounded-full bg-green-500"></div>
            </div>
            <div className="flex items-center space-x-2">
              <FileCode className="w-4 h-4" />
              <span className="font-semibold">{filename}</span>
              <span className="text-xs px-2 py-1 rounded bg-gray-700">{language}</span>
            </div>
          </div>
          
          <div className="flex items-center space-x-2">
            {/* Theme Selector */}
            <select
              value={selectedTheme}
              onChange={(e) => setSelectedTheme(e.target.value as any)}
              className={`text-sm px-2 py-1 rounded ${currentTheme.code} border ${currentTheme.border}`}
            >
              <option value="dark">Dark</option>
              <option value="light">Light</option>
              <option value="neon">Neon</option>
              <option value="cyberpunk">Cyberpunk</option>
            </select>
            
            <button
              onClick={() => setShowOutput(!showOutput)}
              className={`p-2 rounded hover:bg-gray-700 transition-colors`}
              title="Toggle Output"
            >
              {showOutput ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
            </button>
            
            <button
              onClick={handleCopy}
              className={`p-2 rounded hover:bg-gray-700 transition-colors`}
              title="Copy Code"
            >
              {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
            </button>
            
            <button
              onClick={handleDownload}
              className={`p-2 rounded hover:bg-gray-700 transition-colors`}
              title="Download"
            >
              <Download className="w-4 h-4" />
            </button>
            
            <button
              onClick={() => setIsFullscreen(!isFullscreen)}
              className={`p-2 rounded hover:bg-gray-700 transition-colors`}
              title="Toggle Fullscreen"
            >
              {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>
          </div>
        </div>
        
        {/* Search Bar */}
        <div className="mt-3 flex items-center space-x-2">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search code..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
              className={`w-full pl-10 pr-4 py-2 rounded ${currentTheme.code} border ${currentTheme.border} text-sm focus:outline-none focus:ring-2 focus:ring-blue-500`}
            />
          </div>
          <button
            onClick={handleSearch}
            className={`px-3 py-2 rounded ${currentTheme.accent} text-white text-sm hover:opacity-90 transition-opacity`}
          >
            Search
          </button>
          {searchResults.length > 0 && (
            <span className="text-sm text-gray-400">
              {currentSearchIndex + 1} / {searchResults.length}
            </span>
          )}
        </div>
      </div>
      
      {/* Code Editor */}
      <div className="flex">
        {/* Line Numbers */}
        {showLineNumbers && (
          <div className={`${currentTheme.code} ${currentTheme.lineNumbers} text-right py-4 px-3 select-none text-sm font-mono border-r ${currentTheme.border}`}>
            {lines.map((_, index) => (
              <div
                key={index}
                className={`hover:bg-gray-700 cursor-pointer ${
                  searchResults.includes(index + 1) ? 'bg-yellow-600 text-white' : ''
                }`}
              >
                {index + 1}
              </div>
            ))}
          </div>
        )}
        
        {/* Code Area */}
        <div className="flex-1 relative">
          <textarea
            ref={codeRef}
            value={currentCode}
            onChange={(e) => setCurrentCode(e.target.value)}
            readOnly={readOnly}
            className={`w-full h-96 p-4 font-mono text-sm resize-none focus:outline-none ${currentTheme.code} ${currentTheme.text}`}
            style={{
              fontFamily: 'Fira Code, Consolas, Monaco, monospace',
              lineHeight: '1.6'
            }}
            spellCheck={false}
          />
          
          {/* Syntax Highlighted Overlay */}
          {enableSyntaxHighlighting && (
            <div
              className={`absolute top-0 left-0 w-full h-96 p-4 font-mono text-sm pointer-events-none ${currentTheme.code} ${currentTheme.text}`}
              style={{
                fontFamily: 'Fira Code, Consolas, Monaco, monospace',
                lineHeight: '1.6',
                whiteSpace: 'pre-wrap',
                wordWrap: 'break-word'
              }}
              dangerouslySetInnerHTML={{ __html: highlightSyntax(currentCode) }}
            />
          )}
        </div>
      </div>
      
      {/* Output Panel */}
      <AnimatePresence>
        {showOutput && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className={`${currentTheme.code} border-t ${currentTheme.border}`}
          >
            <div className="p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center space-x-2">
                  <Terminal className="w-4 h-4" />
                  <span className="font-semibold text-sm">Output</span>
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={handleRun}
                    disabled={isRunning}
                    className={`flex items-center space-x-1 px-3 py-1 rounded ${currentTheme.accent} text-white text-sm hover:opacity-90 transition-opacity disabled:opacity-50`}
                  >
                    {isRunning ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        <span>Running...</span>
                      </>
                    ) : (
                      <>
                        <Play className="w-4 h-4" />
                        <span>Run</span>
                      </>
                    )}
                  </button>
                  <button
                    onClick={() => setOutput('')}
                    className={`p-1 rounded hover:bg-gray-700 transition-colors`}
                    title="Clear Output"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
              
              <div
                ref={outputRef}
                className={`p-3 rounded ${currentTheme.bg} font-mono text-sm max-h-48 overflow-y-auto`}
              >
                <pre className="whitespace-pre-wrap">{output || 'No output yet. Click Run to execute code.'}</pre>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      
      {/* Status Bar */}
      <div className={`${currentTheme.code} border-t ${currentTheme.border} px-4 py-2 flex items-center justify-between text-xs text-gray-400`}>
        <div className="flex items-center space-x-4">
          <span>{lines.length} lines</span>
          <span>{currentCode.length} characters</span>
          <span>{language}</span>
        </div>
        <div className="flex items-center space-x-2">
          <Sparkles className="w-3 h-3 text-yellow-400" />
          <span>Cascade AI - Limitless</span>
        </div>
      </div>
    </div>
  );
}
