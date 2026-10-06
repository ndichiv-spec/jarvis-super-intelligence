'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Settings, User, Bell, Shield, Globe, Palette, Monitor, 
  Volume2, Mic, Wifi, Database, Cloud, Lock, Eye, EyeOff,
  ChevronRight, Save, RefreshCw, Trash2, Download, Upload,
  ToggleLeft, ToggleRight, Zap, Cpu, HardDrive, Activity
} from 'lucide-react';

interface SettingSection {
  id: string;
  name: string;
  icon: any;
  description: string;
}

const SECTIONS: SettingSection[] = [
  { id: 'general', name: 'General', icon: Settings, description: 'Basic app settings' },
  { id: 'account', name: 'Account', icon: User, description: 'User profile and security' },
  { id: 'notifications', name: 'Notifications', icon: Bell, description: 'Alert preferences' },
  { id: 'privacy', name: 'Privacy', icon: Shield, description: 'Data and privacy controls' },
  { id: 'appearance', name: 'Appearance', icon: Palette, description: 'Theme and display' },
  { id: 'audio', name: 'Audio', icon: Volume2, description: 'Sound and voice settings' },
  { id: 'network', name: 'Network', icon: Wifi, description: 'Connection settings' },
  { id: 'storage', name: 'Storage', icon: Database, description: 'Data management' },
  { id: 'advanced', name: 'Advanced', icon: Cpu, description: 'System configuration' }
];

