'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Terminal, ChevronRight, X, Trash2 } from 'lucide-react';

interface TerminalLine {
  id: string;
  type: 'input' | 'output' | 'error' | 'info';
  content: string;
  timestamp: Date;
}

const COMMANDS: Record<string, (args: string[]) => Promise<string>> = {
  help: async () => `Available commands:
  help          - Show this help message
  echo <text>   - Print text
  date          - Show current date/time
  whoami        - Show current user
  uname         - Show system information
  ls            - List files
  pwd           - Print working directory
  clear         - Clear terminal
  ping <host>   - Ping a host
  uptime        - Show system uptime
  ps            - List processes
  neofetch      - System info display
  calc <expr>   - Calculate expression`,

  date: async () => new Date().toString(),
  whoami: async () => 'jarvis-admin',
  pwd: async () => '/home/jarvis',
  uptime: async () => {
    const hours = Math.floor(Math.random() * 24) + 1;
    return `up ${hours} hours, ${Math.floor(Math.random() * 60)} minutes`;
  },
  uname: async () => 'JARVIS-OS 3.0.0 x86_64 JarvisAI/Ubuntu',

  ls: async () => `Documents/    Projects/     Images/
config.json   README.md     package.json
.env.example  .gitignore    Dockerfile`,

  ps: async () => `PID   NAME              CPU%   MEM%
1     jarvis-core       12.3   8.5
2     ai-engine       45.2   24.1
3     web-server      8.7    5.2
4     db-service      15.4   12.8
5     agent-runner    22.1   9.3`,

  neofetch: async () => `
   /\\        jarvis@jarvis-os
  /  \\       ─────────────────
 / /\\ \\      OS: JARVIS-OS 3.0 x86_64
/ /  \\ \\     Host: JARVIS AI Server
\\ \\  / /     Kernel: 6.1.0-jarvis
 \\ \\/ /      Uptime: 7 days, 14 hours
  \\  /       Shell: jarvis-terminal 2.0
   \\/        CPU: Neural Core @ 4.2GHz
              Memory: 12.4GB / 32GB
              GPU: CUDA RTX 4090`,
};

