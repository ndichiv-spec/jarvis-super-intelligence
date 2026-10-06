import React from 'react';
import { motion } from 'framer-motion';
import { Brain, Cpu, MemoryStick, HardDrive, Activity, Settings, MessageSquare, StickyNote, Bell, Code, Home, Wrench } from 'lucide-react';

interface SystemStatus {
  status: 'online' | 'offline' | 'warning';
  uptime: string;
  components: number;
  cpu_usage: number;
  memory_usage: number;
  disk_usage: number;
  network_status: 'connected' | 'disconnected';
  last_update: string;
}

export function JarvisSimpleDashboard({ initialData, healthStatus }: { initialData?: any, healthStatus?: any }) {
  const [systemStatus, setSystemStatus] = React.useState<SystemStatus>({
    status: 'online',
    uptime: new Date().toLocaleTimeString(),
    components: 0,
    cpu_usage: 23,
    memory_usage: 67,
    disk_usage: 45,
    network_status: 'connected',
    last_update: new Date().toISOString(),
  });

  const [activeSection, setActiveSection] = React.useState('overview');

  React.useEffect(() => {
    if (initialData && Array.isArray(initialData)) {
      setSystemStatus(prev => ({
        ...prev,
        components: initialData.length,
        last_update: new Date().toISOString(),
      }));
    }
  }, [initialData]);

  React.useEffect(() => {
    const interval = setInterval(() => {
      setSystemStatus(prev => ({
        ...prev,
        uptime: new Date().toLocaleTimeString(),
        cpu_usage: Math.floor(Math.random() * 30) + 20,
        memory_usage: Math.floor(Math.random() * 20) + 40,
        disk_usage: Math.floor(Math.random() * 10) + 60,
      }));
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  const sidebarItems = [
    { id: 'overview', name: 'Overview', icon: Brain },
    { id: 'chat', name: 'AI Chat', icon: MessageSquare },
    { id: 'notes', name: 'Notes', icon: StickyNote },
    { id: 'reminders', name: 'Reminders', icon: Bell },
    { id: 'codeviewer', name: 'Code Viewer', icon: Code },
    { id: 'smart-home', name: 'Smart Home', icon: Home },
    { id: 'settings', name: 'Settings', icon: Settings },
    { id: 'tools', name: 'Tools', icon: Wrench },
  ];

  const renderActiveSection = () => {
    switch (activeSection) {
      case 'overview':
        return (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-gray-800 p-6 rounded-xl border border-gray-700"
            >
              <div className="flex items-center justify-between mb-4">
                <Cpu className="w-8 h-8 text-blue-400" />
                <span className="text-sm text-gray-400">CPU Usage</span>
              </div>
              <div className="text-2xl font-bold text-white">{systemStatus.cpu_usage}%</div>
              <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
                <div className="bg-blue-400 h-2 rounded-full" style={{ width: `${systemStatus.cpu_usage}%` }} />
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="bg-gray-800 p-6 rounded-xl border border-gray-700"
            >
              <div className="flex items-center justify-between mb-4">
                <MemoryStick className="w-8 h-8 text-green-400" />
                <span className="text-sm text-gray-400">Memory Usage</span>
              </div>
              <div className="text-2xl font-bold text-white">{systemStatus.memory_usage}%</div>
              <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
                <div className="bg-green-400 h-2 rounded-full" style={{ width: `${systemStatus.memory_usage}%` }} />
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="bg-gray-800 p-6 rounded-xl border border-gray-700"
            >
              <div className="flex items-center justify-between mb-4">
                <HardDrive className="w-8 h-8 text-purple-400" />
                <span className="text-sm text-gray-400">Disk Usage</span>
              </div>
              <div className="text-2xl font-bold text-white">{systemStatus.disk_usage}%</div>
              <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
                <div className="bg-purple-400 h-2 rounded-full" style={{ width: `${systemStatus.disk_usage}%` }} />
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="bg-gray-800 p-6 rounded-xl border border-gray-700"
            >
              <div className="flex items-center justify-between mb-4">
                <Activity className="w-8 h-8 text-orange-400" />
                <span className="text-sm text-gray-400">Components</span>
              </div>
              <div className="text-2xl font-bold text-white">{systemStatus.components}</div>
              <div className="text-sm text-gray-400 mt-2">Active systems</div>
            </motion.div>
          </div>
        );
      default:
        return (
          <div className="bg-gray-800 p-8 rounded-xl border border-gray-700">
            <h2 className="text-2xl font-bold text-white mb-4">{sidebarItems.find(item => item.id === activeSection)?.name}</h2>
            <p className="text-gray-400">This section is under development. Check back soon!</p>
          </div>
        );
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 flex">
      {/* Sidebar */}
      <div className="w-64 bg-gray-800 border-r border-gray-700 p-4">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white flex items-center space-x-2">
            <Brain className="w-8 h-8 text-blue-400" />
            <span>JARVIS</span>
          </h1>
          <p className="text-gray-400 text-sm mt-1">AI Dashboard</p>
        </div>

        <nav className="space-y-2">
          {sidebarItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveSection(item.id)}
              className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${
                activeSection === item.id
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-300 hover:bg-gray-700'
              }`}
            >
              <item.icon className="w-5 h-5" />
              <span>{item.name}</span>
            </button>
          ))}
        </nav>
      </div>

      {/* Main Content */}
      <div className="flex-1">
        {/* Header */}
        <div className="bg-gray-800 border-b border-gray-700 px-8 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-white">
                {sidebarItems.find(item => item.id === activeSection)?.name}
              </h2>
              <p className="text-gray-400 text-sm">
                Status: {systemStatus.status} | Uptime: {systemStatus.uptime}
              </p>
            </div>
            <div className="flex items-center space-x-4">
              <div className="text-sm text-gray-400">
                Components: {systemStatus.components}
              </div>
              <div className={`w-3 h-3 rounded-full ${
                systemStatus.status === 'online' ? 'bg-green-400' :
                systemStatus.status === 'warning' ? 'bg-yellow-400' : 'bg-red-400'
              }`} />
            </div>
          </div>
        </div>

        {/* Content Area */}
        <div className="p-8">
          {renderActiveSection()}
        </div>
      </div>
    </div>
  );
}
