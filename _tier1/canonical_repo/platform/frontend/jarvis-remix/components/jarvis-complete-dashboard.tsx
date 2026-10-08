import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { JarvisChat } from './jarvis-chat';
import { JarvisNotes } from './jarvis-notes';
import { JarvisReminders } from './jarvis-reminders';
import { JarvisCapabilitiesOverview } from './jarvis-capabilities-overview';
import { CascadeCodeViewer } from './cascade-codeviewer';
import { JarvisSuperiorDashboard } from './jarvis-superior-dashboard';
import { JarvisSmartHome } from './jarvis-smart-home';
import { JarvisSettings } from './jarvis-settings';
import { JarvisTools } from './jarvis-tools';
import { 
  Brain, Zap, Shield, Globe, Cpu, Activity, Settings, Layers, Terminal,
  Database, Network, BarChart3, PieChart, TrendingUp, Users, Clock, Bell,
  Search, Menu, X, ChevronDown, Grid, List, Monitor, HardDrive, Wifi,
  Lock, Unlock, Eye, EyeOff, Download, Upload, RefreshCw, Play, Pause,
  Square, Circle, AlertTriangle, CheckCircle, XCircle, Rocket, Target,
  Sparkles, Command, Code, GitBranch, Package, Server, Cloud,
  MemoryStick, Plug, Battery, Gauge,
  Timer, Calendar, FileText, Folder, FolderOpen, Archive, Layers3,
  Atom, Dna, Microscope, Beaker, FlaskConical, TestTube, Stethoscope,
  Heart, TrendingDown, Thermometer, MessageSquare, StickyNote, Bot, Puzzle,
  Wrench, Hammer, Home, CloudRain, Info
} from 'lucide-react';

interface SystemStatus {
  status: 'online' | 'offline' | 'warning';
  uptime: string;
  components: number;
  active_processes: number;
  cpu_usage: number;
  memory_usage: number;
  disk_usage: number;
  network_status: 'connected' | 'disconnected';
  last_update: string;
}

interface DriveEngineStatus {
  initialized: boolean;
  components_loaded: number;
  ai_capabilities: string[];
  performance_metrics: {
    response_time: number;
    throughput: number;
    error_rate: number;
  };
  active_tasks: number;
}

interface JarvisCompleteDashboardProps {
  initialData?: any;
  healthStatus?: any;
}

