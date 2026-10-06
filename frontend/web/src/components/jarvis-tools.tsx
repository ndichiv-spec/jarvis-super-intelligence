'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Wrench, Hammer, Drill, Ruler, 
  Calculator, Clock, Calendar, Timer,
  Terminal, Code, Database, Cloud, Server,
  Image, FileText, Music, Video, File,
  Search, Filter, Download, Upload,
  Zap, Shield, Lock, Key, Globe,
  Play, Pause, RefreshCw, Settings, X, Activity
} from 'lucide-react';

interface Tool {
  id: string;
  name: string;
  description: string;
  icon: any;
  category: string;
  status: 'active' | 'available' | 'beta';
  shortcut?: string;
}

const TOOLS: Tool[] = [
  // Development Tools
  {
    id: 'terminal',
    name: 'Terminal',
    description: 'Command line interface',
    icon: Terminal,
    category: 'Development',
    status: 'active',
    shortcut: 'Ctrl+`'
  },
  {
    id: 'code-editor',
    name: 'Code Editor',
    description: 'Full-featured code editor',
    icon: Code,
    category: 'Development',
    status: 'active',
    shortcut: 'Ctrl+E'
  },
  {
    id: 'database-browser',
    name: 'Database Browser',
    description: 'View and edit databases',
    icon: Database,
    category: 'Development',
    status: 'active'
  },
  // Utility Tools
  {
    id: 'calculator',
    name: 'Calculator',
    description: 'Scientific calculator',
    icon: Calculator,
    category: 'Utility',
    status: 'active',
    shortcut: 'Ctrl+C'
  },
  {
    id: 'timer',
    name: 'Timer',
    description: 'Countdown and stopwatch',
    icon: Timer,
    category: 'Utility',
    status: 'active'
  },
  {
    id: 'calendar',
    name: 'Calendar',
    description: 'Schedule and events',
    icon: Calendar,
    category: 'Utility',
    status: 'active'
  },
  // System Tools
  {
    id: 'system-monitor',
    name: 'System Monitor',
    description: 'CPU, memory, disk usage',
    icon: Activity,
    category: 'System',
    status: 'active'
  },
  {
    id: 'network-tools',
    name: 'Network Tools',
    description: 'Ping, traceroute, DNS',
    icon: Globe,
    category: 'System',
    status: 'active'
  },
  {
    id: 'file-manager',
    name: 'File Manager',
    description: 'Browse and manage files',
    icon: File,
    category: 'System',
    status: 'active'
  },
  // Security Tools
  {
    id: 'password-generator',
    name: 'Password Generator',
    description: 'Generate secure passwords',
    icon: Key,
    category: 'Security',
    status: 'active'
  },
  {
    id: 'encryption',
    name: 'Encryption',
    description: 'Encrypt/decrypt files',
    icon: Lock,
    category: 'Security',
    status: 'active'
  },
  {
    id: 'security-scan',
    name: 'Security Scan',
    description: 'Scan for vulnerabilities',
    icon: Shield,
    category: 'Security',
    status: 'beta'
  },
  // Media Tools
  {
    id: 'image-editor',
    name: 'Image Editor',
    description: 'Edit and optimize images',
    icon: Image,
    category: 'Media',
    status: 'available'
  },
  {
    id: 'video-player',
    name: 'Video Player',
    description: 'Play video files',
    icon: Video,
    category: 'Media',
    status: 'active'
  },
  {
    id: 'audio-player',
    name: 'Audio Player',
    description: 'Play music and audio',
    icon: Music,
    category: 'Media',
    status: 'active'
  }
];

const CATEGORIES = ['All', 'Development', 'Utility', 'System', 'Security', 'Media'];

