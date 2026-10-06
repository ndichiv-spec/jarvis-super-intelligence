'use client';

import React, { useState, useEffect } from 'react';
import { useWebSocketSubscription } from '@/hooks/useWebSocket';
import { getApiUrl, getWsUrl } from '@/lib/runtime-url';
import { motion, AnimatePresence } from 'framer-motion';
import JarvisChat from './jarvis-chat';
import JarvisNotes from './jarvis-notes';
import JarvisReminders from './jarvis-reminders';
import JarvisCapabilitiesOverview from './jarvis-capabilities-overview';
import CascadeCodeViewer from './cascade-codeviewer';
import JarvisSuperiorDashboard from './jarvis-superior-dashboard';
import JarvisSmartHome from './jarvis-smart-home';
import JarvisSettings from './jarvis-settings';
import JarvisTools from './jarvis-tools';
import {
  Brain,
  Zap,
  Shield,
  Globe,
  Cpu,
  Activity,
  Settings,
  Layers,
  Terminal,
  Database,
  Network,
  BarChart3,
  PieChart,
  TrendingUp,
  Users,
  Clock,
  Bell,
  Search,
  Menu,
  X,
  ChevronDown,
  List,
  Monitor,
  HardDrive,
  Wifi,
  Lock,
  Unlock,
  Eye,
  EyeOff,
  Download,
  Upload,
  RefreshCw,
  Play,
  Pause,
  Square,
  Circle,
  AlertTriangle,
  Rocket,
  Target,
  Sparkles,
  Command,
  Code,
  GitBranch,
  Package,
  Server,
  Cloud,
  MemoryStick,
  Plug,
  Battery,
  Gauge,
  Timer,
  Calendar,
  FileText,
  Folder,
  FolderOpen,
  Archive,
  Atom,
  Dna,
  Microscope,
  Beaker,
  FlaskConical,
  TestTube,
  Stethoscope,
  Heart,
  TrendingDown,
  Thermometer,
  MessageSquare,
  StickyNote,
  Bot,
  Puzzle,
  Wrench,
  Hammer,
  CloudRain,
  Info,
  Home, CheckCircle
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
  completed_tasks: number;
  failed_tasks: number;
}

interface ComponentInfo {
  id: string;
  name: string;
  status: 'active' | 'inactive' | 'error';
  type: string;
  description: string;
  last_update: string;
  dependencies: string[];
}

interface AICapability {
  name: string;
  status: 'active' | 'inactive' | 'training';
  performance: number;
  usage: number;
  description: string;
  last_trained: string;
}