export default function JarvisSettings() {
  const [selectedSection, setSelectedSection] = useState('general');
  const [settings, setSettings] = useState({
    darkMode: true,
    notifications: true,
    soundEnabled: true,
    autoSave: true,
    voiceActivation: false,
    encryption: true,
    autoUpdate: true,
    logging: true,
    performanceMode: 'balanced',
    language: 'en',
    timezone: 'UTC'
  });

  const updateSetting = (key: string, value: any) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const renderSection = () => {
    switch (selectedSection) {
      case 'general':
        return (
          <div className="space-y-6">
            <div className="bg-gray-800 p-6 rounded-xl">
              <h3 className="text-xl font-bold mb-4">General Settings</h3>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-semibold">Dark Mode</div>
                    <div className="text-sm text-gray-400">Enable dark theme</div>
                  </div>
                  <button
                    onClick={() => updateSetting('darkMode', !settings.darkMode)}
                    className={`w-12 h-6 rounded-full ${settings.darkMode ? 'bg-blue-600' : 'bg-gray-600'} relative`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-all ${settings.darkMode ? 'left-6' : 'left-0.5'}`} />
                  </button>
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-semibold">Auto Save</div>
                    <div className="text-sm text-gray-400">Automatically save changes</div>
                  </div>
                  <button
                    onClick={() => updateSetting('autoSave', !settings.autoSave)}
                    className={`w-12 h-6 rounded-full ${settings.autoSave ? 'bg-blue-600' : 'bg-gray-600'} relative`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-all ${settings.autoSave ? 'left-6' : 'left-0.5'}`} />
                  </button>
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-semibold">Auto Update</div>
                    <div className="text-sm text-gray-400">Update automatically</div>
                  </div>
                  <button
                    onClick={() => updateSetting('autoUpdate', !settings.autoUpdate)}
                    className={`w-12 h-6 rounded-full ${settings.autoUpdate ? 'bg-blue-600' : 'bg-gray-600'} relative`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-all ${settings.autoUpdate ? 'left-6' : 'left-0.5'}`} />
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      case 'appearance':
        return (
          <div className="space-y-6">
            <div className="bg-gray-800 p-6 rounded-xl">
              <h3 className="text-xl font-bold mb-4">Appearance</h3>
              <div className="grid grid-cols-3 gap-4">
                {['Dark', 'Light', 'Neon'].map((theme) => (
                  <motion.button
                    key={theme}
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    className={`p-4 rounded-xl border-2 ${
                      settings.darkMode && theme === 'Dark' ? 'border-blue-500' : 'border-gray-700'
                    }`}
                  >
                    <div className={`w-full h-20 rounded-lg mb-2 ${
                      theme === 'Dark' ? 'bg-gray-900' : 
                      theme === 'Light' ? 'bg-gray-100' : 'bg-purple-900'
                    }`}></div>
                    <div className="text-sm font-semibold">{theme}</div>
                  </motion.button>
                ))}
              </div>
            </div>
          </div>
        );
      case 'audio':
        return (
          <div className="space-y-6">
            <div className="bg-gray-800 p-6 rounded-xl">
              <h3 className="text-xl font-bold mb-4">Audio Settings</h3>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-semibold">Sound Effects</div>
                    <div className="text-sm text-gray-400">Enable UI sounds</div>
                  </div>
                  <button
                    onClick={() => updateSetting('soundEnabled', !settings.soundEnabled)}
                    className={`w-12 h-6 rounded-full ${settings.soundEnabled ? 'bg-blue-600' : 'bg-gray-600'} relative`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-all ${settings.soundEnabled ? 'left-6' : 'left-0.5'}`} />
                  </button>
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-semibold">Voice Activation</div>
                    <div className="text-sm text-gray-400">Enable voice commands</div>
                  </div>
                  <button
                    onClick={() => updateSetting('voiceActivation', !settings.voiceActivation)}
                    className={`w-12 h-6 rounded-full ${settings.voiceActivation ? 'bg-blue-600' : 'bg-gray-600'} relative`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-all ${settings.voiceActivation ? 'left-6' : 'left-0.5'}`} />
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      case 'storage':
        return (
          <div className="space-y-6">
            <div className="bg-gray-800 p-6 rounded-xl">
              <h3 className="text-xl font-bold mb-4">Storage Management</h3>
              <div className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-gray-700 rounded-lg">
                  <div className="flex items-center">
                    <Database className="w-8 h-8 mr-3 text-blue-400" />
                    <div>
                      <div className="font-semibold">Database</div>
                      <div className="text-sm text-gray-400">245 MB used</div>
                    </div>
                  </div>
                  <button className="p-2 hover:bg-gray-600 rounded-lg">
                    <RefreshCw className="w-5 h-5" />
                  </button>
                </div>
                <div className="flex items-center justify-between p-4 bg-gray-700 rounded-lg">
                  <div className="flex items-center">
                    <Cloud className="w-8 h-8 mr-3 text-purple-400" />
                    <div>
                      <div className="font-semibold">Cache</div>
                      <div className="text-sm text-gray-400">128 MB used</div>
                    </div>
                  </div>
                  <button className="p-2 hover:bg-gray-600 rounded-lg">
                    <Trash2 className="w-5 h-5 text-red-400" />
                  </button>
                </div>
                <div className="flex items-center justify-between p-4 bg-gray-700 rounded-lg">
                  <div className="flex items-center">
                    <HardDrive className="w-8 h-8 mr-3 text-green-400" />
                    <div>
                      <div className="font-semibold">Logs</div>
                      <div className="text-sm text-gray-400">64 MB used</div>
                    </div>
                  </div>
                  <button className="p-2 hover:bg-gray-600 rounded-lg">
                    <Download className="w-5 h-5" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      case 'advanced':
        return (
          <div className="space-y-6">
            <div className="bg-gray-800 p-6 rounded-xl">
              <h3 className="text-xl font-bold mb-4">Advanced Settings</h3>
              <div className="space-y-4">
                <div>
                  <div className="font-semibold mb-2">Performance Mode</div>
                  <select
                    value={settings.performanceMode}
                    onChange={(e) => updateSetting('performanceMode', e.target.value)}
                    className="w-full bg-gray-700 p-3 rounded-lg"
                  >
                    <option value="balanced">Balanced</option>
                    <option value="performance">Performance</option>
                    <option value="power">Power Saving</option>
                  </select>
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-semibold">Encryption</div>
                    <div className="text-sm text-gray-400">End-to-end encryption</div>
                  </div>
                  <button
                    onClick={() => updateSetting('encryption', !settings.encryption)}
                    className={`w-12 h-6 rounded-full ${settings.encryption ? 'bg-blue-600' : 'bg-gray-600'} relative`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-all ${settings.encryption ? 'left-6' : 'left-0.5'}`} />
                  </button>
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-semibold">Logging</div>
                    <div className="text-sm text-gray-400">Enable system logging</div>
                  </div>
                  <button
                    onClick={() => updateSetting('logging', !settings.logging)}
                    className={`w-12 h-6 rounded-full ${settings.logging ? 'bg-blue-600' : 'bg-gray-600'} relative`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-all ${settings.logging ? 'left-6' : 'left-0.5'}`} />
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      default:
        return (
          <div className="bg-gray-800 p-6 rounded-xl">
            <h3 className="text-xl font-bold mb-4">{SECTIONS.find(s => s.id === selectedSection)?.name}</h3>
            <p className="text-gray-400">Settings for this section coming soon.</p>
          </div>
        );
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 text-white p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <h1 className="text-4xl font-bold mb-2 flex items-center">
            <Settings className="mr-3 w-10 h-10 text-blue-400" />
            JARVIS Settings
          </h1>
          <p className="text-gray-400">Configure your JARVIS experience</p>
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Sidebar */}
          <div className="lg:col-span-1">
            <div className="bg-gray-800/50 backdrop-blur-xl p-4 rounded-xl border border-gray-700/50">
              {SECTIONS.map((section) => {
                const Icon = section.icon;
                return (
                  <motion.button
                    key={section.id}
                    whileHover={{ x: 5 }}
                    onClick={() => setSelectedSection(section.id)}
                    className={`w-full flex items-center p-3 rounded-lg mb-2 transition-colors ${
                      selectedSection === section.id 
                        ? 'bg-blue-600' 
                        : 'hover:bg-gray-700'
                    }`}
                  >
                    <Icon className="w-5 h-5 mr-3" />
                    <div className="text-left">
                      <div className="font-semibold">{section.name}</div>
                      <div className="text-xs text-gray-400">{section.description}</div>
                    </div>
                    <ChevronRight className="w-4 h-4 ml-auto" />
                  </motion.button>
                );
              })}
            </div>
          </div>

          {/* Main Content */}
          <div className="lg:col-span-3">
            <motion.div
              key={selectedSection}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3 }}
            >
              {renderSection()}
            </motion.div>

            {/* Save Button */}
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="mt-6 w-full bg-gradient-to-r from-blue-600 to-purple-600 p-4 rounded-xl font-semibold flex items-center justify-center"
            >
              <Save className="w-5 h-5 mr-2" />
              Save Changes
            </motion.button>
          </div>
        </div>
      </div>
    </div>
  );
}