export default function JarvisTools() {
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  const filteredTools = TOOLS.filter(tool => {
    const matchesCategory = selectedCategory === 'All' || tool.category === selectedCategory;
    const matchesSearch = tool.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         tool.description.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesCategory && matchesSearch;
  });

  const activeCount = TOOLS.filter(t => t.status === 'active').length;
  const availableCount = TOOLS.filter(t => t.status === 'available').length;
  const betaCount = TOOLS.filter(t => t.status === 'beta').length;

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-green-900 to-gray-900 text-white p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <h1 className="text-4xl font-bold mb-2 flex items-center">
            <Wrench className="mr-3 w-10 h-10 text-green-400" />
            JARVIS Tools
          </h1>
          <p className="text-gray-400">Powerful tools for every task</p>
        </motion.div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-gradient-to-br from-green-600 to-green-800 p-6 rounded-xl"
          >
            <div className="text-3xl font-bold">{TOOLS.length}</div>
            <div className="text-green-200">Total Tools</div>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.1 }}
            className="bg-gradient-to-br from-blue-600 to-blue-800 p-6 rounded-xl"
          >
            <div className="text-3xl font-bold">{activeCount}</div>
            <div className="text-blue-200">Active</div>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.2 }}
            className="bg-gradient-to-br from-yellow-600 to-yellow-800 p-6 rounded-xl"
          >
            <div className="text-3xl font-bold">{availableCount}</div>
            <div className="text-yellow-200">Available</div>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.3 }}
            className="bg-gradient-to-br from-purple-600 to-purple-800 p-6 rounded-xl"
          >
            <div className="text-3xl font-bold">{betaCount}</div>
            <div className="text-purple-200">Beta</div>
          </motion.div>
        </div>

        {/* Search and Filter */}
        <div className="mb-6 flex flex-col md:flex-row gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-3 text-gray-400 w-5 h-5" />
            <input
              type="text"
              placeholder="Search tools..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-gray-800 text-white pl-10 pr-4 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-600"
            />
          </div>
          <div className="flex gap-2">
            {CATEGORIES.map(cat => (
              <motion.button
                key={cat}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => setSelectedCategory(cat)}
                className={`px-4 py-2 rounded-lg ${
                  selectedCategory === cat ? 'bg-green-600' : 'bg-gray-700 hover:bg-gray-600'
                }`}
              >
                {cat}
              </motion.button>
            ))}
          </div>
        </div>

        {/* Tools Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredTools.map((tool, index) => {
            const Icon = tool.icon;
            return (
              <motion.div
                key={tool.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
                whileHover={{ scale: 1.03, y: -5 }}
                onClick={() => setSelectedTool(tool)}
                className="cursor-pointer"
              >
                <div className="relative">
                  <div className="absolute inset-0 bg-gradient-to-r from-green-600 to-emerald-600 rounded-2xl blur-xl opacity-50"></div>
                  <div className="relative bg-gray-900/80 backdrop-blur-xl p-6 rounded-2xl border border-gray-700/50">
                    <div className="flex items-start justify-between mb-4">
                      <div className="w-14 h-14 bg-gradient-to-br from-green-600 to-emerald-600 rounded-xl flex items-center justify-center">
                        <Icon className="w-7 h-7" />
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className={`px-2 py-1 rounded text-xs font-semibold ${
                          tool.status === 'active' ? 'bg-green-600' :
                          tool.status === 'available' ? 'bg-yellow-600' :
                          'bg-purple-600'
                        }`}>
                          {tool.status}
                        </span>
                      </div>
                    </div>
                    <h3 className="text-xl font-bold mb-2">{tool.name}</h3>
                    <p className="text-gray-400 text-sm mb-3">{tool.description}</p>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-500">{tool.category}</span>
                      {tool.shortcut && (
                        <span className="text-xs bg-gray-700 px-2 py-1 rounded">{tool.shortcut}</span>
                      )}
                    </div>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Tool Detail Modal */}
        <AnimatePresence>
          {selectedTool && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4"
              onClick={() => setSelectedTool(null)}
            >
              <motion.div
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.9, opacity: 0 }}
                className="bg-gray-900 p-8 rounded-2xl max-w-2xl w-full border border-gray-700"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center">
                    <div className="w-16 h-16 bg-gradient-to-br from-green-600 to-emerald-600 rounded-xl flex items-center justify-center mr-4">
                      {React.createElement(selectedTool.icon, { className: 'w-8 h-8' })}
                    </div>
                    <div>
                      <h2 className="text-2xl font-bold">{selectedTool.name}</h2>
                      <p className="text-gray-400">{selectedTool.category}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setSelectedTool(null)}
                    className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
                  >
                    <X className="w-6 h-6" />
                  </button>
                </div>

                <div className="space-y-4">
                  <div className="bg-gray-800 p-4 rounded-xl">
                    <h3 className="font-semibold mb-2">Description</h3>
                    <p className="text-gray-300">{selectedTool.description}</p>
                  </div>

                  <div className="bg-gray-800 p-4 rounded-xl">
                    <h3 className="font-semibold mb-2">Status</h3>
                    <div className="flex items-center">
                      <div className={`w-3 h-3 rounded-full mr-2 ${
                        selectedTool.status === 'active' ? 'bg-green-500' :
                        selectedTool.status === 'available' ? 'bg-yellow-500' :
                        'bg-purple-500'
                      }`}></div>
                      <span className="capitalize">{selectedTool.status}</span>
                    </div>
                  </div>

                  {selectedTool.shortcut && (
                    <div className="bg-gray-800 p-4 rounded-xl">
                      <h3 className="font-semibold mb-2">Keyboard Shortcut</h3>
                      <div className="bg-gray-700 px-4 py-2 rounded-lg inline-block">
                        <code className="text-green-400">{selectedTool.shortcut}</code>
                      </div>
                    </div>
                  )}

                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    className="w-full bg-gradient-to-r from-green-600 to-emerald-600 p-4 rounded-xl font-semibold flex items-center justify-center"
                  >
                    <Play className="w-5 h-5 mr-2" />
                    Launch Tool
                  </motion.button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
