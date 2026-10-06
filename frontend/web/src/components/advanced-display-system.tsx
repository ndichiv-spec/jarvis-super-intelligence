'use client';

import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence, useMotionValue, useTransform } from 'framer-motion';
import { 
  Monitor, 
  Cpu, 
  HardDrive, 
  Wifi, 
  Zap, 
  Shield, 
  Activity,
  TrendingUp,
  TrendingDown,
  BarChart3,
  PieChart,
  LineChart,
  Grid3x3,
  Layers,
  Eye,
  EyeOff,
  Maximize2,
  Minimize2,
  Fullscreen,
  Plus,
  List,
  RefreshCw,
  Settings,
  Bell,
  X,
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  ChevronRight,
  Play,
  Pause,
  Square,
  Circle,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Download,
  Upload,
  Copy,
  Trash2,
  Edit,
  Save,
  FolderOpen,
  FileText,
  Image,
  Video,
  Music,
  Code,
  Terminal,
  Database,
  Globe,
  Lock,
  Unlock,
  Users,
  UserPlus,
  UserMinus,
  Filter,
  Search,
  MoreVertical,
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
  Camera,
  Mic,
  MicOff,
  Volume2,
  VolumeX
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface DisplayMetrics {
  fps: number;
  resolution: string;
  refreshRate: number;
  colorDepth: string;
  aspectRatio: string;
  brightness: number;
  contrast: number;
  saturation: number;
}

interface PerformanceData {
  timestamp: number;
  cpu: number;
  memory: number;
  gpu: number;
  network: number;
  disk: number;
}

interface DisplaySettings {
  theme: 'dark' | 'light' | 'auto';
  layout: 'grid' | 'list' | 'cards' | 'compact';
  animations: boolean;
  notifications: boolean;
  autoRefresh: boolean;
  refreshInterval: number;
}

interface WidgetData {
  id: string;
  title: string;
  type: 'chart' | 'metric' | 'table' | 'list' | 'custom';
  size: 'small' | 'medium' | 'large' | 'full';
  position: { x: number; y: number };
  data: any;
  isVisible: boolean;
}

export const AdvancedDisplaySystem: React.FC = () => {
  const [displayMetrics, setDisplayMetrics] = useState<DisplayMetrics>({
    fps: 144,
    resolution: '1920x1080',
    refreshRate: 144,
    colorDepth: '24-bit',
    aspectRatio: '16:9',
    brightness: 75,
    contrast: 80,
    saturation: 90
  });

  const [performanceHistory, setPerformanceHistory] = useState<PerformanceData[]>([]);
  const [displaySettings, setDisplaySettings] = useState<DisplaySettings>({
    theme: 'dark',
    layout: 'grid',
    animations: true,
    notifications: true,
    autoRefresh: true,
    refreshInterval: 2000
  });

  const [widgets, setWidgets] = useState<WidgetData[]>([
    {
      id: 'cpu-monitor',
      title: 'CPU Monitor',
      type: 'chart',
      size: 'medium',
      position: { x: 0, y: 0 },
      data: [],
      isVisible: true
    },
    {
      id: 'memory-usage',
      title: 'Memory Usage',
      type: 'metric',
      size: 'small',
      position: { x: 1, y: 0 },
      data: { value: 65, max: 100 },
      isVisible: true
    },
    {
      id: 'network-activity',
      title: 'Network Activity',
      type: 'chart',
      size: 'large',
      position: { x: 0, y: 1 },
      data: [],
      isVisible: true
    }
  ]);

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [selectedWidget, setSelectedWidget] = useState<string | null>(null);

  const dragX = useMotionValue(0);
  const dragY = useMotionValue(0);

  useEffect(() => {
    // Simulate real-time performance data
    const interval = setInterval(() => {
      const newData: PerformanceData = {
        timestamp: Date.now(),
        cpu: Math.random() * 100,
        memory: Math.random() * 100,
        gpu: Math.random() * 100,
        network: Math.random() * 100,
        disk: Math.random() * 100
      };

      setPerformanceHistory(prev => {
        const updated = [...prev, newData];
        return updated.slice(-50); // Keep last 50 data points
      });
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  const addWidget = (type: WidgetData['type']) => {
    const newWidget: WidgetData = {
      id: `widget-${Date.now()}`,
      title: `New ${type} Widget`,
      type,
      size: 'medium',
      position: { x: 2, y: 2 },
      data: type === 'chart' ? [] : {},
      isVisible: true
    };
    setWidgets(prev => [...prev, newWidget]);
  };

  const removeWidget = (id: string) => {
    setWidgets(prev => prev.filter(w => w.id !== id));
    setSelectedWidget(null);
  };

  const updateWidgetPosition = (id: string, newPosition: { x: number; y: number }) => {
    setWidgets(prev => prev.map(w => 
      w.id === id ? { ...w, position: newPosition } : w
    ));
  };

  const getWidgetSize = (size: WidgetData['size']) => {
    switch (size) {
      case 'small': return 'w-64 h-48';
      case 'medium': return 'w-80 h-60';
      case 'large': return 'w-96 h-72';
      case 'full': return 'w-full h-80';
      default: return 'w-80 h-60';
    }
  };

  const renderWidget = (widget: WidgetData) => {
    const sizeClass = getWidgetSize(widget.size);
    
    return (
      <motion.div
        drag
        dragMomentum={false}
        dragElastic={0.1}
        onDragEnd={(event, info) => {
          const gridX = Math.round(info.point.x / 320);
          const gridY = Math.round(info.point.y / 240);
          updateWidgetPosition(widget.id, { x: gridX, y: gridY });
        }}
        className={cn(
          'absolute p-4 rounded-xl border cursor-move transition-all duration-200',
          displaySettings.theme === 'dark' 
            ? 'bg-gray-800 border-gray-700' 
            : 'bg-white border-gray-200',
          selectedWidget === widget.id ? 'ring-2 ring-blue-500' : ''
        )}
        style={{
          left: `${widget.position.x * 320}px`,
          top: `${widget.position.y * 240}px`,
          width: widget.size === 'full' ? '100%' : undefined
        }}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        onClick={() => setSelectedWidget(widget.id)}
      >
        <div className="flex items-center justify-between mb-3">
          <h4 className="font-semibold text-sm">{widget.title}</h4>
          <div className="flex space-x-1">
            <motion.button
              className="p-1 rounded hover:bg-gray-700"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
            >
              <Settings className="w-3 h-3" />
            </motion.button>
            <motion.button
              className="p-1 rounded hover:bg-red-500"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
              onClick={() => removeWidget(widget.id)}
            >
              <X className="w-3 h-3" />
            </motion.button>
          </div>
        </div>

        {/* Widget Content */}
        <div className={cn('h-full', sizeClass)}>
          {widget.type === 'chart' && (
            <div className="h-full flex items-center justify-center">
              <LineChart className="w-full h-full text-blue-400" />
              <div className="text-center mt-2">
                <div className="text-xs text-gray-400">Real-time data</div>
              </div>
            </div>
          )}
          
          {widget.type === 'metric' && (
            <div className="h-full flex flex-col items-center justify-center">
              <div className="text-3xl font-bold mb-2">
                {widget.data.value}%
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2">
                <motion.div
                  className="bg-blue-500 h-full rounded-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${widget.data.value}%` }}
                  transition={{ duration: 1 }}
                />
              </div>
            </div>
          )}
        </div>
      </motion.div>
    );
  };

  return (
    <div className={cn(
      'min-h-screen transition-colors duration-300',
      displaySettings.theme === 'dark' ? 'bg-gray-900' : 'bg-gray-50'
    )}>
      {/* Advanced Header */}
      <header className="sticky top-0 z-50 backdrop-blur-xl border-b border-gray-800">
        <div className="flex items-center justify-between px-6 py-4">
          <div className="flex items-center space-x-6">
            <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-600 bg-clip-text text-transparent">
              Advanced Display System
            </h1>
            
            {/* Display Metrics */}
            <div className="flex items-center space-x-4 text-sm">
              <div className="flex items-center space-x-2">
                <Monitor className="w-4 h-4 text-blue-400" />
                <span>{displayMetrics.resolution}</span>
              </div>
              <div className="flex items-center space-x-2">
                <Activity className="w-4 h-4 text-green-400" />
                <span>{displayMetrics.fps} FPS</span>
              </div>
              <div className="flex items-center space-x-2">
                <Zap className="w-4 h-4 text-yellow-400" />
                <span>{displayMetrics.refreshRate} Hz</span>
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            {/* Layout Selector */}
            <div className="flex items-center space-x-2">
              <LayoutSelector
                currentLayout={displaySettings.layout}
                onLayoutChange={(layout) => setDisplaySettings(prev => ({ ...prev, layout }))}
              />
            </div>

            {/* Theme Toggle */}
            <motion.button
              className="p-2 rounded-lg hover:bg-gray-800 transition-colors"
              onClick={() => setDisplaySettings(prev => ({ 
                ...prev, 
                theme: prev.theme === 'dark' ? 'light' : 'dark' 
              }))}
              whileHover={{ rotate: 180 }}
              whileTap={{ scale: 0.95 }}
            >
              {displaySettings.theme === 'dark' ? <Eye className="w-5 h-5" /> : <EyeOff className="w-5 h-5" />}
            </motion.button>

            {/* Fullscreen Toggle */}
            <motion.button
              className="p-2 rounded-lg hover:bg-gray-800 transition-colors"
              onClick={toggleFullscreen}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              {isFullscreen ? <Minimize2 className="w-5 h-5" /> : <Maximize2 className="w-5 h-5" />}
            </motion.button>

            {/* Settings */}
            <motion.button
              className="p-2 rounded-lg hover:bg-gray-800 transition-colors"
              onClick={() => setShowSettings(!showSettings)}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <Settings className="w-5 h-5" />
            </motion.button>
          </div>
        </div>
      </header>

      {/* Display Controls */}
      <AnimatePresence>
        {showSettings && (
          <motion.div
            initial={{ opacity: 0, y: -50 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -50 }}
            className="absolute top-20 left-1/2 transform -translate-x-1/2 z-40 w-96 p-6 rounded-xl border bg-gray-800 shadow-2xl"
          >
            <h3 className="text-lg font-semibold mb-4">Display Settings</h3>
            
            <div className="space-y-4">
              {/* Brightness Control */}
              <div>
                <label className="block text-sm font-medium mb-2">Brightness</label>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={displayMetrics.brightness}
                  onChange={(e) => setDisplayMetrics(prev => ({ 
                    ...prev, 
                    brightness: parseInt(e.target.value) 
                  }))}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-gray-400 mt-1">
                  <span>0</span>
                  <span>{displayMetrics.brightness}%</span>
                  <span>100</span>
                </div>
              </div>

              {/* Contrast Control */}
              <div>
                <label className="block text-sm font-medium mb-2">Contrast</label>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={displayMetrics.contrast}
                  onChange={(e) => setDisplayMetrics(prev => ({ 
                    ...prev, 
                    contrast: parseInt(e.target.value) 
                  }))}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-gray-400 mt-1">
                  <span>0</span>
                  <span>{displayMetrics.contrast}%</span>
                  <span>100</span>
                </div>
              </div>

              {/* Refresh Rate */}
              <div>
                <label className="block text-sm font-medium mb-2">Auto Refresh</label>
                <div className="flex items-center space-x-3">
                  <input
                    type="checkbox"
                    checked={displaySettings.autoRefresh}
                    onChange={(e) => setDisplaySettings(prev => ({ 
                      ...prev, 
                      autoRefresh: e.target.checked 
                    }))}
                    className="rounded"
                  />
                  <input
                    type="number"
                    min="500"
                    max="10000"
                    step="500"
                    value={displaySettings.refreshInterval}
                    onChange={(e) => setDisplaySettings(prev => ({ 
                      ...prev, 
                      refreshInterval: parseInt(e.target.value) 
                    }))}
                    disabled={!displaySettings.autoRefresh}
                    className="w-24 px-2 py-1 rounded bg-gray-700 text-white"
                  />
                  <span className="text-sm text-gray-400">ms</span>
                </div>
              </div>
            </div>

            <motion.button
              className="absolute top-4 right-4 p-1 rounded hover:bg-gray-700"
              onClick={() => setShowSettings(false)}
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
            >
              <X className="w-4 h-4" />
            </motion.button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Widget Grid */}
      <div className="relative p-6" style={{ minHeight: 'calc(100vh - 200px)' }}>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {/* Add Widget Button */}
          <motion.div
            className="border-2 border-dashed border-gray-600 rounded-xl p-8 flex flex-col items-center justify-center cursor-pointer hover:border-blue-500 transition-colors"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => {
              const types: WidgetData['type'][] = ['chart', 'metric', 'table', 'list'];
              const randomType = types[Math.floor(Math.random() * types.length)];
              addWidget(randomType);
            }}
          >
            <Plus className="w-8 h-8 text-gray-400 mb-3" />
            <span className="text-sm text-gray-400">Add Widget</span>
          </motion.div>

          {/* Render Widgets */}
          {widgets.filter(w => w.isVisible).map((widget) => (
            <div key={widget.id} className="relative">
              {renderWidget(widget)}
            </div>
          ))}
        </div>
      </div>

      {/* Performance Overlay */}
      <AnimatePresence>
        {selectedWidget && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed bottom-6 right-6 bg-gray-800 rounded-lg p-4 shadow-2xl z-50"
            onClick={() => setSelectedWidget(null)}
          >
            <div className="flex items-center space-x-3 mb-3">
              <Eye className="w-4 h-4 text-blue-400" />
              <span className="font-medium">Widget Details</span>
            </div>
            <div className="text-sm text-gray-300">
              <p>Widget: {selectedWidget}</p>
              <p>Position: {widgets.find(w => w.id === selectedWidget)?.position.x}, {widgets.find(w => w.id === selectedWidget)?.position.y}</p>
              <p>Size: {widgets.find(w => w.id === selectedWidget)?.size}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// Helper Component for Layout Selection
const LayoutSelector: React.FC<{
  currentLayout: DisplaySettings['layout'];
  onLayoutChange: (layout: DisplaySettings['layout']) => void;
}> = ({ currentLayout, onLayoutChange }) => {
  const layouts = [
    { value: 'grid', icon: Grid3x3, label: 'Grid View' },
    { value: 'list', icon: List, label: 'List View' },
    { value: 'cards', icon: Layers, label: 'Card View' },
    { value: 'compact', icon: Minimize2, label: 'Compact' }
  ];

  return (
    <div className="relative">
      <motion.button
        className="flex items-center space-x-2 px-3 py-2 rounded-lg hover:bg-gray-800 transition-colors"
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
      >
        <Grid3x3 className="w-4 h-4" />
        <span className="text-sm">{currentLayout}</span>
        <ChevronDown className="w-4 h-4" />
      </motion.button>
    </div>
  );
};

export default AdvancedDisplaySystem;