export function JarvisCompleteDashboard({ 
  initialData, 
  healthStatus 
}: JarvisCompleteDashboardProps) {
  const [systemStatus, setSystemStatus] = useState<SystemStatus>({
    status: 'online',
    uptime: '00:00:00',
    components: 0,
    active_processes: 0,
    cpu_usage: 0,
    memory_usage: 0,
    disk_usage: 0,
    active_processes: 47,
    cpu_usage: 23,
    memory_usage: 67,
    disk_usage: 45,
    network_status: 'connected',
    last_update: new Date().toISOString()
  });

  const [driveEngineStatus, setDriveEngineStatus] = useState<DriveEngineStatus>({
    initialized: true,
    components_loaded: 209,
    ai_capabilities: ['Natural Language Processing', 'Computer Vision', 'Autonomous Decision Making'],
    performance_metrics: {
      response_time: 120,
      throughput: 1500,
      error_rate: 0.02
    },
    active_tasks: 12
  });

  const [hostname, setHostname] = useState('localhost');
  const [isConnected, setIsConnected] = useState(true);

  useEffect(() => {
    // Set hostname on client side only
    if (typeof window !== 'undefined') {
      setHostname(window.location.hostname);
    }
  }, []);

  useEffect(() => {
    // WebSocket connection for real-time updates
    if (typeof window !== 'undefined') {
      const ws = new WebSocket(`ws://${hostname}:8000/ws`);
      
      ws.onopen = () => {
        setIsConnected(true);
        console.log('WebSocket connected');
      };
      
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'system_status') {
          setSystemStatus(prev => ({ ...prev, ...data.payload }));
        } else if (data.type === 'drive_engine_status') {
          setDriveEngineStatus(prev => ({ ...prev, ...data.payload }));
        }
      };
      
      ws.onclose = () => {
        setIsConnected(false);
        console.log('WebSocket disconnected');
      };
      
      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setIsConnected(false);
      };
      
      return () => {
        ws.close();
      };
    }
  }, [hostname]);

  const sections = [
    { id: 'superior', name: 'Superior View', icon: Sparkles },
    { id: 'overview', name: 'Overview', icon: Activity },
    { id: 'drive-engine', name: 'Drive Engine', icon: Cpu },
    { id: 'components', name: 'Components', icon: Layers },
    { id: 'ai-capabilities', name: 'AI Capabilities', icon: Sparkles },
    { id: 'capabilities', name: 'All Capabilities', icon: Command },
    { id: 'smarthome', name: 'Smart Home', icon: Home },
    { id: 'tools', name: 'Tools', icon: Wrench },
    { id: 'codeviewer', name: 'Cascade CodeViewer', icon: Code },
    { id: 'settings', name: 'Settings', icon: Settings },
    { id: 'chat', name: 'AI Chat', icon: MessageSquare },
    { id: 'notes', name: 'Notes', icon: StickyNote },
    { id: 'reminders', name: 'Reminders', icon: Bell },
  ];

  const renderContent = () => {
    switch (selectedSection) {
      case 'superior':
        return <JarvisSuperiorDashboard />;
      case 'overview':
        return renderOverview();
      case 'drive-engine':
        return renderDriveEngine();
      case 'components':
        return renderComponents();
      case 'ai-capabilities':
        return renderAICapabilities();
      case 'capabilities':
        return <JarvisCapabilitiesOverview />;
      case 'smarthome':
        return <JarvisSmartHome />;
      case 'tools':
        return <JarvisTools />;
      case 'codeviewer':
        return <CascadeCodeViewer />;
      case 'settings':
        return <JarvisSettings />;
      case 'chat':
        return <JarvisChat />;
      case 'notes':
        return <JarvisNotes />;
      case 'reminders':
        return <JarvisReminders />;
      default:
        return <JarvisSuperiorDashboard />;
    }
  };

  const renderOverview = () => (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="bg-gradient-to-br from-blue-600 to-blue-800 p-6 rounded-xl shadow-xl"
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-blue-100 text-sm">System Status</p>
            <p className="text-2xl font-bold text-white">{systemStatus.status}</p>
          </div>
          <CheckCircle className="w-8 h-8 text-blue-200" />
        </div>
        <div className="mt-4">
          <p className="text-blue-100 text-xs">Uptime: {systemStatus.uptime}</p>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="bg-gradient-to-br from-green-600 to-green-800 p-6 rounded-xl shadow-xl"
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-green-100 text-sm">Components</p>
            <p className="text-2xl font-bold text-white">{systemStatus.components}</p>
          </div>
          <Package className="w-8 h-8 text-green-200" />
        </div>
        <div className="mt-4">
          <p className="text-green-100 text-xs">Active: {driveEngineStatus.components_loaded}</p>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="bg-gradient-to-br from-purple-600 to-purple-800 p-6 rounded-xl shadow-xl"
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-purple-100 text-sm">CPU Usage</p>
            <p className="text-2xl font-bold text-white">{systemStatus.cpu_usage}%</p>
          </div>
          <Cpu className="w-8 h-8 text-purple-200" />
        </div>
        <div className="mt-4">
          <div className="w-full bg-purple-900 rounded-full h-2">
            <div 
              className="bg-purple-300 h-2 rounded-full transition-all duration-300"
              style={{ width: `${systemStatus.cpu_usage}%` }}
            />
          </div>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="bg-gradient-to-br from-orange-600 to-orange-800 p-6 rounded-xl shadow-xl"
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-orange-100 text-sm">Memory Usage</p>
            <p className="text-2xl font-bold text-white">{systemStatus.memory_usage}%</p>
          </div>
          <MemoryStick className="w-8 h-8 text-orange-200" />
        </div>
        <div className="mt-4">
          <div className="w-full bg-orange-900 rounded-full h-2">
            <div 
              className="bg-orange-300 h-2 rounded-full transition-all duration-300"
              style={{ width: `${systemStatus.memory_usage}%` }}
            />
          </div>
        </div>
      </motion.div>
    </div>
  );

  const renderDriveEngine = () => (
    <div className="space-y-6">
      <div className="bg-gradient-to-r from-indigo-600 to-purple-600 p-6 rounded-xl">
        <h3 className="text-xl font-bold text-white mb-4">Drive Engine Status</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white/10 p-4 rounded-lg">
            <p className="text-indigo-100 text-sm">Initialized</p>
            <p className="text-lg font-semibold text-white">
              {driveEngineStatus.initialized ? 'Yes' : 'No'}
            </p>
          </div>
          <div className="bg-white/10 p-4 rounded-lg">
            <p className="text-indigo-100 text-sm">Components Loaded</p>
            <p className="text-lg font-semibold text-white">
              {driveEngineStatus.components_loaded}
            </p>
          </div>
          <div className="bg-white/10 p-4 rounded-lg">
            <p className="text-indigo-100 text-sm">Active Tasks</p>
            <p className="text-lg font-semibold text-white">
              {driveEngineStatus.active_tasks}
            </p>
          </div>
        </div>
      </div>

      <div className="bg-gray-800 p-6 rounded-xl">
        <h4 className="text-lg font-semibold text-white mb-4">Performance Metrics</h4>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <p className="text-gray-400 text-sm">Response Time</p>
            <p className="text-2xl font-bold text-green-400">
              {driveEngineStatus.performance_metrics.response_time}ms
            </p>
          </div>
          <div>
            <p className="text-gray-400 text-sm">Throughput</p>
            <p className="text-2xl font-bold text-blue-400">
              {driveEngineStatus.performance_metrics.throughput}/s
            </p>
          </div>
          <div>
            <p className="text-gray-400 text-sm">Error Rate</p>
            <p className="text-2xl font-bold text-red-400">
              {(driveEngineStatus.performance_metrics.error_rate * 100).toFixed(2)}%
            </p>
          </div>
        </div>
      </div>
    </div>
  );

  const renderComponents = () => (
    <div className="bg-gray-800 p-6 rounded-xl">
      <h3 className="text-xl font-bold text-white mb-4">System Components</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {['Advanced AI', 'Core Systems', 'Database', 'API Gateway', 'Security', 'Monitoring'].map((category, index) => (
          <motion.div
            key={category}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: index * 0.1 }}
            className="bg-gray-700 p-4 rounded-lg hover:bg-gray-600 transition-colors cursor-pointer"
          >
            <h4 className="font-semibold text-white mb-2">{category}</h4>
            <p className="text-gray-300 text-sm">Active components</p>
          </motion.div>
        ))}
      </div>
    </div>
  );

  const renderAICapabilities = () => (
    <div className="space-y-6">
      <div className="bg-gradient-to-r from-cyan-600 to-blue-600 p-6 rounded-xl">
        <h3 className="text-xl font-bold text-white mb-4">AI Capabilities</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {driveEngineStatus.ai_capabilities.map((capability, index) => (
            <motion.div
              key={capability}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.1 }}
              className="bg-white/10 p-4 rounded-lg"
            >
              <p className="text-white font-medium">{capability}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700">
        <div className="px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <Brain className="w-8 h-8 text-blue-400" />
              <h1 className="text-2xl font-bold">JARVIS Dashboard</h1>
              <div className="flex items-center space-x-2">
                <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-400' : 'bg-red-400'} animate-pulse`} />
                <span className="text-sm text-gray-400">
                  {isConnected ? 'Connected' : 'Disconnected'}
                </span>
              </div>
            </div>
            <div className="flex items-center space-x-4">
              <button className="p-2 rounded-lg hover:bg-gray-700 transition-colors">
                <Search className="w-5 h-5" />
              </button>
              <button className="p-2 rounded-lg hover:bg-gray-700 transition-colors">
                <Settings className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-gray-800 border-b border-gray-700">
        <div className="px-6 py-2">
          <div className="flex space-x-1 overflow-x-auto">
            {sections.map((section) => (
              <button
                key={section.id}
                onClick={() => setSelectedSection(section.id)}
                className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-colors ${
                  selectedSection === section.id
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:bg-gray-700 hover:text-white'
                }`}
              >
                <section.icon className="w-4 h-4" />
                <span className="text-sm font-medium">{section.name}</span>
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="p-6">
        <AnimatePresence mode="wait">
          <motion.div
            key={selectedSection}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
          >
            {renderContent()}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
