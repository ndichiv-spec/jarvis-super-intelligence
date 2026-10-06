'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
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
  Grid,
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
  CheckCircle,
  XCircle
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface DashboardMetrics {
  cpu: number;
  memory: number;
  disk: number;
  network: number;
  activeUsers: number;
  totalRequests: number;
  uptime: string;
  systemHealth: 'excellent' | 'good' | 'warning' | 'critical';
}

interface Tool {
  id: string;
  name: string;
  description: string;
  icon: React.ComponentType<any>;
  category: string;
  status: 'active' | 'inactive' | 'maintenance';
  usage?: number;
  lastUsed?: string;
}

interface SubDashboard {
  id: string;
  name: string;
  description: string;
  icon: React.ComponentType<any>;
  color: string;
  route: string;
  widgets: number;
  isActive: boolean;
}

export const ModernDashboardSystem: React.FC = () => {
  const [metrics, setMetrics] = useState<DashboardMetrics>({
    cpu: 45,
    memory: 62,
    disk: 78,
    network: 23,
    activeUsers: 127,
    totalRequests: 45982,
    uptime: '15d 7h 32m',
    systemHealth: 'excellent'
  });

  const [selectedDashboard, setSelectedDashboard] = useState('main');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [notifications, setNotifications] = useState(3);
  const [darkMode, setDarkMode] = useState(true);

  const tools: Tool[] = [
    {
      id: 'neural-processor',
      name: 'Neural Processor',
      description: 'Advanced AI processing with quantum algorithms',
      icon: Brain,
      category: 'AI Tools',
      status: 'active',
      usage: 87
    },
    {
      id: 'system-monitor',
      name: 'System Monitor',
      description: 'Real-time system performance tracking',
      icon: Monitor,
      category: 'System',
      status: 'active',
      usage: 92
    },
    {
      id: 'data-analyzer',
      name: 'Data Analyzer',
      description: 'Advanced data analysis and visualization',
      icon: BarChart3,
      category: 'Analytics',
      status: 'active',
      usage: 65
    },
    {
      id: 'network-scanner',
      name: 'Network Scanner',
      description: 'Network security and performance analysis',
      icon: Network,
      category: 'Security',
      status: 'active',
      usage: 78
    },
    {
      id: 'terminal',
      name: 'Advanced Terminal',
      description: 'Powerful command-line interface',
      icon: Terminal,
      category: 'Development',
      status: 'active',
      usage: 45
    },
    {
      id: 'database-manager',
      name: 'Database Manager',
      description: 'Database optimization and management',
      icon: Database,
      category: 'Data',
      status: 'active',
      usage: 56
    }
  ];

  const subDashboards: SubDashboard[] = [
    {
      id: 'main',
      name: 'Main Dashboard',
      description: 'Overview of all system metrics and controls',
      icon: Grid,
      color: 'from-blue-500 to-cyan-400',
      route: '/dashboard',
      widgets: 12,
      isActive: true
    },
    {
      id: 'analytics',
      name: 'Analytics Hub',
      description: 'Deep analytics and performance metrics',
      icon: BarChart3,
      color: 'from-purple-500 to-pink-400',
      route: '/dashboard/analytics',
      widgets: 8,
      isActive: false
    },
    {
      id: 'security',
      name: 'Security Center',
      description: 'Security monitoring and threat detection',
      icon: Shield,
      color: 'from-green-500 to-emerald-400',
      route: '/dashboard/security',
      widgets: 6,
      isActive: false
    },
    {
      id: 'development',
      name: 'Development Studio',
      description: 'Code development and testing environment',
      icon: Terminal,
      color: 'from-orange-500 to-red-400',
      route: '/dashboard/development',
      widgets: 10,
      isActive: false
    },
    {
      id: 'automation',
      name: 'Automation Hub',
      description: 'Task automation and workflow management',
      icon: Zap,
      color: 'from-yellow-500 to-amber-400',
      route: '/dashboard/automation',
      widgets: 7,
      isActive: false
    },
    {
      id: 'settings',
      name: 'Advanced Settings',
      description: 'System configuration and preferences',
      icon: Settings,
      color: 'from-indigo-500 to-purple-400',
      route: '/dashboard/settings',
      widgets: 15,
      isActive: false
    }
  ];

  useEffect(() => {
    // Simulate real-time metrics updates
    const interval = setInterval(() => {
      setMetrics(prev => ({
        ...prev,
        cpu: Math.max(10, Math.min(95, prev.cpu + (Math.random() - 0.5) * 5)),
        memory: Math.max(20, Math.min(95, prev.memory + (Math.random() - 0.5) * 3)),
        network: Math.max(5, Math.min(100, prev.network + (Math.random() - 0.5) * 8)),
        totalRequests: prev.totalRequests + Math.floor(Math.random() * 10)
      }));
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  const getHealthColor = (health: string) => {
    switch (health) {
      case 'excellent': return 'text-green-400';
      case 'good': return 'text-blue-400';
      case 'warning': return 'text-yellow-400';
      case 'critical': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  const getUsageColor = (usage: number) => {
    if (usage >= 80) return 'text-red-400';
    if (usage >= 60) return 'text-yellow-400';
    return 'text-green-400';
  };

  return (
    <div className={cn(
      'min-h-screen transition-colors duration-300',
      darkMode ? 'bg-gray-900' : 'bg-gray-50'
    )}>
      {/* Modern Header */}
      <header className="sticky top-0 z-50 backdrop-blur-xl border-b border-gray-800">
        <div className="flex items-center justify-between px-6 py-4">
          <div className="flex items-center space-x-4">
            <motion.div
              className="w-10 h-10 bg-gradient-to-r from-blue-500 to-purple-600 rounded-lg flex items-center justify-center"
              whileHover={{ rotate: 180, scale: 1.1 }}
              transition={{ type: 'spring', stiffness: 400, damping: 17 }}
            >
              <Brain className="w-6 h-6 text-white" />
            </motion.div>
            <div>
              <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-600 bg-clip-text text-transparent">
                JARVIS Advanced
              </h1>
              <p className="text-sm text-gray-400">Quantum Intelligence Platform</p>
            </div>
          </div>

          <div className="flex items-center space-x-6">
            {/* Search Bar */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search tools, dashboards, settings..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className={cn(
                  'pl-10 pr-4 py-2 w-64 rounded-lg border transition-all duration-200',
                  darkMode 
                    ? 'bg-gray-800 border-gray-700 text-white placeholder-gray-500 focus:border-blue-500' 
                    : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500 focus:border-blue-500'
                )}
              />
            </div>

            {/* Notifications */}
            <motion.button
              className="relative p-2 rounded-lg hover:bg-gray-800 transition-colors"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <Bell className="w-5 h-5" />
              {notifications > 0 && (
                <motion.span
                  className="absolute -top-1 -right-1 w-3 h-3 bg-red-500 rounded-full"
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                />
              )}
            </motion.button>

            {/* Dark Mode Toggle */}
            <motion.button
              className="p-2 rounded-lg hover:bg-gray-800 transition-colors"
              onClick={() => setDarkMode(!darkMode)}
              whileHover={{ rotate: 180 }}
              whileTap={{ scale: 0.95 }}
            >
              {darkMode ? <Eye className="w-5 h-5" /> : <EyeOff className="w-5 h-5" />}
            </motion.button>

            {/* Settings */}
            <motion.button
              className="p-2 rounded-lg hover:bg-gray-800 transition-colors"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <Settings className="w-5 h-5" />
            </motion.button>
          </div>
        </div>
      </header>

      <div className="flex">
        {/* Modern Sidebar */}
        <AnimatePresence>
          {sidebarOpen && (
            <motion.aside
              initial={{ x: -300 }}
              animate={{ x: 0 }}
              exit={{ x: -300 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              className={cn(
                'w-80 h-screen border-r border-gray-800 overflow-y-auto',
                darkMode ? 'bg-gray-900' : 'bg-white'
              )}
            >
              <div className="p-6">
                {/* Dashboard Selector */}
                <div className="mb-8">
                  <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
                    Dashboards
                  </h3>
                  <div className="space-y-2">
                    {subDashboards.map((dashboard) => (
                      <motion.button
                        key={dashboard.id}
                        onClick={() => setSelectedDashboard(dashboard.id)}
                        className={cn(
                          'w-full flex items-center space-x-3 px-4 py-3 rounded-lg text-left transition-all duration-200',
                          selectedDashboard === dashboard.id
                            ? 'bg-gradient-to-r ' + dashboard.color + ' text-white'
                            : darkMode 
                              ? 'hover:bg-gray-800 text-gray-300' 
                              : 'hover:bg-gray-100 text-gray-700'
                        )}
                        whileHover={{ x: 5 }}
                        whileTap={{ scale: 0.98 }}
                      >
                        <dashboard.icon className="w-5 h-5" />
                        <div className="flex-1">
                          <div className="font-medium">{dashboard.name}</div>
                          <div className="text-xs opacity-70">{dashboard.widgets} widgets</div>
                        </div>
                      </motion.button>
                    ))}
                  </div>
                </div>

                {/* Quick Tools */}
                <div>
                  <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
                    Quick Tools
                  </h3>
                  <div className="space-y-2">
                    {tools.filter(tool => tool.status === 'active').map((tool) => (
                      <motion.div
                        key={tool.id}
                        className={cn(
                          'flex items-center space-x-3 p-3 rounded-lg cursor-pointer transition-all duration-200',
                          darkMode ? 'hover:bg-gray-800' : 'hover:bg-gray-100'
                        )}
                        whileHover={{ x: 5 }}
                        whileTap={{ scale: 0.98 }}
                      >
                        <tool.icon className={cn(
                          'w-5 h-5',
                          tool.status === 'active' ? 'text-green-400' : 'text-gray-400'
                        )} />
                        <div className="flex-1">
                          <div className="font-medium text-sm">{tool.name}</div>
                          <div className="text-xs opacity-70">{tool.category}</div>
                        </div>
                        {tool.usage && (
                          <div className={cn('text-xs font-medium', getUsageColor(tool.usage))}>
                            {tool.usage}%
                          </div>
                        )}
                      </motion.div>
                    ))}
                  </div>
                </div>
              </div>
            </motion.aside>
          )}
        </AnimatePresence>

        {/* Main Content Area */}
        <main className="flex-1 overflow-y-auto">
          <div className="p-6">
            {/* System Metrics Overview */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8"
            >
              {[
                { label: 'CPU Usage', value: `${metrics.cpu}%`, icon: Cpu, color: 'from-blue-500 to-cyan-400' },
                { label: 'Memory', value: `${metrics.memory}%`, icon: HardDrive, color: 'from-purple-500 to-pink-400' },
                { label: 'Network', value: `${metrics.network}%`, icon: Wifi, color: 'from-green-500 to-emerald-400' },
                { label: 'Disk', value: `${metrics.disk}%`, icon: Database, color: 'from-orange-500 to-red-400' }
              ].map((metric, index) => (
                <motion.div
                  key={metric.label}
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: index * 0.1 }}
                  className={cn(
                    'p-6 rounded-xl border transition-all duration-200 hover:scale-105',
                    darkMode 
                      ? 'bg-gray-800 border-gray-700' 
                      : 'bg-white border-gray-200'
                  )}
                >
                  <div className="flex items-center justify-between mb-4">
                    <metric.icon className="w-6 h-6 text-blue-400" />
                    <div className={`w-3 h-3 rounded-full bg-gradient-to-r ${metric.color}`}></div>
                  </div>
                  <div className="text-2xl font-bold mb-1">{metric.value}</div>
                  <div className="text-sm text-gray-400">{metric.label}</div>
                </motion.div>
              ))}
            </motion.div>

            {/* Advanced Charts Section */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
              {/* Performance Chart */}
              <motion.div
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                className={cn(
                  'p-6 rounded-xl border',
                  darkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'
                )}
              >
                <h3 className="text-lg font-semibold mb-4 flex items-center">
                  <TrendingUp className="w-5 h-5 mr-2 text-green-400" />
                  Performance Trends
                </h3>
                <div className="h-64 flex items-center justify-center">
                  <div className="text-center">
                    <BarChart3 className="w-16 h-16 mx-auto mb-4 text-blue-400" />
                    <p className="text-gray-400">Real-time performance analytics</p>
                  </div>
                </div>
              </motion.div>

              {/* System Health */}
              <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                className={cn(
                  'p-6 rounded-xl border',
                  darkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'
                )}
              >
                <h3 className="text-lg font-semibold mb-4 flex items-center">
                  <Shield className="w-5 h-5 mr-2 text-green-400" />
                  System Health
                </h3>
                <div className="space-y-4">
                  {[
                    { label: 'System Status', value: metrics.systemHealth, icon: CheckCircle },
                    { label: 'Active Users', value: metrics.activeUsers.toString(), icon: Users },
                    { label: 'Total Requests', value: metrics.totalRequests.toLocaleString(), icon: Activity },
                    { label: 'Uptime', value: metrics.uptime, icon: Clock }
                  ].map((item) => (
                    <div key={item.label} className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <item.icon className="w-4 h-4 text-gray-400" />
                        <span className="text-sm">{item.label}</span>
                      </div>
                      <span className={cn('text-sm font-medium', getHealthColor(item.value))}>
                        {item.value}
                      </span>
                    </div>
                  ))}
                </div>
              </motion.div>
            </div>

            {/* Tools Grid */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-8"
            >
              <h2 className="text-2xl font-bold mb-6">Advanced Tools & Utilities</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {tools.map((tool, index) => (
                  <motion.div
                    key={tool.id}
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: index * 0.1 }}
                    whileHover={{ y: -5, scale: 1.02 }}
                    className={cn(
                      'p-6 rounded-xl border cursor-pointer transition-all duration-200',
                      darkMode 
                        ? 'bg-gray-800 border-gray-700 hover:border-blue-500' 
                        : 'bg-white border-gray-200 hover:border-blue-500'
                    )}
                  >
                    <div className="flex items-center justify-between mb-4">
                      <tool.icon className={cn(
                        'w-8 h-8',
                        tool.status === 'active' ? 'text-green-400' : 'text-gray-400'
                      )} />
                      <div className={cn(
                        'px-2 py-1 rounded text-xs font-medium',
                        tool.status === 'active' 
                          ? 'bg-green-500/20 text-green-400' 
                          : 'bg-gray-500/20 text-gray-400'
                      )}>
                        {tool.status}
                      </div>
                    </div>
                    <h3 className="font-semibold mb-2">{tool.name}</h3>
                    <p className="text-sm text-gray-400 mb-4">{tool.description}</p>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-gray-500">{tool.category}</span>
                      {tool.usage && (
                        <span className={cn('font-medium', getUsageColor(tool.usage))}>
                          {tool.usage}% usage
                        </span>
                      )}
                    </div>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          </div>
        </main>
      </div>
    </div>
  );
};

export default ModernDashboardSystem;
