'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Brain,
  Zap,
  Cpu,
  Activity,
  Layers,
  Database,
  Network,
  Users,
  Clock,
  Bell,
  Search,
  Monitor,
  HardDrive,
  Wifi,
  Rocket,
  Target,
  Sparkles,
  Command,
  Code,
  GitBranch,
  Package,
  Server,
  Cloud,
  Gauge,
  Calendar,
  FileText,
  Folder,
  Archive,
  Atom,
  Beaker,
  FlaskConical,
  TestTube,
  Heart,
  TrendingDown,
  Settings,
  Cog,
  ToggleLeft,
  ToggleRight,
  Bolt,
  Flame,
  Sun,
  Moon,
  Star,
  Award,
  Trophy,
  Medal,
  Gem,
  Share2,
  Share,
  Link,
  Map,
  Navigation,
  Compass,
  ZoomIn,
  ZoomOut,
  Maximize,
  Minimize,
  RotateCw,
  RotateCcw,
  ArrowUp,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ChevronsUp,
  ChevronsDown,
  ChevronsLeft,
  ChevronsRight,
  LayoutGrid,
  LayoutList,
  Table,
  HardDriveDownload,
  HardDriveUpload,
  ServerCog,
  ServerCrash,
  ServerOff,
  Usb,
  MessageSquare,
  StickyNote,
  Bot,
  Puzzle,
  Wrench,
  Hammer,
  CloudRain,
  Thermometer,
  Info,
  X,
  Home, CheckCircle
} from 'lucide-react';

interface Capability {
  id: string;
  name: string;
  description: string;
  icon: any;
  category: string;
  status: 'active' | 'available' | 'experimental';
  features: string[];
  modules?: string[];
  metrics?: {
    performance: number;
    uptime: number;
    errors: number;
    requests: number;
  };
}