export default function JarvisCompleteDashboard() {
  const [systemStatus, setSystemStatus] = useState<SystemStatus>({
    status: 'online',
    uptime: '0h 0m 0s',
    components: 209,
    active_processes: 0,
    cpu_usage: 0,
    memory_usage: 0,
    disk_usage: 0,
    network_status: 'connected',
    last_update: new Date().toISOString()
  });

  const [driveEngineStatus, setDriveEngineStatus] = useState<DriveEngineStatus>({
    initialized: false,
    components_loaded: 0,
    ai_capabilities: [],
    performance_metrics: {
      response_time: 0,
      throughput: 0,
      error_rate: 0
    },
    active_tasks: 0,
    completed_tasks: 0,
    failed_tasks: 0
  });

  const [components, setComponents] = useState<ComponentInfo[]>([]);
  const [aiCapabilities, setAICapabilities] = useState<AICapability[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSection, setSelectedSection] = useState('overview');
  const [componentAction, setComponentAction] = useState<{id: string, action: string} | null>(null);
  const [aiTasks, setAiTasks] = useState<any[]>([]);
  const [newTask, setNewTask] = useState({ type: 'general', input: '' });
  
  // Advanced systems state
  const [swarmStatus, setSwarmStatus] = useState<any>(null);
  const [multimodalStatus, setMultimodalStatus] = useState<any>(null);
  const [causalStatus, setCausalStatus] = useState<any>(null);
  const [optimizerStatus, setOptimizerStatus] = useState<any>(null);
  const [quantumStatus, setQuantumStatus] = useState<any>(null);
  const [neuroSymbolicStatus, setNeuroSymbolicStatus] = useState<any>(null);
  const [memoryStatus, setMemoryStatus] = useState<any>(null);

  // Sections configuration
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

  // Component control functions
  const handleComponentAction = async (componentId: string, action: 'start' | 'stop' | 'restart') => {
    setComponentAction({ id: componentId, action });
    try {
      const response = await fetch(getApiUrl(`/api/v1/components/${componentId}/${action}`), {
        method: 'POST'
      });
      const result = await response.json();
      if (result.success) {
        // Refresh components
        const componentsResponse = await fetch(getApiUrl('/api/v1/components'));
        const componentsData = await componentsResponse.json();
        setComponents(componentsData.components || []);
      }
    } catch (error) {
      console.error('Component action failed:', error);
    } finally {
      setComponentAction(null);
    }
  };

  const handleStartAll = async () => {
    try {
      const response = await fetch(getApiUrl('/api/v1/components/start-all'), {
        method: 'POST'
      });
      const result = await response.json();
      if (result.success) {
        const componentsResponse = await fetch(getApiUrl('/api/v1/components'));
        const componentsData = await componentsResponse.json();
        setComponents(componentsData.components || []);
      }
    } catch (error) {
      console.error('Start all failed:', error);
    }
  };

  const handleStopAll = async () => {
    try {
      const response = await fetch(getApiUrl('/api/v1/components/stop-all'), {
        method: 'POST'
      });
      const result = await response.json();
      if (result.success) {
        const componentsResponse = await fetch(getApiUrl('/api/v1/components'));
        const componentsData = await componentsResponse.json();
        setComponents(componentsData.components || []);
      }
    } catch (error) {
      console.error('Stop all failed:', error);
    }
  };

  // AI Task functions
  const handleCreateTask = async () => {
    try {
      const response = await fetch(getApiUrl('/api/v1/ai/tasks'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newTask)
      });
      const result = await response.json();
      if (result.success) {
        setNewTask({ type: 'general', input: '' });
        fetchAITasks();
      }
    } catch (error) {
      console.error('Failed to create task:', error);
    }
  };

  const fetchAITasks = async () => {
    try {
      const response = await fetch(getApiUrl('/api/v1/ai/tasks'));
      const data = await response.json();
      setAiTasks(data.tasks || []);
    } catch (error) {
      console.error('Failed to fetch AI tasks:', error);
    }
  };

  // Fetch AI tasks on mount
  useEffect(() => {
    fetchAITasks();
    const interval = setInterval(fetchAITasks, 5000);
    return () => clearInterval(interval);
  }, []);

  // Fetch advanced systems data
  const fetchAdvancedSystems = async () => {
    try {
      const [swarm, multimodal, causal, optimizer, quantum, neuroSymbolic, memory] = await Promise.all([
        fetch(getApiUrl('/api/v1/swarm/status')).then(r => r.json()).catch(() => null),
        fetch(getApiUrl('/api/v1/multimodal/status')).then(r => r.json()).catch(() => null),
        fetch(getApiUrl('/api/v1/causal/status')).then(r => r.json()).catch(() => null),
        fetch(getApiUrl('/api/v1/optimizer/status')).then(r => r.json()).catch(() => null),
        fetch(getApiUrl('/api/v1/quantum/status')).then(r => r.json()).catch(() => null),
        fetch(getApiUrl('/api/v1/neuro_symbolic/status')).then(r => r.json()).catch(() => null),
        fetch(getApiUrl('/api/v1/memory/status')).then(r => r.json()).catch(() => null)
      ]);

      if (swarm && !swarm.error) setSwarmStatus(swarm);
      if (multimodal && !multimodal.error) setMultimodalStatus(multimodal);
      if (causal && !causal.error) setCausalStatus(causal);
      if (optimizer && !optimizer.error) setOptimizerStatus(optimizer);
      if (quantum && !quantum.error) setQuantumStatus(quantum);
      if (neuroSymbolic && !neuroSymbolic.error) setNeuroSymbolicStatus(neuroSymbolic);
      if (memory && !memory.error) setMemoryStatus(memory);
    } catch (error) {
      console.error('Error fetching advanced systems:', error);
    }
  };

  // Fetch advanced systems on mount
  useEffect(() => {
    fetchAdvancedSystems();
    const interval = setInterval(fetchAdvancedSystems, 10000);
    return () => clearInterval(interval);
  }, []);

  const dashboardWS = useWebSocketSubscription(getWsUrl('/ws/dashboard'));
  const componentsWS = useWebSocketSubscription(getWsUrl('/ws/components'));

  // Handle WebSocket updates
  useEffect(() => {
    if (dashboardWS.lastMessage && dashboardWS.lastMessage.type === 'status_update' && dashboardWS.lastMessage.data) {
      setSystemStatus(prev => ({
        ...prev,
        ...(dashboardWS.lastMessage?.data || {}),
        last_update: new Date().toISOString()
      }));
    }
  }, [dashboardWS.lastMessage?.type]);

  useEffect(() => {
    if (componentsWS.lastMessage && componentsWS.lastMessage.type === 'components_update' && componentsWS.lastMessage.data) {
      setComponents((componentsWS.lastMessage?.data as any)?.components || []);
    }
  }, [componentsWS.lastMessage]);

  // Initial data fetch
  useEffect(() => {
    const fetchSystemData = async () => {
      try {
        const statusResponse = await fetch('/api/v1/status');
        if (statusResponse.ok) {
          const statusData = await statusResponse.json();
          setSystemStatus(prev => ({
            ...prev,
            ...statusData,
            last_update: new Date().toISOString()
          }));
        }

        const componentsResponse = await fetch('/api/v1/components');
        if (componentsResponse.ok) {
          const componentsData = await componentsResponse.json();
          setComponents(componentsData.components || []);
        }

        const metricsResponse = await fetch('/api/v1/metrics');
        if (metricsResponse.ok) {
          const metricsData = await metricsResponse.json();
          setDriveEngineStatus(prev => ({
            ...prev,
            initialized: true,
            components_loaded: metricsData.components_loaded || 209,
            performance_metrics: metricsData.performance_metrics || prev.performance_metrics
          }));
        }

        setLoading(false);
      } catch (error) {
        console.error('Error fetching system data:', error);
        setLoading(false);
      }
    };

    fetchSystemData();
  }, []);

  const renderOverview = () => (
    <div className="space-y-6">
      {/* System Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="bg-gradient-to-br from-purple-600 to-purple-800 p-6 rounded-xl shadow-xl"
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-green-100 text-sm">System Status</p>
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

      {/* Drive Engine Status */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-gray-800 p-6 rounded-xl shadow-xl"
      >
        <h3 className="text-xl font-bold text-white mb-4 flex items-center">
          <Cpu className="mr-2" />
          Drive Engine Status
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-gray-700 p-4 rounded-lg">
            <p className="text-gray-400 text-sm">Initialization</p>
            <p className="text-lg font-semibold text-white">
              {driveEngineStatus.initialized ? '✅ Initialized' : '⏳ Initializing...'}
            </p>
          </div>
          <div className="bg-gray-700 p-4 rounded-lg">
            <p className="text-gray-400 text-sm">Active Tasks</p>
            <p className="text-lg font-semibold text-white">{driveEngineStatus.active_tasks}</p>
          </div>
          <div className="bg-gray-700 p-4 rounded-lg">
            <p className="text-gray-400 text-sm">Response Time</p>
            <p className="text-lg font-semibold text-white">{driveEngineStatus.performance_metrics.response_time}ms</p>
          </div>
        </div>
      </motion.div>
    </div>
  );

  const renderDriveEngine = () => (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-gray-800 p-6 rounded-xl shadow-xl"
      >
        <h3 className="text-xl font-bold text-white mb-4 flex items-center">
          <Rocket className="mr-2" />
          Drive Engine Control Center
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <h4 className="text-lg font-semibold text-white mb-3">System Controls</h4>
            <div className="space-y-3">
              <button className="w-full bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center justify-center">
                <Play className="mr-2" /> Start All Components
              </button>
              <button className="w-full bg-yellow-600 hover:bg-yellow-700 text-white px-4 py-2 rounded-lg flex items-center justify-center">
                <Pause className="mr-2" /> Pause System
              </button>
              <button className="w-full bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg flex items-center justify-center">
                <Square className="mr-2" /> Stop All Components
              </button>
              <button className="w-full bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg flex items-center justify-center">
                <RefreshCw className="mr-2" /> Restart System
              </button>
            </div>
          </div>
          <div>
            <h4 className="text-lg font-semibold text-white mb-3">Performance Metrics</h4>
            <div className="space-y-3">
              <div className="bg-gray-700 p-3 rounded-lg">
                <p className="text-gray-400 text-sm">Throughput</p>
                <p className="text-lg font-semibold text-white">{driveEngineStatus.performance_metrics.throughput} req/s</p>
              </div>
              <div className="bg-gray-700 p-3 rounded-lg">
                <p className="text-gray-400 text-sm">Error Rate</p>
                <p className="text-lg font-semibold text-white">{driveEngineStatus.performance_metrics.error_rate}%</p>
              </div>
              <div className="bg-gray-700 p-3 rounded-lg">
                <p className="text-gray-400 text-sm">Completed Tasks</p>
                <p className="text-lg font-semibold text-white">{driveEngineStatus.completed_tasks}</p>
              </div>
              <div className="bg-gray-700 p-3 rounded-lg">
                <p className="text-gray-400 text-sm">Failed Tasks</p>
                <p className="text-lg font-semibold text-white">{driveEngineStatus.failed_tasks}</p>
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );

  const renderComponents = () => (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-gray-800 p-6 rounded-xl shadow-xl"
      >
        <h3 className="text-xl font-bold text-white mb-4 flex items-center">
          <Package className="mr-2" />
          Component Management ({components.length})
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {components.slice(0, 12).map((component, index) => (
            <motion.div
              key={component.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className="bg-gray-700 p-4 rounded-lg"
            >
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-semibold text-white">{component.name}</h4>
                <div className={`w-3 h-3 rounded-full ${
                  component.status === 'active' ? 'bg-green-500' :
                  component.status === 'inactive' ? 'bg-yellow-500' : 'bg-red-500'
                }`} />
              </div>
              <p className="text-gray-400 text-sm mb-2">{component.description}</p>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">{component.type}</span>
                <div className="flex space-x-2">
                  {component.status === 'active' ? (
                    <>
                      <button 
                        onClick={() => handleComponentAction(component.id, 'stop')}
                        disabled={componentAction?.id === component.id}
                        className="text-red-400 hover:text-red-300 text-sm disabled:opacity-50"
                      >
                        {componentAction?.id === component.id && componentAction?.action === 'stop' ? 'Stopping...' : 'Stop'}
                      </button>
                      <button 
                        onClick={() => handleComponentAction(component.id, 'restart')}
                        disabled={componentAction?.id === component.id}
                        className="text-yellow-400 hover:text-yellow-300 text-sm disabled:opacity-50"
                      >
                        {componentAction?.id === component.id && componentAction?.action === 'restart' ? 'Restarting...' : 'Restart'}
                      </button>
                    </>
                  ) : (
                    <button 
                      onClick={() => handleComponentAction(component.id, 'start')}
                      disabled={componentAction?.id === component.id}
                      className="text-green-400 hover:text-green-300 text-sm disabled:opacity-50"
                    >
                      {componentAction?.id === component.id && componentAction?.action === 'start' ? 'Starting...' : 'Start'}
                    </button>
                  )}
                </div>
              </div>
            </motion.div>
          ))}
        </div>
        {components.length > 12 && (
          <div className="mt-4 flex justify-center space-x-4">
            <button 
              onClick={handleStartAll}
              className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg"
            >
              Start All
            </button>
            <button 
              onClick={handleStopAll}
              className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg"
            >
              Stop All
            </button>
            <button className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg">
              Load More Components
            </button>
          </div>
        )}
      </motion.div>
    </div>
  );

  const renderAICapabilities = () => (
    <div className="space-y-6">
      {/* AI Task Submission */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-gray-800 p-6 rounded-xl shadow-xl"
      >
        <h3 className="text-xl font-bold text-white mb-4 flex items-center">
          <Brain className="mr-2" />
          AI Task Submission
        </h3>
        <div className="space-y-4">
          <div>
            <label className="block text-gray-400 text-sm mb-2">Task Type</label>
            <select 
              value={newTask.type}
              onChange={(e) => setNewTask({...newTask, type: e.target.value})}
              className="w-full bg-gray-700 text-white px-4 py-2 rounded-lg"
            >
              <option value="general">General AI Task</option>
              <option value="analysis">Data Analysis</option>
              <option value="generation">Content Generation</option>
              <option value="optimization">System Optimization</option>
            </select>
          </div>
          <div>
            <label className="block text-gray-400 text-sm mb-2">Task Input</label>
            <textarea
              value={newTask.input}
              onChange={(e) => setNewTask({...newTask, input: e.target.value})}
              placeholder="Enter your task description..."
              className="w-full bg-gray-700 text-white px-4 py-2 rounded-lg h-24"
            />
          </div>
          <button 
            onClick={handleCreateTask}
            className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg"
          >
            Submit Task
          </button>
        </div>
      </motion.div>

      {/* AI Tasks List */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-gray-800 p-6 rounded-xl shadow-xl"
      >
        <h3 className="text-xl font-bold text-white mb-4 flex items-center">
          <Activity className="mr-2" />
          Active AI Tasks ({aiTasks.length})
        </h3>
        <div className="space-y-3">
          {aiTasks.slice(0, 5).map((task) => (
            <div key={task.id} className="bg-gray-700 p-4 rounded-lg">
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold text-white">{task.type}</span>
                <span className={`px-2 py-1 rounded text-xs ${
                  task.status === 'completed' ? 'bg-green-600' :
                  task.status === 'processing' ? 'bg-blue-600' :
                  task.status === 'failed' ? 'bg-red-600' : 'bg-yellow-600'
                }`}>
                  {task.status}
                </span>
              </div>
              <div className="w-full bg-gray-600 rounded-full h-2 mb-2">
                <div 
                  className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${task.progress}%` }}
                />
              </div>
              <p className="text-gray-400 text-sm">Progress: {task.progress}%</p>
            </div>
          ))}
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-gray-800 p-6 rounded-xl shadow-xl"
      >
        <h3 className="text-xl font-bold text-white mb-4 flex items-center">
          <Sparkles className="mr-2" />
          Advanced AI Systems Status
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Swarm Intelligence */}
          <div className="bg-gradient-to-r from-orange-600 to-red-600 p-4 rounded-lg">
            <h5 className="font-semibold text-white mb-2 flex items-center">
              <Users className="mr-2 w-4 h-4" />
              Swarm Intelligence
            </h5>
            {swarmStatus ? (
              <div>
                <p className="text-gray-200 text-sm mb-2">
                  {swarmStatus.agents?.length || 0} Active Agents
                </p>
                <div className="text-xs text-gray-300">
                  Tasks: {swarmStatus.metrics?.total_tasks || 0} | 
                  Completed: {swarmStatus.metrics?.completed_tasks || 0}
                </div>
              </div>
            ) : (
              <p className="text-gray-200 text-sm">Loading...</p>
            )}
          </div>
          
          {/* Multimodal AI */}
          <div className="bg-gradient-to-r from-green-600 to-teal-600 p-4 rounded-lg">
            <h5 className="font-semibold text-white mb-2 flex items-center">
              <Monitor className="mr-2 w-4 h-4" />
              Multimodal AI
            </h5>
            {multimodalStatus ? (
              <div>
                <p className="text-gray-200 text-sm mb-2">
                  {multimodalStatus.active_modalities?.length || 0} Modalities Active
                </p>
                <div className="text-xs text-gray-300">
                  Fusions: {multimodalStatus.performance_metrics?.total_fusions || 0}
                </div>
              </div>
            ) : (
              <p className="text-gray-200 text-sm">Loading...</p>
            )}
          </div>
          
          {/* Causal Reasoning */}
          <div className="bg-gradient-to-r from-purple-600 to-pink-600 p-4 rounded-lg">
            <h5 className="font-semibold text-white mb-2 flex items-center">
              <GitBranch className="mr-2 w-4 h-4" />
              Causal Reasoning
            </h5>
            {causalStatus ? (
              <div>
                <p className="text-gray-200 text-sm mb-2">
                  {causalStatus.nodes_count || 0} Nodes | {causalStatus.edges_count || 0} Edges
                </p>
                <div className="text-xs text-gray-300">
                  Inferences: {causalStatus.metrics?.total_inferences || 0}
                </div>
              </div>
            ) : (
              <p className="text-gray-200 text-sm">Loading...</p>
            )}
          </div>
          
          {/* Auto Optimizer */}
          <div className="bg-gradient-to-r from-blue-600 to-indigo-600 p-4 rounded-lg">
            <h5 className="font-semibold text-white mb-2 flex items-center">
              <Gauge className="mr-2 w-4 h-4" />
              Auto Optimizer
            </h5>
            {optimizerStatus ? (
              <div>
                <p className="text-gray-200 text-sm mb-2">
                  Auto-tuning: {optimizerStatus.auto_tuning_enabled ? 'Enabled' : 'Disabled'}
                </p>
                <div className="text-xs text-gray-300">
                  Optimizations: {optimizerStatus.stats?.total_optimizations || 0}
                </div>
              </div>
            ) : (
              <p className="text-gray-200 text-sm">Loading...</p>
            )}
          </div>
          
          {/* Quantum AI */}
          <div className="bg-gradient-to-r from-violet-600 to-purple-600 p-4 rounded-lg">
            <h5 className="font-semibold text-white mb-2 flex items-center">
              <Atom className="mr-2 w-4 h-4" />
              Quantum AI
            </h5>
            {quantumStatus ? (
              <div>
                <p className="text-gray-200 text-sm mb-2">
                  {quantumStatus.available_circuits || 0} Quantum Circuits
                </p>
                <div className="text-xs text-gray-300">
                  Executions: {quantumStatus.metrics?.total_executions || 0}
                </div>
              </div>
            ) : (
              <p className="text-gray-200 text-sm">Loading...</p>
            )}
          </div>
          
          {/* Neuro-Symbolic */}
          <div className="bg-gradient-to-r from-cyan-600 to-blue-600 p-4 rounded-lg">
            <h5 className="font-semibold text-white mb-2 flex items-center">
              <Brain className="mr-2 w-4 h-4" />
              Neuro-Symbolic
            </h5>
            {neuroSymbolicStatus ? (
              <div>
                <p className="text-gray-200 text-sm mb-2">
                  {neuroSymbolicStatus.symbolic_rules_count || 0} Rules | 
                  {neuroSymbolicStatus.neural_patterns_count || 0} Patterns
                </p>
                <div className="text-xs text-gray-300">
                  Inferences: {neuroSymbolicStatus.metrics?.total_inferences || 0}
                </div>
              </div>
            ) : (
              <p className="text-gray-200 text-sm">Loading...</p>
            )}
          </div>
          
          {/* Memory System */}
          <div className="bg-gradient-to-r from-amber-600 to-orange-600 p-4 rounded-lg md:col-span-2">
            <h5 className="font-semibold text-white mb-2 flex items-center">
              <Database className="mr-2 w-4 h-4" />
              Advanced Memory & Knowledge Graph
            </h5>
            {memoryStatus ? (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-gray-200 text-sm mb-2">
                    {memoryStatus.total_memories || 0} Memories | 
                    {memoryStatus.knowledge_nodes || 0} Knowledge Nodes
                  </p>
                  <div className="text-xs text-gray-300">
                    Working Memory: {memoryStatus.working_memory_size || 0}
                  </div>
                </div>
                <div>
                  <p className="text-gray-200 text-sm mb-2">
                    {memoryStatus.knowledge_edges || 0} Knowledge Edges
                  </p>
                  <div className="text-xs text-gray-300">
                    Retrievals: {memoryStatus.metrics?.retrieval_count || 0}
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-gray-200 text-sm">Loading...</p>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  );

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

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-500 mx-auto"></div>
          <p className="text-white mt-4">Loading JARVIS Dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <div className="bg-gray-800 border-b border-gray-700">
        <div className="p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="w-12 h-12 bg-gradient-to-r from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
                <Sparkles className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-white">JARVIS Complete Dashboard</h1>
                <p className="text-gray-400">Advanced AI System Management</p>
              </div>
            </div>
            <div className="flex items-center space-x-4">
              <div className={`px-3 py-1 rounded-full text-sm ${
                systemStatus.status === 'online' ? 'bg-green-600' : 'bg-red-600'
              }`}>
                {systemStatus.status}
              </div>
              <div className="text-sm text-gray-400">
                Last Update: {new Date(systemStatus.last_update).toLocaleTimeString()}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <div className="bg-gray-800 border-b border-gray-700">
        <div className="px-6">
          <div className="flex space-x-1 overflow-x-auto">
            {sections.map((section) => {
              const Icon = section.icon;
              return (
                <button
                  key={section.id}
                  onClick={() => setSelectedSection(section.id)}
                  className={`flex items-center px-4 py-3 rounded-t-lg transition-colors ${
                    selectedSection === section.id
                      ? 'bg-gray-900 text-blue-400 border-b-2 border-blue-400'
                      : 'text-gray-400 hover:text-white hover:bg-gray-700'
                  }`}
                >
                  <Icon className="w-4 h-4 mr-2" />
                  {section.name}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="p-6">
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
      </div>
    </div>
  );
}
