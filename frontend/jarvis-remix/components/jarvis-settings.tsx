import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Settings, User, Shield, Bell, Palette, Globe, Database } from 'lucide-react';

interface Setting {
  id: string;
  name: string;
  description: string;
  icon: any;
  enabled: boolean;
}

export function JarvisSettings() {
  const [settings, setSettings] = useState<Setting[]>([
    {
      id: '1',
      name: 'Notifications',
      description: 'Enable system notifications and alerts',
      icon: Bell,
      enabled: true
    },
    {
      id: '2',
      name: 'Dark Mode',
      description: 'Use dark theme for the interface',
      icon: Palette,
      enabled: true
    },
    {
      id: '3',
      name: 'Auto-save',
      description: 'Automatically save work progress',
      icon: Database,
      enabled: true
    },
    {
      id: '4',
      name: 'Security Mode',
      description: 'Enhanced security features',
      icon: Shield,
      enabled: false
    },
    {
      id: '5',
      name: 'Language',
      description: 'Interface language preference',
      icon: Globe,
      enabled: true
    },
    {
      id: '6',
      name: 'User Profile',
      description: 'Manage your profile settings',
      icon: User,
      enabled: true
    }
  ]);

  const toggleSetting = (id: string) => {
    setSettings(prev => prev.map(setting =>
      setting.id === id ? { ...setting, enabled: !setting.enabled } : setting
    ));
  };

  return (
    <div className="h-full flex flex-col bg-gray-800 rounded-xl">
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center space-x-2">
          <Settings className="w-6 h-6 text-orange-400" />
          <h2 className="text-xl font-semibold text-white">Settings</h2>
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4">
        <div className="space-y-4">
          {settings.map((setting) => (
            <motion.div
              key={setting.id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: parseInt(setting.id) * 0.1 }}
              className="bg-gray-700 p-4 rounded-lg hover:bg-gray-600 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <setting.icon className="w-5 h-5 text-blue-400" />
                  <div>
                    <h3 className="font-medium text-white">{setting.name}</h3>
                    <p className="text-sm text-gray-400">{setting.description}</p>
                  </div>
                </div>
                <button
                  onClick={() => toggleSetting(setting.id)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    setting.enabled ? 'bg-blue-500' : 'bg-gray-500'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      setting.enabled ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
            </motion.div>
          ))}
        </div>
        
        <div className="mt-6 p-4 bg-gray-700 rounded-lg">
          <h3 className="text-lg font-semibold text-white mb-3">System Information</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-400">JARVIS Version</span>
              <span className="text-white">3.0.0</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Backend Status</span>
              <span className="text-green-400">Connected</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Last Update</span>
              <span className="text-white">2 hours ago</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Storage Used</span>
              <span className="text-white">2.4 GB</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