const CAPABILITIES: Capability[] = [
  // Advanced AI Systems
  {
    id: 'swarm-intelligence',
    name: 'Swarm Intelligence',
    description: 'Distributed multi-agent system for complex problem solving',
    icon: Users,
    category: 'Advanced AI',
    status: 'active',
    features: [
      '5 autonomous agents',
      'Distributed task execution',
      'Agent communication protocols',
      'Performance tracking',
      'Load balancing',
      'Fault tolerance'
    ],
    modules: ['Agent Manager', 'Task Distributor', 'Communication Router', 'Performance Monitor', 'Load Balancer'],
    metrics: { performance: 98, uptime: 99.9, errors: 0.01, requests: 15420 }
  },
  {
    id: 'multimodal-ai',
    name: 'Multimodal AI Fusion',
    description: 'AI system that processes and fuses multiple data modalities',
    icon: Layers,
    category: 'Advanced AI',
    status: 'active',
    features: [
      'Text processing',
      'Image analysis',
      'Audio recognition',
      'Video understanding',
      'Sensor data fusion',
      'Cross-modal reasoning'
    ],
    modules: ['Text Processor', 'Vision Engine', 'Audio Analyzer', 'Fusion Core', 'Cross-Modal Reasoner'],
    metrics: { performance: 95, uptime: 99.8, errors: 0.02, requests: 12350 }
  },
  {
    id: 'causal-reasoning',
    name: 'Causal Reasoning Engine',
    description: 'Graph-based causal inference and counterfactual analysis',
    icon: GitBranch,
    category: 'Advanced AI',
    status: 'active',
    features: [
      'Causal graph construction',
      'Counterfactual analysis',
      'Intervention modeling',
      'Causal effect estimation',
      'Graph-based inference',
      'Confidence scoring'
    ],
    modules: ['Graph Builder', 'Causal Inference', 'Counterfactual Engine', 'Effect Estimator', 'Confidence Scorer'],
    metrics: { performance: 92, uptime: 99.7, errors: 0.03, requests: 8900 }
  },
  {
    id: 'auto-optimizer',
    name: 'Performance Auto-Optimizer',
    description: 'Automatic system performance tuning and optimization',
    icon: Gauge,
    category: 'Advanced AI',
    status: 'active',
    features: [
      'Real-time monitoring',
      'Auto-tuning algorithms',
      'Resource optimization',
      'Cache management',
      'Memory optimization',
      'Performance metrics'
    ],
    modules: ['Monitor', 'Tuner', 'Resource Manager', 'Cache Optimizer', 'Memory Manager'],
    metrics: { performance: 97, uptime: 99.9, errors: 0.01, requests: 21000 }
  },
  {
    id: 'quantum-ai',
    name: 'Quantum AI Integration',
    description: 'Quantum computing simulation for AI algorithms',
    icon: Atom,
    category: 'Advanced AI',
    status: 'active',
    features: [
      'Grover search algorithm',
      'QAOA optimization',
      'VQE variational circuits',
      'Quantum ML circuits',
      'Quantum advantage simulation',
      'Circuit execution tracking'
    ],
    modules: ['Quantum Simulator', 'Grover Engine', 'QAOA Optimizer', 'VQE Circuit', 'ML Circuit'],
    metrics: { performance: 89, uptime: 99.5, errors: 0.05, requests: 5600 }
  },
  {
    id: 'neuro-symbolic',
    name: 'Neuro-Symbolic Integration',
    description: 'Hybrid neural and symbolic reasoning system',
    icon: Brain,
    category: 'Advanced AI',
    status: 'active',
    features: [
      'Symbolic rule engine',
      'Neural pattern recognition',
      'Hybrid inference',
      'Rule learning',
      'Pattern extraction',
      'Confidence estimation'
    ],
    modules: ['Symbolic Engine', 'Neural Network', 'Hybrid Inference', 'Rule Learner', 'Pattern Extractor'],
    metrics: { performance: 94, uptime: 99.8, errors: 0.02, requests: 11200 }
  },
  {
    id: 'knowledge-graph',
    name: 'Knowledge Graph & Memory',
    description: 'Advanced memory system with knowledge graph',
    icon: Network,
    category: 'Advanced AI',
    status: 'active',
    features: [
      'Knowledge node management',
      'Edge relationship tracking',
      'Memory retrieval',
      'Working memory',
      'Long-term storage',
      'Graph traversal'
    ],
    modules: ['Node Manager', 'Edge Tracker', 'Memory Retrieval', 'Working Memory', 'Graph Traverser'],
    metrics: { performance: 96, uptime: 99.9, errors: 0.01, requests: 18700 }
  },
  // base44 Features
  {
    id: 'multi-model-ai',
    name: 'Multi-Model AI Chat',
    description: 'Support for multiple AI model providers',
    icon: Bot,
    category: 'base44 Features',
    status: 'active',
    features: [
      'Claude (Anthropic)',
      'OpenAI GPT',
      'Google Gemini',
      'Ollama (local)',
      'Model switching',
      'Streaming responses'
    ],
    modules: ['Claude Provider', 'OpenAI Provider', 'Gemini Provider', 'Ollama Provider', 'Model Switcher'],
    metrics: { performance: 99, uptime: 99.9, errors: 0.01, requests: 25000 }
  },
  {
    id: 'notes-system',
    name: 'Notes Management',
    description: 'Full CRUD notes system with tags and search',
    icon: StickyNote,
    category: 'base44 Features',
    status: 'active',
    features: [
      'Create/Edit/Delete notes',
      'Tag support',
      'Full-text search',
      'Auto-save',
      'Timestamps',
      'SQLite persistence'
    ],
    modules: ['Note CRUD', 'Tag Manager', 'Search Engine', 'Auto-Save', 'SQLite Storage'],
    metrics: { performance: 100, uptime: 100, errors: 0, requests: 5000 }
  },
  {
    id: 'reminders-system',
    name: 'Reminders System',
    description: 'Task and reminder management with due dates',
    icon: Bell,
    category: 'base44 Features',
    status: 'active',
    features: [
      'Create/Edit/Delete reminders',
      'Due date tracking',
      'Completion status',
      'Overdue highlighting',
      'Tag support',
      'Persistent storage'
    ],
    modules: ['Reminder CRUD', 'Due Tracker', 'Status Manager', 'Overdue Checker', 'Storage'],
    metrics: { performance: 100, uptime: 100, errors: 0, requests: 3000 }
  },
  {
    id: 'web-search',
    name: 'Web Search Skill',
    description: 'DuckDuckGo web search integration',
    icon: Search,
    category: 'base44 Features',
    status: 'active',
    features: [
      'DuckDuckGo search',
      'Result summarization',
      'Query extraction',
      'Multiple results',
      'AI-powered summaries',
      'Intent detection'
    ],
    modules: ['Search API', 'Summarizer', 'Query Extractor', 'Result Parser', 'Intent Detector'],
    metrics: { performance: 95, uptime: 99.5, errors: 0.05, requests: 7500 }
  },
  {
    id: 'weather-skill',
    name: 'Weather Skill',
    description: 'Weather information via OpenWeatherMap',
    icon: CloudRain,
    category: 'base44 Features',
    status: 'available',
    features: [
      'Current weather',
      'Temperature data',
      'Humidity tracking',
      'Location support',
      'Forecast data',
      'API integration'
    ],
    modules: ['Weather API', 'Location Service', 'Forecast Engine', 'Data Parser'],
    metrics: { performance: 90, uptime: 98, errors: 0.1, requests: 2000 }
  },
  {
    id: 'system-info',
    name: 'System Info Skill',
    description: 'System information and monitoring',
    icon: Cpu,
    category: 'base44 Features',
    status: 'active',
    features: [
      'CPU monitoring',
      'Memory tracking',
      'Disk usage',
      'Time/date info',
      'System stats',
      'Real-time data'
    ],
    modules: ['CPU Monitor', 'Memory Tracker', 'Disk Monitor', 'Time Service', 'Stats Collector'],
    metrics: { performance: 100, uptime: 100, errors: 0, requests: 10000 }
  },
  {
    id: 'smart-home',
    name: 'Smart Home Integration',
    description: 'Home Assistant smart device control',
    icon: Home,
    category: 'base44 Features',
    status: 'available',
    features: [
      'Light control',
      'Thermostat control',
      'ToggleLeft management',
      'Device listing',
      'State monitoring',
      'Service calls'
    ],
    modules: ['Device Manager', 'Light Controller', 'Thermostat Controller', 'ToggleLeft Manager', 'State Monitor'],
    metrics: { performance: 85, uptime: 97, errors: 0.15, requests: 1500 }
  },
  // Core Systems
  {
    id: 'drive-engine',
    name: 'JARVIS Drive Engine',
    description: 'Core AI engine for JARVIS system',
    icon: Cpu,
    category: 'Core Systems',
    status: 'active',
    features: [
      'AI orchestration',
      'Task management',
      'Component coordination',
      'Resource allocation',
      'Error handling',
      'Performance monitoring'
    ],
    modules: ['Orchestrator', 'Task Manager', 'Component Coordinator', 'Resource Allocator', 'Error Handler'],
    metrics: { performance: 99, uptime: 99.9, errors: 0.01, requests: 50000 }
  },
  {
    id: 'component-registry',
    name: 'Component Registry',
    description: '209 registered system components',
    icon: Database,
    category: 'Core Systems',
    status: 'active',
    features: [
      '209 components',
      'Auto-discovery',
      'Lifecycle management',
      'Dependency tracking',
      'Health monitoring',
      'Start/stop controls'
    ],
    modules: ['Discovery Engine', 'Lifecycle Manager', 'Dependency Tracker', 'Health Monitor', 'Control Interface'],
    metrics: { performance: 100, uptime: 100, errors: 0, requests: 20000 }
  },
  {
    id: 'microservices',
    name: 'Microservices Architecture',
    description: 'Distributed microservices system',
    icon: Server,
    category: 'Core Systems',
    status: 'active',
    features: [
      'Service registry',
      'Load balancing',
      'API gateway',
      'Service discovery',
      'Health checks',
      'Scaling support'
    ],
    modules: ['Service Registry', 'Load Balancer', 'API Gateway', 'Discovery Service', 'Health Checker'],
    metrics: { performance: 97, uptime: 99.8, errors: 0.02, requests: 35000 }
  },
  {
    id: 'websockets',
    name: 'Real-time WebSocket',
    description: 'Real-time bidirectional communication',
    icon: Wifi,
    category: 'Core Systems',
    status: 'active',
    features: [
      'Dashboard streaming',
      'Component updates',
      'Real-time metrics',
      'Event broadcasting',
      'Connection management',
      'Auto-reconnect'
    ],
    modules: ['WebSocket Server', 'Event Broadcaster', 'Connection Manager', 'Reconnect Handler'],
    metrics: { performance: 98, uptime: 99.9, errors: 0.01, requests: 40000 }
  },
  {
    id: 'entity-layer',
    name: 'Entity Layer (base44)',
    description: 'Auto-CRUD database entity system',
    icon: Database,
    category: 'Core Systems',
    status: 'active',
    features: [
      'Auto table creation',
      'CRUD operations',
      'SQLite backend',
      'Schema definition',
      'Query filtering',
      'Relationship support'
    ],
    modules: ['Schema Manager', 'CRUD Generator', 'SQLite Backend', 'Query Builder', 'Relation Manager'],
    metrics: { performance: 99, uptime: 100, errors: 0, requests: 15000 }
  },
  {
    id: 'automated-testing',
    name: 'Automated Testing Suite',
    description: 'Comprehensive testing and validation',
    icon: TestTube,
    category: 'Core Systems',
    status: 'active',
    features: [
      'Unit tests',
      'Integration tests',
      'Performance tests',
      'Security tests',
      'Coverage reports',
      'CI/CD integration'
    ],
    modules: ['Unit Test Runner', 'Integration Tester', 'Performance Tester', 'Security Scanner', 'Coverage Reporter'],
    metrics: { performance: 95, uptime: 99, errors: 0.05, requests: 8000 }
  },
  {
    id: 'deployment',
    name: 'Deployment Management',
    description: 'System deployment and scaling',
    icon: Rocket,
    category: 'Core Systems',
    status: 'active',
    features: [
      'Container support',
      'Scaling capabilities',
      'Health monitoring',
      'Rollback support',
      'Configuration management',
      'Environment handling'
    ],
    modules: ['Container Manager', 'Scaler', 'Health Monitor', 'Rollback Manager', 'Config Manager'],
    metrics: { performance: 96, uptime: 99.5, errors: 0.03, requests: 5000 }
  }
];

