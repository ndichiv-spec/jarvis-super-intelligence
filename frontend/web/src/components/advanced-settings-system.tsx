'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Settings,
  User,
  Shield,
  Bell,
  Monitor,
  Database,
  Globe,
  Zap,
  Brain,
  Cpu,
  HardDrive,
  Wifi,
  Lock,
  Unlock,
  Eye,
  EyeOff,
  Volume2,
  VolumeX,
  Mic,
  MicOff,
  Camera,
  CameraOff,
  Download,
  Upload,
  RefreshCw,
  Save,
  X,
  Check,
  AlertTriangle,
  Info,
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  ChevronRight,
  Plus,
  Minus,
  Trash2,
  Copy,
  Move,
  GripVertical,
  Search,
  Filter,
  MoreVertical,
  Terminal,
  Code,
  FileText,
  Image,
  Video,
  Music,
  FolderOpen,
  Calendar,
  Clock,
  Timer,
  Target,
  Award,
  Star,
  Heart,
  MessageSquare,
  Share2,
  Link,
  ExternalLink,
  Github,
  Twitter,
  Linkedin,
  Mail,
  Phone,
  MapPin,
  Sun,
  Moon,
  Cloud,
  CloudRain,
  CloudSnow,
  Battery,
  BatteryCharging,
  Power,
  PowerOff,
  SkipForward,
  SkipBack,
  Rewind,
  FastForward,
  ChevronFirst,
  ChevronLast,
  ArrowUp,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  ArrowUpLeft,
  ArrowDownRight,
  ArrowDownLeft,
  MoveUp,
  MoveDown,
  MoveLeft,
  MoveRight,
  MoveDiagonal,
  MoveDiagonal2,
  Expand,
  Shrink,
  Fullscreen,
  Scan,
  ScanLine,
  ScanEye,
  ScanQrCode,
  ScanBarcode,
  ScanFace,
  UserPlus,
  UserMinus,
  Users,
  Key,
  KeyRound,
  Fingerprint,
  IdCard,
  CreditCard,
  Smartphone,
  Tablet,
  Server,
  Tv,
  Gamepad2,
  Square,
  Circle,
  Hexagon,
  Pentagon,
  Octagon,
  Star as StarIcon,
  Heart as HeartIcon,
  Diamond,
  Club,
  Spade,
  Music as MusicIcon,
  Music2,
  Music3,
  Music4,
  Play,
  Pause,
  Square as SquareIcon,
  Circle as CircleIcon,
  Triangle as TriangleIcon,
  Pentagon as PentagonIcon,
  Hexagon as HexagonIcon,
  Octagon as OctagonIcon,
  Star as StarIcon2,
  Heart as HeartIcon2,
  Diamond as DiamondIcon,
  Club as ClubIcon,
  Spade as SpadeIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface SettingSection {
  id: string;
  name: string;
  description: string;
  icon: React.ComponentType<any>;
  color: string;
  settings: Setting[];
}

interface Setting {
  id: string;
  name: string;
  description: string;
  type: 'boolean' | 'string' | 'number' | 'select' | 'range' | 'file' | 'color' | 'password' | 'array';
  value: any;
  options?: string[];
  min?: number;
  max?: number;
  step?: number;
  category?: string;
  permissions?: string[];
  dependencies?: string[];
  validation?: (value: any) => boolean | string;
  placeholder?: string;
  help?: string;
  warning?: string;
  danger?: boolean;
}

interface UserPreferences {
  theme: 'dark' | 'light' | 'auto';
  language: string;
  timezone: string;
  dateFormat: string;
  timeFormat: string;
  currency: string;
  notifications: {
    email: boolean;
    push: boolean;
    sms: boolean;
    desktop: boolean;
  };
  privacy: {
    analytics: boolean;
    crashReports: boolean;
    usageData: boolean;
    location: boolean;
  };
  accessibility: {
    highContrast: boolean;
    largeText: boolean;
    reducedMotion: boolean;
    screenReader: boolean;
    keyboardNavigation: boolean;
  };
}