export default function TerminalApp() {
  const [lines, setLines] = useState<TerminalLine[]>([
    {
      id: 'welcome',
      type: 'info',
      content: 'Welcome to JARVIS Terminal v2.0. Type "help" for available commands.',
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [commandHistory, setCommandHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const terminalRef = useRef<HTMLDivElement>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const scrollToBottom = () => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [lines]);

  const executeCommand = useCallback(
    async (cmd: string) => {
      const trimmed = cmd.trim();
      if (!trimmed) return;

      setIsProcessing(true);
      setCommandHistory((prev) => [...prev, trimmed]);
      setHistoryIndex(-1);

      // Add input line
      const inputLine: TerminalLine = {
        id: Date.now().toString(),
        type: 'input',
        content: trimmed,
        timestamp: new Date(),
      };

      const parts = trimmed.split(/\s+/);
      const command = parts[0].toLowerCase();
      const args = parts.slice(1);

      let outputLine: TerminalLine;

      if (command === 'clear') {
        setLines([]);
        setIsProcessing(false);
        return;
      }

      if (command === 'echo') {
        outputLine = {
          id: (Date.now() + 1).toString(),
          type: 'output',
          content: args.join(' '),
          timestamp: new Date(),
        };
      } else if (command === 'calc') {
        try {
          const result = Function(`"use strict"; return (${args.join(' ')})`)();
          outputLine = {
            id: (Date.now() + 1).toString(),
            type: 'output',
            content: `= ${result}`,
            timestamp: new Date(),
          };
        } catch {
          outputLine = {
            id: (Date.now() + 1).toString(),
            type: 'error',
            content: 'Error: Invalid expression',
            timestamp: new Date(),
          };
        }
      } else if (command === 'ping') {
        const host = args[0] || 'localhost';
        outputLine = {
          id: (Date.now() + 1).toString(),
          type: 'output',
          content: `PING ${host}: 4 packets transmitted, 4 received, 0% loss\nrtt min/avg/max = 2.1/4.3/8.7 ms`,
          timestamp: new Date(),
        };
      } else if (COMMANDS[command]) {
        try {
          const result = await COMMANDS[command](args);
          outputLine = {
            id: (Date.now() + 1).toString(),
            type: 'output',
            content: result,
            timestamp: new Date(),
          };
        } catch {
          outputLine = {
            id: (Date.now() + 1).toString(),
            type: 'error',
            content: `Error executing command: ${command}`,
            timestamp: new Date(),
          };
        }
      } else {
        outputLine = {
          id: (Date.now() + 1).toString(),
          type: 'error',
          content: `command not found: ${command}. Type "help" for available commands.`,
          timestamp: new Date(),
        };
      }

      setLines((prev) => [...prev, inputLine, outputLine]);
      setIsProcessing(false);
    },
    []
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    executeCommand(input);
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (commandHistory.length > 0) {
        const newIndex = historyIndex === -1 ? commandHistory.length - 1 : Math.max(0, historyIndex - 1);
        setHistoryIndex(newIndex);
        setInput(commandHistory[newIndex]);
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIndex !== -1) {
        const newIndex = historyIndex + 1;
        if (newIndex >= commandHistory.length) {
          setHistoryIndex(-1);
          setInput('');
        } else {
          setHistoryIndex(newIndex);
          setInput(commandHistory[newIndex]);
        }
      }
    } else if (e.key === 'Tab') {
      e.preventDefault();
      // Simple tab completion
      const partial = input.toLowerCase();
      const match = Object.keys(COMMANDS).find((cmd) => cmd.startsWith(partial));
      if (match) {
        setInput(match);
      }
    }
  };

  const clearTerminal = () => {
    setLines([]);
  };

  return (
    <div className="flex flex-col h-full bg-[#0a0e14]">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/30 bg-[#0d1117]">
        <div className="flex items-center gap-2">
          <Terminal className="w-3.5 h-3.5 text-emerald-400" />
          <span className="text-xs text-foreground/60 font-mono">jarvis-terminal</span>
        </div>
        <button
          onClick={clearTerminal}
          className="flex items-center gap-1 text-[10px] text-foreground/40 hover:text-foreground/60 px-2 py-0.5 rounded hover:bg-white/5 transition-colors"
        >
          <Trash2 className="w-3 h-3" />
          Clear
        </button>
      </div>

      {/* Terminal Content */}
      <div
        ref={terminalRef}
        className="flex-1 overflow-y-auto p-3 font-mono text-sm custom-scrollbar"
        onClick={() => inputRef.current?.focus()}
      >
        <AnimatePresence>
          {lines.map((line) => (
            <motion.div
              key={line.id}
              initial={{ opacity: 0, x: -5 }}
              animate={{ opacity: 1, x: 0 }}
              className="mb-1"
            >
              {line.type === 'input' && (
                <div className="flex items-start gap-2">
                  <span className="text-emerald-400 shrink-0">
                    <ChevronRight className="w-4 h-4" />
                  </span>
                  <span className="text-cyan-400">jarvis@jarvis</span>
                  <span className="text-foreground/40">:</span>
                  <span className="text-blue-400">~</span>
                  <span className="text-foreground/40">$</span>
                  <span className="text-foreground">{line.content}</span>
                </div>
              )}
              {line.type === 'output' && (
                <pre className="text-foreground/80 whitespace-pre-wrap pl-6">{line.content}</pre>
              )}
              {line.type === 'error' && (
                <pre className="text-red-400 whitespace-pre-wrap pl-6">{line.content}</pre>
              )}
              {line.type === 'info' && (
                <div className="text-amber-400/80 pl-6">{line.content}</div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Input Line */}
        <form onSubmit={handleSubmit} className="flex items-center gap-2 mt-1">
          <span className="text-emerald-400 shrink-0">
            <ChevronRight className="w-4 h-4" />
          </span>
          <span className="text-cyan-400">jarvis@jarvis</span>
          <span className="text-foreground/40">:</span>
          <span className="text-blue-400">~</span>
          <span className="text-foreground/40">$</span>
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 bg-transparent text-foreground outline-none caret-primary"
            autoFocus
            autoComplete="off"
            spellCheck={false}
          />
        </form>
      </div>

      {/* Status bar */}
      <div className="flex items-center justify-between px-3 py-1 border-t border-border/30 bg-[#0d1117] text-[10px] text-foreground/30">
        <span>bash</span>
        <span>{lines.length} lines</span>
        <span className={isProcessing ? 'text-emerald-400' : ''}>
          {isProcessing ? 'processing...' : 'ready'}
        </span>
      </div>
    </div>
  );
}