const CATEGORIES = ['Advanced AI', 'base44 Features', 'Core Systems'];

export default function JarvisCapabilitiesOverview() {
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [selectedCapability, setSelectedCapability] = useState<Capability | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  const filteredCapabilities = CAPABILITIES.filter(cap => {
    const matchesCategory = selectedCategory === 'All' || cap.category === selectedCategory;
    const matchesSearch = cap.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         cap.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         cap.features.some(f => f.toLowerCase().includes(searchTerm.toLowerCase()));
    return matchesCategory && matchesSearch;
  });

  const activeCount = CAPABILITIES.filter(c => c.status === 'active').length;
  const availableCount = CAPABILITIES.filter(c => c.status === 'available').length;
  const experimentalCount = CAPABILITIES.filter(c => c.status === 'experimental').length;

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-2 flex items-center">
            <Sparkles className="mr-3 w-10 h-10 text-blue-400" />
            JARVIS Complete Capabilities
          </h1>
          <p className="text-gray-400 text-lg">
            Comprehensive overview of all {CAPABILITIES.length} system capabilities, tools, and features
          </p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-gradient-to-br from-blue-600 to-blue-800 p-6 rounded-xl">
            <div className="text-3xl font-bold">{CAPABILITIES.length}</div>
            <div className="text-blue-200">Total Capabilities</div>
          </div>
          <div className="bg-gradient-to-br from-green-600 to-green-800 p-6 rounded-xl">
            <div className="text-3xl font-bold">{activeCount}</div>
            <div className="text-green-200">Active</div>
          </div>
          <div className="bg-gradient-to-br from-yellow-600 to-yellow-800 p-6 rounded-xl">
            <div className="text-3xl font-bold">{availableCount}</div>
            <div className="text-yellow-200">Available</div>
          </div>
          <div className="bg-gradient-to-br from-purple-600 to-purple-800 p-6 rounded-xl">
            <div className="text-3xl font-bold">209</div>
            <div className="text-purple-200">Components</div>
          </div>
        </div>

        {/* Search and Filter */}
        <div className="mb-6 flex flex-col md:flex-row gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-3 text-gray-400 w-5 h-5" />
            <input
              type="text"
              placeholder="Search capabilities..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-gray-800 text-white pl-10 pr-4 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setSelectedCategory('All')}
              className={`px-4 py-2 rounded-lg ${selectedCategory === 'All' ? 'bg-blue-600' : 'bg-gray-700 hover:bg-gray-600'}`}
            >
              All
            </button>
            {CATEGORIES.map(cat => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-4 py-2 rounded-lg ${selectedCategory === cat ? 'bg-blue-600' : 'bg-gray-700 hover:bg-gray-600'}`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* Capabilities Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredCapabilities.map((capability) => {
            const Icon = capability.icon;
            return (
              <motion.div
                key={capability.id}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                whileHover={{ scale: 1.02 }}
                className="bg-gray-800 p-6 rounded-xl cursor-pointer hover:bg-gray-750 transition-colors"
                onClick={() => setSelectedCapability(capability)}
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="w-12 h-12 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
                    <Icon className="w-6 h-6 text-white" />
                  </div>
                  <span className={`px-2 py-1 rounded text-xs ${
                    capability.status === 'active' ? 'bg-green-600' :
                    capability.status === 'available' ? 'bg-yellow-600' :
                    'bg-purple-600'
                  }`}>
                    {capability.status}
                  </span>
                </div>
                <h3 className="text-xl font-bold mb-2">{capability.name}</h3>
                <p className="text-gray-400 text-sm mb-3">{capability.description}</p>
                <div className="text-xs text-gray-500">{capability.category}</div>
                <div className="mt-3 text-xs text-blue-400">
                  {capability.features.length} features
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Detail Modal */}
        <AnimatePresence>
          {selectedCapability && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50"
              onClick={() => setSelectedCapability(null)}
            >
              <motion.div
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.9, opacity: 0 }}
                className="bg-gray-800 p-8 rounded-xl max-w-2xl w-full"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-start justify-between mb-6">
                  <div className="flex items-center">
                    <div className="w-16 h-16 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center mr-4">
                      {React.createElement(selectedCapability.icon, { className: 'w-8 h-8 text-white' })}
                    </div>
                    <div>
                      <h2 className="text-2xl font-bold">{selectedCapability.name}</h2>
                      <p className="text-gray-400">{selectedCapability.category}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setSelectedCapability(null)}
                    className="text-gray-400 hover:text-white"
                  >
                    <X className="w-6 h-6" />
                  </button>
                </div>
                <p className="text-gray-300 mb-6">{selectedCapability.description}</p>
                <div className="mb-4">
                  <h3 className="text-lg font-bold mb-3">Features</h3>
                  <ul className="space-y-2">
                    {selectedCapability.features.map((feature, index) => (
                      <li key={index} className="flex items-center text-gray-300">
                        <CheckCircle className="w-4 h-4 mr-2 text-green-400" />
                        {feature}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* HUD - Functional Modules */}
                {selectedCapability.modules && (
                  <div className="mb-4 bg-gray-700 p-4 rounded-xl">
                    <h3 className="text-lg font-bold mb-3 flex items-center">
                      <Activity className="w-5 h-5 mr-2 text-blue-400" />
                      Functional Modules (HUD)
                    </h3>
                    <div className="grid grid-cols-2 gap-2">
                      {selectedCapability.modules.map((module, index) => (
                        <motion.div
                          key={index}
                          initial={{ opacity: 0, scale: 0.9 }}
                          animate={{ opacity: 1, scale: 1 }}
                          transition={{ delay: index * 0.05 }}
                          className="bg-gray-800 p-3 rounded-lg border border-gray-600 hover:border-blue-500 transition-colors cursor-pointer"
                        >
                          <div className="flex items-center">
                            <div className="w-2 h-2 bg-green-500 rounded-full mr-2 animate-pulse"></div>
                            <span className="text-sm">{module}</span>
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  </div>
                )}

                {/* HUD - Performance Metrics */}
                {selectedCapability.metrics && (
                  <div className="mb-4 bg-gray-700 p-4 rounded-xl">
                    <h3 className="text-lg font-bold mb-3 flex items-center">
                      <Gauge className="w-5 h-5 mr-2 text-purple-400" />
                      Performance Metrics
                    </h3>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <div className="text-gray-400 text-sm">Performance</div>
                        <div className="text-2xl font-bold text-green-400">{selectedCapability.metrics.performance}%</div>
                        <div className="w-full bg-gray-600 rounded-full h-2 mt-1">
                          <div 
                            className="bg-green-500 h-2 rounded-full" 
                            style={{ width: `${selectedCapability.metrics.performance}%` }}
                          ></div>
                        </div>
                      </div>
                      <div>
                        <div className="text-gray-400 text-sm">Uptime</div>
                        <div className="text-2xl font-bold text-blue-400">{selectedCapability.metrics.uptime}%</div>
                        <div className="w-full bg-gray-600 rounded-full h-2 mt-1">
                          <div 
                            className="bg-blue-500 h-2 rounded-full" 
                            style={{ width: `${selectedCapability.metrics.uptime}%` }}
                          ></div>
                        </div>
                      </div>
                      <div>
                        <div className="text-gray-400 text-sm">Error Rate</div>
                        <div className="text-2xl font-bold text-red-400">{selectedCapability.metrics.errors}%</div>
                      </div>
                      <div>
                        <div className="text-gray-400 text-sm">Requests</div>
                        <div className="text-2xl font-bold text-purple-400">{selectedCapability.metrics.requests.toLocaleString()}</div>
                      </div>
                    </div>
                  </div>
                )}
                <div className="flex items-center justify-between">
                  <span className={`px-3 py-1 rounded ${
                    selectedCapability.status === 'active' ? 'bg-green-600' :
                    selectedCapability.status === 'available' ? 'bg-yellow-600' :
                    'bg-purple-600'
                  }`}>
                    Status: {selectedCapability.status}
                  </span>
                  <button
                    onClick={() => setSelectedCapability(null)}
                    className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg"
                  >
                    Close
                  </button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