interface SystemConfiguration {
  performance: {
    maxMemory: number;
    maxCpu: number;
    maxThreads: number;
    cacheSize: number;
    autoCleanup: boolean;
    cleanupInterval: number;
  };
  security: {
    encryptionLevel: string;
    sessionTimeout: number;
    twoFactorAuth: boolean;
    apiRateLimit: number;
    allowedOrigins: string[];
    blockedIps: string[];
  };
  network: {
    proxyEnabled: boolean;
    proxyHost: string;
    proxyPort: number;
    proxyUsername: string;
    proxyPassword: string;
    dnsServers: string[];
    vpnEnabled: boolean;
    vpnConfig: string;
  };
  storage: {
    primaryPath: string;
    backupPath: string;
    maxStorage: number;
    compressionEnabled: boolean;
    encryptionEnabled: boolean;
    autoBackup: boolean;
    backupInterval: number;
  };
}

export const AdvancedSettingsSystem: React.FC = () => {
  const [activeSection, setActiveSection] = useState('general');
  const [searchQuery, setSearchQuery] = useState('');
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  const [userPreferences, setUserPreferences] = useState<UserPreferences>({
    theme: 'dark',
    language: 'en',
    timezone: 'UTC',
    dateFormat: 'MM/DD/YYYY',
    timeFormat: '12h',
    currency: 'USD',
    notifications: {
      email: true,
      push: true,
      sms: false,
      desktop: true
    },
    privacy: {
      analytics: false,
      crashReports: true,
      usageData: false,
      location: false
    },
    accessibility: {
      highContrast: false,
      largeText: false,
      reducedMotion: false,
      screenReader: false,
      keyboardNavigation: true
    }
  });

  const [systemConfiguration, setSystemConfiguration] = useState<SystemConfiguration>({
    performance: {
      maxMemory: 4096,
      maxCpu: 80,
      maxThreads: 8,
      cacheSize: 1024,
      autoCleanup: true,
      cleanupInterval: 3600
    },
    security: {
      encryptionLevel: 'AES-256',
      sessionTimeout: 3600,
      twoFactorAuth: false,
      apiRateLimit: 1000,
      allowedOrigins: ['http://localhost:3000'],
      blockedIps: []
    },
    network: {
      proxyEnabled: false,
      proxyHost: '',
      proxyPort: 8080,
      proxyUsername: '',
      proxyPassword: '',
      dnsServers: ['8.8.8.8', '8.8.4.4'],
      vpnEnabled: false,
      vpnConfig: ''
    },
    storage: {
      primaryPath: '/data/jarvis',
      backupPath: '/backup/jarvis',
      maxStorage: 10240,
      compressionEnabled: true,
      encryptionEnabled: true,
      autoBackup: true,
      backupInterval: 86400
    }
  });

  const settingSections: SettingSection[] = [
    {
      id: 'general',
      name: 'General',
      description: 'Basic settings and preferences',
      icon: Settings,
      color: 'from-blue-500 to-cyan-400',
      settings: [
        {
          id: 'theme',
          name: 'Theme',
          description: 'Choose your preferred theme',
          type: 'select',
          value: userPreferences.theme,
          options: ['dark', 'light', 'auto'],
          category: 'appearance'
        },
        {
          id: 'language',
          name: 'Language',
          description: 'Select your preferred language',
          type: 'select',
          value: userPreferences.language,
          options: ['en', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'ko', 'zh'],
          category: 'localization'
        },
        {
          id: 'timezone',
          name: 'Timezone',
          description: 'Set your timezone',
          type: 'select',
          value: userPreferences.timezone,
          options: ['UTC', 'EST', 'CST', 'MST', 'PST', 'GMT', 'CET', 'IST', 'JST', 'AEST'],
          category: 'localization'
        }
      ]
    },
    {
      id: 'notifications',
      name: 'Notifications',
      description: 'Manage notification preferences',
      icon: Bell,
      color: 'from-purple-500 to-pink-400',
      settings: [
        {
          id: 'email-notifications',
          name: 'Email Notifications',
          description: 'Receive notifications via email',
          type: 'boolean',
          value: userPreferences.notifications.email,
          category: 'communication'
        },
        {
          id: 'push-notifications',
          name: 'Push Notifications',
          description: 'Receive push notifications',
          type: 'boolean',
          value: userPreferences.notifications.push,
          category: 'communication'
        },
        {
          id: 'desktop-notifications',
          name: 'Monitor Notifications',
          description: 'Show desktop notifications',
          type: 'boolean',
          value: userPreferences.notifications.desktop,
          category: 'communication'
        }
      ]
    },
    {
      id: 'privacy',
      name: 'Privacy',
      description: 'Privacy and data protection settings',
      icon: Shield,
      color: 'from-green-500 to-emerald-400',
      settings: [
        {
          id: 'analytics',
          name: 'Analytics',
          description: 'Help improve Jarvis with usage analytics',
          type: 'boolean',
          value: userPreferences.privacy.analytics,
          category: 'data-collection',
          warning: 'This will share anonymous usage data'
        },
        {
          id: 'crash-reports',
          name: 'Crash Reports',
          description: 'Automatically send crash reports',
          type: 'boolean',
          value: userPreferences.privacy.crashReports,
          category: 'data-collection'
        },
        {
          id: 'usage-data',
          name: 'Usage Data',
          description: 'Share usage data for improvements',
          type: 'boolean',
          value: userPreferences.privacy.usageData,
          category: 'data-collection',
          warning: 'This may include sensitive information'
        }
      ]
    },
    {
      id: 'accessibility',
      name: 'Accessibility',
      description: 'Accessibility and ease of use settings',
      icon: User,
      color: 'from-yellow-500 to-amber-400',
      settings: [
        {
          id: 'high-contrast',
          name: 'High Contrast',
          description: 'Increase contrast for better visibility',
          type: 'boolean',
          value: userPreferences.accessibility.highContrast,
          category: 'visual'
        },
        {
          id: 'large-text',
          name: 'Large Text',
          description: 'Increase text size for better readability',
          type: 'boolean',
          value: userPreferences.accessibility.largeText,
          category: 'visual'
        },
        {
          id: 'reduced-motion',
          name: 'Reduced Motion',
          description: 'Reduce animations and transitions',
          type: 'boolean',
          value: userPreferences.accessibility.reducedMotion,
          category: 'visual'
        },
        {
          id: 'keyboard-navigation',
          name: 'Keyboard Navigation',
          description: 'Enable keyboard shortcuts and navigation',
          type: 'boolean',
          value: userPreferences.accessibility.keyboardNavigation,
          category: 'interaction'
        }
      ]
    },
    {
      id: 'performance',
      name: 'Performance',
      description: 'System performance and resource settings',
      icon: Zap,
      color: 'from-red-500 to-orange-400',
      settings: [
        {
          id: 'max-memory',
          name: 'Max Memory (MB)',
          description: 'Maximum memory allocation',
          type: 'range',
          value: systemConfiguration.performance.maxMemory,
          min: 512,
          max: 16384,
          step: 512,
          category: 'resources',
          danger: true
        },
        {
          id: 'max-cpu',
          name: 'Max CPU Usage (%)',
          description: 'Maximum CPU usage percentage',
          type: 'range',
          value: systemConfiguration.performance.maxCpu,
          min: 10,
          max: 100,
          step: 5,
          category: 'resources'
        },
        {
          id: 'max-threads',
          name: 'Max Threads',
          description: 'Maximum number of threads',
          type: 'range',
          value: systemConfiguration.performance.maxThreads,
          min: 1,
          max: 32,
          step: 1,
          category: 'resources'
        },
        {
          id: 'auto-cleanup',
          name: 'Auto Cleanup',
          description: 'Automatically clean up temporary files',
          type: 'boolean',
          value: systemConfiguration.performance.autoCleanup,
          category: 'maintenance'
        }
      ]
    },
    {
      id: 'security',
      name: 'Security',
      description: 'Security and authentication settings',
      icon: Lock,
      color: 'from-indigo-500 to-purple-400',
      settings: [
        {
          id: 'encryption-level',
          name: 'Encryption Level',
          description: 'Data encryption strength',
          type: 'select',
          value: systemConfiguration.security.encryptionLevel,
          options: ['AES-128', 'AES-256', 'AES-512'],
          category: 'encryption'
        },
        {
          id: 'session-timeout',
          name: 'Session Timeout (seconds)',
          description: 'Automatic session timeout duration',
          type: 'range',
          value: systemConfiguration.security.sessionTimeout,
          min: 300,
          max: 86400,
          step: 300,
          category: 'authentication'
        },
        {
          id: 'two-factor-auth',
          name: 'Two-Factor Authentication',
          description: 'Enable two-factor authentication',
          type: 'boolean',
          value: systemConfiguration.security.twoFactorAuth,
          category: 'authentication'
        },
        {
          id: 'api-rate-limit',
          name: 'API Rate Limit',
          description: 'Maximum API requests per minute',
          type: 'range',
          value: systemConfiguration.security.apiRateLimit,
          min: 100,
          max: 10000,
          step: 100,
          category: 'api'
        }
      ]
    },
    {
      id: 'network',
      name: 'Network',
      description: 'Network and connectivity settings',
      icon: Wifi,
      color: 'from-teal-500 to-cyan-400',
      settings: [
        {
          id: 'proxy-enabled',
          name: 'Proxy Enabled',
          description: 'Enable proxy server',
          type: 'boolean',
          value: systemConfiguration.network.proxyEnabled,
          category: 'proxy'
        },
        {
          id: 'proxy-host',
          name: 'Proxy Host',
          description: 'Proxy server hostname',
          type: 'string',
          value: systemConfiguration.network.proxyHost,
          placeholder: 'proxy.example.com',
          category: 'proxy',
          dependencies: ['proxy-enabled']
        },
        {
          id: 'proxy-port',
          name: 'Proxy Port',
          description: 'Proxy server port',
          type: 'number',
          value: systemConfiguration.network.proxyPort,
          min: 1,
          max: 65535,
          category: 'proxy',
          dependencies: ['proxy-enabled']
        }
      ]
    },
    {
      id: 'storage',
      name: 'Storage',
      description: 'Storage and backup settings',
      icon: HardDrive,
      color: 'from-orange-500 to-red-400',
      settings: [
        {
          id: 'primary-path',
          name: 'Primary Storage Path',
          description: 'Main storage directory',
          type: 'string',
          value: systemConfiguration.storage.primaryPath,
          category: 'paths',
          danger: true
        },
        {
          id: 'backup-path',
          name: 'Backup Path',
          description: 'Backup storage directory',
          type: 'string',
          value: systemConfiguration.storage.backupPath,
          category: 'paths'
        },
        {
          id: 'max-storage',
          name: 'Max Storage (GB)',
          description: 'Maximum storage allocation',
          type: 'range',
          value: systemConfiguration.storage.maxStorage,
          min: 1,
          max: 10240,
          step: 1,
          category: 'limits'
        },
        {
          id: 'auto-backup',
          name: 'Auto Backup',
          description: 'Automatically backup data',
          type: 'boolean',
          value: systemConfiguration.storage.autoBackup,
          category: 'backup'
        },
        {
          id: 'encryption-enabled',
          name: 'Storage Encryption',
          description: 'Encrypt stored data',
          type: 'boolean',
          value: systemConfiguration.storage.encryptionEnabled,
          category: 'security'
        }
      ]
    }
  ];

  const filteredSections = settingSections.filter(section => {
    const hasMatchingSettings = section.settings.some(setting =>
      setting.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      setting.description.toLowerCase().includes(searchQuery.toLowerCase())
    );
    return hasMatchingSettings || searchQuery === '';
  });

  const updateSetting = (sectionId: string, settingId: string, value: any) => {
    setHasUnsavedChanges(true);
    
    if (sectionId === 'general') {
      setUserPreferences(prev => ({
        ...prev,
        [settingId]: value
      }));
    } else if (sectionId === 'notifications') {
      setUserPreferences(prev => ({
        ...prev,
        notifications: {
          ...prev.notifications,
          [settingId]: value
        }
      }));
    } else if (sectionId === 'privacy') {
      setUserPreferences(prev => ({
        ...prev,
        privacy: {
          ...prev.privacy,
          [settingId]: value
        }
      }));
    } else if (sectionId === 'accessibility') {
      setUserPreferences(prev => ({
        ...prev,
        accessibility: {
          ...prev.accessibility,
          [settingId]: value
        }
      }));
    } else if (sectionId === 'performance') {
      setSystemConfiguration(prev => ({
        ...prev,
        performance: {
          ...prev.performance,
          [settingId]: value
        }
      }));
    } else if (sectionId === 'security') {
      setSystemConfiguration(prev => ({
        ...prev,
        security: {
          ...prev.security,
          [settingId]: value
        }
      }));
    } else if (sectionId === 'network') {
      setSystemConfiguration(prev => ({
        ...prev,
        network: {
          ...prev.network,
          [settingId]: value
        }
      }));
    } else if (sectionId === 'storage') {
      setSystemConfiguration(prev => ({
        ...prev,
        storage: {
          ...prev.storage,
          [settingId]: value
        }
      }));
    }
  };

  const saveSettings = async () => {
    setIsSaving(true);
    setSaveStatus('saving');
    
    // Simulate saving settings
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    setHasUnsavedChanges(false);
    setIsSaving(false);
    setSaveStatus('saved');
    
    setTimeout(() => {
      setSaveStatus('idle');
    }, 3000);
  };

  const resetSettings = () => {
    if (confirm('Are you sure you want to reset all settings to defaults?')) {
      setUserPreferences({
        theme: 'dark',
        language: 'en',
        timezone: 'UTC',
        dateFormat: 'MM/DD/YYYY',
        timeFormat: '12h',
        currency: 'USD',
        notifications: {
          email: true,
          push: true,
          sms: false,
          desktop: true
        },
        privacy: {
          analytics: false,
          crashReports: true,
          usageData: false,
          location: false
        },
        accessibility: {
          highContrast: false,
          largeText: false,
          reducedMotion: false,
          screenReader: false,
          keyboardNavigation: true
        }
      });
      
      setSystemConfiguration({
        performance: {
          maxMemory: 4096,
          maxCpu: 80,
          maxThreads: 8,
          cacheSize: 1024,
          autoCleanup: true,
          cleanupInterval: 3600
        },
        security: {
          encryptionLevel: 'AES-256',
          sessionTimeout: 3600,
          twoFactorAuth: false,
          apiRateLimit: 1000,
          allowedOrigins: ['http://localhost:3000'],
          blockedIps: []
        },
        network: {
          proxyEnabled: false,
          proxyHost: '',
          proxyPort: 8080,
          proxyUsername: '',
          proxyPassword: '',
          dnsServers: ['8.8.8.8', '8.8.4.4'],
          vpnEnabled: false,
          vpnConfig: ''
        },
        storage: {
          primaryPath: '/data/jarvis',
          backupPath: '/backup/jarvis',
          maxStorage: 10240,
          compressionEnabled: true,
          encryptionEnabled: true,
          autoBackup: true,
          backupInterval: 86400
        }
      });
      
      setHasUnsavedChanges(true);
    }
  };

  const renderSetting = (sectionId: string, setting: Setting) => {
    const isDisabled = setting.dependencies && setting.dependencies.some(dep => {
      const [section, settingId] = dep.split('-');
      // Check if dependency is satisfied
      return false; // Simplified for now
    });

    return (
      <motion.div
        key={setting.id}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className={cn(
          'p-4 rounded-lg border transition-all duration-200',
          setting.danger ? 'border-red-500/30 bg-red-500/10' : 'border-gray-700 bg-gray-800/50',
          isDisabled ? 'opacity-50 pointer-events-none' : ''
        )}
      >
        <div className="flex items-start justify-between mb-3">
          <div className="flex-1">
            <label className="flex items-center space-x-2">
              <h4 className="font-medium text-white">{setting.name}</h4>
              {setting.danger && <AlertTriangle className="w-4 h-4 text-red-400" />}
            </label>
            <p className="text-sm text-gray-400 mt-1">{setting.description}</p>
          </div>
        </div>

        {/* Setting Input */}
        <div className="mt-3">
          {setting.type === 'boolean' && (
            <motion.button
              onClick={() => updateSetting(sectionId, setting.id, !setting.value)}
              className={cn(
                'w-12 h-6 rounded-full transition-colors duration-200',
                setting.value ? 'bg-blue-600' : 'bg-gray-600'
              )}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <motion.div
                className={cn(
                  'w-5 h-5 bg-white rounded-full shadow-md',
                  setting.value ? 'translate-x-6' : 'translate-x-0.5'
                )}
                layout
              />
            </motion.button>
          )}

          {setting.type === 'select' && (
            <select
              value={setting.value}
              onChange={(e) => updateSetting(sectionId, setting.id, e.target.value)}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:border-blue-500 focus:outline-none"
            >
              {setting.options?.map(option => (
                <option key={option} value={option}>
                  {option.charAt(0).toUpperCase() + option.slice(1)}
                </option>
              ))}
            </select>
          )}

          {setting.type === 'string' && (
            <input
              type="text"
              value={setting.value}
              onChange={(e) => updateSetting(sectionId, setting.id, e.target.value)}
              placeholder={setting.placeholder}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          )}

          {setting.type === 'number' && (
            <input
              type="number"
              value={setting.value}
              onChange={(e) => updateSetting(sectionId, setting.id, parseInt(e.target.value))}
              min={setting.min}
              max={setting.max}
              step={setting.step}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:border-blue-500 focus:outline-none"
            />
          )}

          {setting.type === 'range' && (
            <div className="space-y-2">
              <input
                type="range"
                value={setting.value}
                onChange={(e) => updateSetting(sectionId, setting.id, parseInt(e.target.value))}
                min={setting.min}
                max={setting.max}
                step={setting.step}
                className="w-full"
              />
              <div className="flex justify-between text-sm text-gray-400">
                <span>{setting.min}</span>
                <span className="text-white font-medium">{setting.value}</span>
                <span>{setting.max}</span>
              </div>
            </div>
          )}

          {setting.type === 'password' && (
            <input
              type="password"
              value={setting.value}
              onChange={(e) => updateSetting(sectionId, setting.id, e.target.value)}
              placeholder={setting.placeholder}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          )}

          {setting.type === 'file' && (
            <input
              type="file"
              onChange={(e) => updateSetting(sectionId, setting.id, e.target.files?.[0])}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-gray-600 file:text-white"
            />
          )}
        </div>

        {/* Help Text */}
        {setting.help && (
          <div className="mt-2 flex items-start space-x-2">
            <Info className="w-4 h-4 text-blue-400 mt-0.5" />
            <p className="text-xs text-gray-400">{setting.help}</p>
          </div>
        )}

        {/* Warning Text */}
        {setting.warning && (
          <div className="mt-2 flex items-start space-x-2">
            <AlertTriangle className="w-4 h-4 text-yellow-400 mt-0.5" />
            <p className="text-xs text-yellow-400">{setting.warning}</p>
          </div>
        )}
      </motion.div>
    );
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-400 to-purple-600 bg-clip-text text-transparent mb-2">
              Advanced Settings
            </h1>
            <p className="text-gray-400">
              Configure Jarvis to your preferences
            </p>
          </div>
          
          <div className="flex items-center space-x-4">
            {/* Search */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search settings..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10 pr-4 py-2 w-64 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
              />
            </div>

            {/* Advanced Toggle */}
            <motion.button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className={cn(
                'px-4 py-2 rounded-lg transition-colors',
                showAdvanced ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-300'
              )}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              Advanced
            </motion.button>

            {/* Save Button */}
            <motion.button
              onClick={saveSettings}
              disabled={!hasUnsavedChanges || isSaving}
              className={cn(
                'px-6 py-2 rounded-lg font-medium transition-colors',
                hasUnsavedChanges && !isSaving
                  ? 'bg-blue-600 hover:bg-blue-700 text-white'
                  : 'bg-gray-700 text-gray-400 cursor-not-allowed'
              )}
              whileHover={hasUnsavedChanges && !isSaving ? { scale: 1.05 } : {}}
              whileTap={hasUnsavedChanges && !isSaving ? { scale: 0.95 } : {}}
            >
              {isSaving ? (
                <RefreshCw className="w-5 h-5 animate-spin" />
              ) : saveStatus === 'saved' ? (
                <Check className="w-5 h-5" />
              ) : (
                <Save className="w-5 h-5" />
              )}
            </motion.button>

            {/* Reset Button */}
            <motion.button
              onClick={resetSettings}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              Reset
            </motion.button>
          </div>
        </div>
      </header>

      <div className="flex">
        {/* Sidebar */}
        <aside className="w-64 mr-6">
          <nav className="space-y-2">
            {filteredSections.map((section) => (
              <motion.button
                key={section.id}
                onClick={() => setActiveSection(section.id)}
                className={cn(
                  'w-full flex items-center space-x-3 px-4 py-3 rounded-lg text-left transition-all duration-200',
                  activeSection === section.id
                    ? 'bg-gradient-to-r ' + section.color + ' text-white'
                    : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                )}
                whileHover={{ x: 5 }}
                whileTap={{ scale: 0.98 }}
              >
                <section.icon className="w-5 h-5" />
                <div>
                  <div className="font-medium">{section.name}</div>
                  <div className="text-xs opacity-70">{section.settings.length} settings</div>
                </div>
              </motion.button>
            ))}
          </nav>
        </aside>

        {/* Main Content */}
        <main className="flex-1">
          <AnimatePresence mode="wait">
            {filteredSections.map((section) => (
              activeSection === section.id && (
                <motion.div
                  key={section.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  transition={{ duration: 0.2 }}
                >
                  <div className="mb-6">
                    <h2 className="text-2xl font-bold mb-2 flex items-center">
                      <section.icon className="w-6 h-6 mr-3" />
                      {section.name}
                    </h2>
                    <p className="text-gray-400">{section.description}</p>
                  </div>

                  <div className="space-y-4">
                    {section.settings
                      .filter(setting => 
                        searchQuery === '' || 
                        setting.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                        setting.description.toLowerCase().includes(searchQuery.toLowerCase())
                      )
                      .map((setting) => renderSetting(section.id, setting))}
                  </div>
                </motion.div>
              )
            ))}
          </AnimatePresence>
        </main>
      </div>

      {/* Save Status Toast */}
      <AnimatePresence>
        {saveStatus !== 'idle' && (
          <motion.div
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 50 }}
            className="fixed bottom-6 right-6 bg-gray-800 border border-gray-700 rounded-lg p-4 shadow-2xl"
          >
            <div className="flex items-center space-x-3">
              {saveStatus === 'saving' && (
                <>
                  <RefreshCw className="w-5 h-5 text-blue-400 animate-spin" />
                  <span>Saving settings...</span>
                </>
              )}
              {saveStatus === 'saved' && (
                <>
                  <Check className="w-5 h-5 text-green-400" />
                  <span>Settings saved successfully</span>
                </>
              )}
              {saveStatus === 'error' && (
                <>
                  <X className="w-5 h-5 text-red-400" />
                  <span>Failed to save settings</span>
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default AdvancedSettingsSystem;
