import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Wrench, Activity, Terminal, Code, Database, Cloud, Calculator, Clock, Timer, Search, Filter, Download, Upload } from 'lucide-react';

interface Tool {
  id: string;
  name: string;
  description: string;
  icon: any;
  category: string;
  status: 'active' | 'available' | 'beta';
}

export function JarvisTools() {
  const [tools] = useState<Tool[]>([
    {
      id: '1',
      name: 'System Monitor',
      description: 'CPU, memory, disk usage',
      icon: Activity,
      category: 'System',
      status: 'active'
    },
    {
      id: '2',
      name: 'Terminal',
      description: 'Command line interface',
      icon: Terminal,
      category: 'Development',
      status: 'active'
    },
    {
      id: '3',
      name: 'Code Editor',
      description: 'Advanced code editing',
      icon: Code,
      category: 'Development',
      status: 'active'
    },
    {
      id: '4',
      name: 'Database Manager',
      description: 'Database administration',
      icon: Database,
      category: 'Data',
      status: 'active'
    },
    {
      id: '5',
      name: 'Cloud Storage',
      description: 'File synchronization',
      icon: Cloud,
      category: 'Storage',
      status: 'available'
    },
    {
      id: '6',
      name: 'Calculator',
      description: 'Advanced calculations',
      icon: Calculator,
      category: 'Utility',
      status: 'active'
    },
    {
      id: '7',
      name: 'Timer',
      description: 'Countdown and stopwatch',
      icon: Timer,
      category: 'Utility',
      status: 'active'
    },
    {
      id: '8',
      name: 'File Search',
      description: 'Advanced file search',
      icon: Search,
      category: 'Utility',
      status: 'beta'
    },
    {
      id: '9',
      name: 'Data Filter',
      description: 'Data filtering tools',
      icon: Filter,
      category: 'Data',
      status: 'available'
    },
    {
      id: '10',
      name: 'File Transfer',
      description: 'Upload/download manager',
      icon: Upload,
      category: 'Network',
      status: 'active'
    }
  ]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'bg-green-500';
      case 'available': return 'bg-blue-500';
      case 'beta': return 'bg-yellow-500';
      default: return 'bg-gray-500';
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'active': return 'ACTIVE';
      case 'available': return 'AVAILABLE';
      case 'beta': return 'BETA';
      default: return 'UNKNOWN';
    }
  };

  return (
    <div className="h-full flex flex-col bg-gray-800 rounded-xl">
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center space-x-2">
          <Wrench className="w-6 h-6 text-purple-400" />
          <h2 className="text-xl font-semibold text-white">Tools</h2>
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {tools.map((tool) => (
            <motion.div
              key={tool.id}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: parseInt(tool.id) * 0.05 }}
              className="bg-gray-700 p-4 rounded-lg hover:bg-gray-600 transition-colors cursor-pointer"
            >
              <div className="flex items-center justify-between mb-3">
                <tool.icon className="w-6 h-6 text-blue-400" />
                <span className={`px-2 py-1 rounded text-xs text-white ${getStatusColor(tool.status)}`}>
                  {getStatusText(tool.status)}
                </span>
              </div>
              <h3 className="font-medium text-white mb-1">{tool.name}</h3>
              <p className="text-sm text-gray-400 mb-2">{tool.description}</p>
              <div className="text-xs text-gray-500">
                Category: {tool.category}
              </div>
            </motion.div>
          ))}
        </div>
        
        <div className="mt-6 p-4 bg-gray-700 rounded-lg">
          <h3 className="text-lg font-semibold text-white mb-3">Quick Actions</h3>
          <div className="grid grid-cols-2 gap-2">
            <button className="bg-blue-500 hover:bg-blue-600 text-white px-3 py-2 rounded text-sm transition-colors flex items-center justify-center space-x-1">
              <Terminal className="w-3 h-3" />
              <span>Open Terminal</span>
            </button>
            <button className="bg-green-500 hover:bg-green-600 text-white px-3 py-2 rounded text-sm transition-colors flex items-center justify-center space-x-1">
              <Activity className="w-3 h-3" />
              <span>System Monitor</span>
            </button>
            <button className="bg-purple-500 hover:bg-purple-600 text-white px-3 py-2 rounded text-sm transition-colors flex items-center justify-center space-x-1">
              <Code className="w-3 h-3" />
              <span>Code Editor</span>
            </button>
            <button className="bg-orange-500 hover:bg-orange-600 text-white px-3 py-2 rounded text-sm transition-colors flex items-center justify-center space-x-1">
              <Database className="w-3 h-3" />
              <span>Database</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
