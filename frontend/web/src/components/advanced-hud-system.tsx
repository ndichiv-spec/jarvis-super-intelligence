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
  VolumeX,
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
  Home,
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
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface HUDWidget {
  id: string;
  type: 'metric' | 'chart' | 'alert' | 'control' | 'status' | 'custom';
  title: string;
  position: { x: number; y: number };
  size: { width: number; height: number };
  data: any;
  isVisible: boolean;
  isLocked: boolean;
  opacity: number;
  zIndex: number;
  theme: 'light' | 'dark' | 'cyberpunk' | 'matrix' | 'neon';
  animation: 'none' | 'pulse' | 'glow' | 'slide' | 'fade' | 'rotate';
  color: string;
  backgroundColor: string;
  borderColor: string;
  fontSize: 'small' | 'medium' | 'large';
  fontFamily: 'mono' | 'sans' | 'serif';
  borderRadius: 'none' | 'small' | 'medium' | 'large';
  shadow: 'none' | 'small' | 'medium' | 'large';
  blur: 'none' | 'small' | 'medium' | 'large';
  customStyles?: React.CSSProperties;
}

interface HUDLayout {
  name: string;
  description: string;
  widgets: HUDWidget[];
  grid: { rows: number; columns: number };
  spacing: number;
  padding: number;
  backgroundColor: string;
  backgroundImage?: string;
  backgroundOpacity: number;
}

interface HUDData {
  system: {
    cpu: number;
    memory: number;
    disk: number;
    network: number;
    temperature: number;
    power: number;
    battery: number;
  };
  network: {
    upload: number;
    download: number;
    latency: number;
    packetLoss: number;
    connections: number;
    bandwidth: number;
  };
  security: {
    threats: number;
    blocked: number;
    alerts: number;
    firewall: 'active' | 'inactive' | 'warning';
    vpn: 'connected' | 'disconnected';
    encryption: 'enabled' | 'disabled';
  };
  performance: {
    fps: number;
    responseTime: number;
    throughput: number;
    efficiency: number;
    uptime: number;
    errors: number;
  };
  notifications: Array<{
    id: string;
    type: 'info' | 'warning' | 'error' | 'success';
    title: string;
    message: string;
    timestamp: Date;
    priority: 'low' | 'medium' | 'high' | 'critical';
    actions?: Array<{
      label: string;
      action: () => void;
    }>;
  }>;
}

interface HUDTheme {
  name: string;
  colors: {
    primary: string;
    secondary: string;
    accent: string;
    background: string;
    surface: string;
    text: string;
    border: string;
    success: string;
    warning: string;
    error: string;
    info: string;
  };
  fonts: {
    primary: string;
    secondary: string;
    mono: string;
  };
  effects: {
    glow: boolean;
    blur: boolean;
    shadow: boolean;
    animation: boolean;
  };
}

export const AdvancedHUDSystem: React.FC = () => {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isLocked, setIsLocked] = useState(false);
  const [showGrid, setShowGrid] = useState(false);
  const [showControls, setShowControls] = useState(true);
  const [selectedTheme, setSelectedTheme] = useState('cyberpunk');
  const [selectedLayout, setSelectedLayout] = useState('default');
  const [isEditing, setIsEditing] = useState(false);
  const [selectedWidget, setSelectedWidget] = useState<string | null>(null);
  const [hudData, setHudData] = useState<HUDData>({
    system: {
      cpu: 45,
      memory: 62,
      disk: 78,
      network: 23,
      temperature: 65,
      power: 85,
      battery: 92
    },
    network: {
      upload: 2.5,
      download: 15.7,
      latency: 12,
      packetLoss: 0.1,
      connections: 127,
      bandwidth: 100
    },
    security: {
      threats: 3,
      blocked: 47,
      alerts: 2,
      firewall: 'active',
      vpn: 'connected',
      encryption: 'enabled'
    },
    performance: {
      fps: 144,
      responseTime: 45,
      throughput: 892,
      efficiency: 94,
      uptime: 15 * 24 * 60 * 60, // 15 days in seconds
      errors: 0
    },
    notifications: []
  });

  const [widgets, setWidgets] = useState<HUDWidget[]>([
    {
      id: 'cpu-monitor',
      type: 'metric',
      title: 'CPU Usage',
      position: { x: 10, y: 10 },
      size: { width: 200, height: 100 },
      data: { value: 45, max: 100 },
      isVisible: true,
      isLocked: false,
      opacity: 0.9,
      zIndex: 1,
      theme: 'cyberpunk',
      animation: 'pulse',
      color: '#00ff00',
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      borderColor: '#00ff00',
      fontSize: 'medium',
      fontFamily: 'mono',
      borderRadius: 'small',
      shadow: 'medium',
      blur: 'small'
    },
    {
      id: 'memory-monitor',
      type: 'metric',
      title: 'Memory Usage',
      position: { x: 220, y: 10 },
      size: { width: 200, height: 100 },
      data: { value: 62, max: 100 },
      isVisible: true,
      isLocked: false,
      opacity: 0.9,
      zIndex: 1,
      theme: 'cyberpunk',
      animation: 'pulse',
      color: '#00ffff',
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      borderColor: '#00ffff',
      fontSize: 'medium',
      fontFamily: 'mono',
      borderRadius: 'small',
      shadow: 'medium',
      blur: 'small'
    },
    {
      id: 'network-monitor',
      type: 'chart',
      title: 'Network Activity',
      position: { x: 10, y: 120 },
      size: { width: 410, height: 150 },
      data: { history: [], upload: 2.5, download: 15.7 },
      isVisible: true,
      isLocked: false,
      opacity: 0.9,
      zIndex: 1,
      theme: 'cyberpunk',
      animation: 'glow',
      color: '#ff00ff',
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      borderColor: '#ff00ff',
      fontSize: 'medium',
      fontFamily: 'mono',
      borderRadius: 'small',
      shadow: 'medium',
      blur: 'small'
    },
    {
      id: 'security-status',
      type: 'status',
      title: 'Security Status',
      position: { x: 10, y: 280 },
      size: { width: 200, height: 100 },
      data: { threats: 3, blocked: 47, alerts: 2, status: 'secure' },
      isVisible: true,
      isLocked: false,
      opacity: 0.9,
      zIndex: 1,
      theme: 'cyberpunk',
      animation: 'pulse',
      color: '#ffff00',
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      borderColor: '#ffff00',
      fontSize: 'medium',
      fontFamily: 'mono',
      borderRadius: 'small',
      shadow: 'medium',
      blur: 'small'
    },
    {
      id: 'performance-metrics',
      type: 'metric',
      title: 'Performance',
      position: { x: 220, y: 280 },
      size: { width: 200, height: 100 },
      data: { fps: 144, responseTime: 45, efficiency: 94 },
      isVisible: true,
      isLocked: false,
      opacity: 0.9,
      zIndex: 1,
      theme: 'cyberpunk',
      animation: 'glow',
      color: '#ff6600',
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      borderColor: '#ff6600',
      fontSize: 'medium',
      fontFamily: 'mono',
      borderRadius: 'small',
      shadow: 'medium',
      blur: 'small'
    }
  ]);

  const [themes] = useState<HUDTheme[]>([
    {
      name: 'cyberpunk',
      colors: {
        primary: '#00ff00',
        secondary: '#00ffff',
        accent: '#ff00ff',
        background: 'rgba(0, 0, 0, 0.9)',
        surface: 'rgba(0, 0, 0, 0.8)',
        text: '#00ff00',
        border: '#00ff00',
        success: '#00ff00',
        warning: '#ffff00',
        error: '#ff0000',
        info: '#00ffff'
      },
      fonts: {
        primary: 'monospace',
        secondary: 'sans-serif',
        mono: 'monospace'
      },
      effects: {
        glow: true,
        blur: true,
        shadow: true,
        animation: true
      }
    },
    {
      name: 'matrix',
      colors: {
        primary: '#00ff00',
        secondary: '#008800',
        accent: '#00ff00',
        background: 'rgba(0, 0, 0, 0.9)',
        surface: 'rgba(0, 0, 0, 0.8)',
        text: '#00ff00',
        border: '#00ff00',
        success: '#00ff00',
        warning: '#ffff00',
        error: '#ff0000',
        info: '#00ffff'
      },
      fonts: {
        primary: 'monospace',
        secondary: 'monospace',
        mono: 'monospace'
      },
      effects: {
        glow: true,
        blur: false,
        shadow: true,
        animation: true
      }
    },
    {
      name: 'neon',
      colors: {
        primary: '#ff00ff',
        secondary: '#00ffff',
        accent: '#ffff00',
        background: 'rgba(0, 0, 0, 0.9)',
        surface: 'rgba(0, 0, 0, 0.8)',
        text: '#ffffff',
        border: '#ff00ff',
        success: '#00ff00',
        warning: '#ffff00',
        error: '#ff0000',
        info: '#00ffff'
      },
      fonts: {
        primary: 'sans-serif',
        secondary: 'monospace',
        mono: 'monospace'
      },
      effects: {
        glow: true,
        blur: true,
        shadow: true,
        animation: true
      }
    }
  ]);

  const dragX = useMotionValue(0);
  const dragY = useMotionValue(0);

  useEffect(() => {
    // Simulate real-time data updates
    const interval = setInterval(() => {
      setHudData(prev => ({
        ...prev,
        system: {
          ...prev.system,
          cpu: Math.max(10, Math.min(95, prev.system.cpu + (Math.random() - 0.5) * 5)),
          memory: Math.max(20, Math.min(95, prev.system.memory + (Math.random() - 0.5) * 3)),
          network: Math.max(5, Math.min(100, prev.system.network + (Math.random() - 0.5) * 8)),
          temperature: Math.max(40, Math.min(85, prev.system.temperature + (Math.random() - 0.5) * 2))
        },
        network: {
          ...prev.network,
          upload: Math.max(0, prev.network.upload + (Math.random() - 0.5) * 2),
          download: Math.max(0, prev.network.download + (Math.random() - 0.5) * 5),
          latency: Math.max(5, Math.min(100, prev.network.latency + (Math.random() - 0.5) * 10))
        },
        performance: {
          ...prev.performance,
          fps: Math.max(30, Math.min(240, prev.performance.fps + (Math.random() - 0.5) * 10)),
          responseTime: Math.max(10, Math.min(200, prev.performance.responseTime + (Math.random() - 0.5) * 20))
        }
      }));
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

  const addWidget = (type: HUDWidget['type']) => {
    const newWidget: HUDWidget = {
      id: `widget-${Date.now()}`,
      type,
      title: `New ${type} Widget`,
      position: { x: 50, y: 50 },
      size: { width: 200, height: 100 },
      data: type === 'metric' ? { value: 50, max: 100 } : {},
      isVisible: true,
      isLocked: false,
      opacity: 0.9,
      zIndex: 1,
      theme: selectedTheme as HUDWidget['theme'],
      animation: 'pulse',
      color: '#00ff00',
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      borderColor: '#00ff00',
      fontSize: 'medium',
      fontFamily: 'mono',
      borderRadius: 'small',
      shadow: 'medium',
      blur: 'small'
    };
    setWidgets(prev => [...prev, newWidget]);
  };

  const removeWidget = (id: string) => {
    setWidgets(prev => prev.filter(w => w.id !== id));
    setSelectedWidget(null);
  };

  const updateWidget = (id: string, updates: Partial<HUDWidget>) => {
    setWidgets(prev => prev.map(w => w.id === id ? { ...w, ...updates } : w));
  };

  const getThemeColors = (themeName: string) => {
    const theme = themes.find(t => t.name === themeName);
    return theme?.colors || themes[0].colors;
  };

  const renderWidget = (widget: HUDWidget) => {
    const colors = getThemeColors(widget.theme);
    const isSelected = selectedWidget === widget.id;

    const getAnimationClass = () => {
      switch (widget.animation) {
        case 'pulse': return 'animate-pulse';
        case 'glow': return 'animate-glow';
        case 'slide': return 'animate-slide';
        case 'fade': return 'animate-fade';
        case 'rotate': return 'animate-rotate';
        default: return '';
      }
    };

    const getBorderRadiusClass = () => {
      switch (widget.borderRadius) {
        case 'none': return 'rounded-none';
        case 'small': return 'rounded';
        case 'medium': return 'rounded-lg';
        case 'large': return 'rounded-xl';
        default: return 'rounded';
      }
    };

    const getBlurClass = () => {
      switch (widget.blur) {
        case 'small': return 'backdrop-blur-sm';
        case 'medium': return 'backdrop-blur-md';
        case 'large': return 'backdrop-blur-lg';
        default: return '';
      }
    };

    const getShadowClass = () => {
      switch (widget.shadow) {
        case 'small': return 'shadow-sm';
        case 'medium': return 'shadow-lg';
        case 'large': return 'shadow-2xl';
        default: return '';
      }
    };

    const getFontSizeClass = () => {
      switch (widget.fontSize) {
        case 'small': return 'text-xs';
        case 'medium': return 'text-sm';
        case 'large': return 'text-base';
        default: return 'text-sm';
      }
    };

    const getFontFamilyClass = () => {
      switch (widget.fontFamily) {
        case 'mono': return 'font-mono';
        case 'sans': return 'font-sans';
        case 'serif': return 'font-serif';
        default: return 'font-mono';
      }
    };

    return (
      <motion.div
        key={widget.id}
        drag={!isLocked && !widget.isLocked}
        dragMomentum={false}
        dragElastic={0.1}
        onDragEnd={(event, info) => {
          updateWidget(widget.id, {
            position: {
              x: widget.position.x + info.offset.x,
              y: widget.position.y + info.offset.y
            }
          });
        }}
        className={cn(
          'absolute border cursor-move transition-all duration-200',
          getBorderRadiusClass(),
          getBlurClass(),
          getShadowClass(),
          getAnimationClass(),
          isSelected ? 'ring-2 ring-blue-500' : ''
        )}
        style={{
          left: `${widget.position.x}px`,
          top: `${widget.position.y}px`,
          width: `${widget.size.width}px`,
          height: `${widget.size.height}px`,
          backgroundColor: widget.backgroundColor,
          borderColor: widget.borderColor,
          borderWidth: '1px',
          opacity: widget.opacity,
          zIndex: widget.zIndex,
          boxShadow: `0 0 ${widget.theme === 'cyberpunk' ? '10px' : '5px'} ${widget.color}`,
          ...widget.customStyles
        }}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        onClick={() => setSelectedWidget(widget.id)}
      >
        {/* Widget Header */}
        <div className={cn(
          'flex items-center justify-between p-2 border-b',
          getFontSizeClass(),
          getFontFamilyClass()
        )} style={{ borderColor: widget.borderColor }}>
          <span style={{ color: widget.color }}>{widget.title}</span>
          <div className="flex space-x-1">
            {!isLocked && (
              <>
                <motion.button
                  className="p-1 hover:bg-white/10 rounded"
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={(e) => {
                    e.stopPropagation();
                    updateWidget(widget.id, { isLocked: !widget.isLocked });
                  }}
                >
                  {widget.isLocked ? <Lock className="w-3 h-3" /> : <Unlock className="w-3 h-3" />}
                </motion.button>
                <motion.button
                  className="p-1 hover:bg-white/10 rounded"
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={(e) => {
                    e.stopPropagation();
                    removeWidget(widget.id);
                  }}
                >
                  <X className="w-3 h-3" />
                </motion.button>
              </>
            )}
          </div>
        </div>

        {/* Widget Content */}
        <div className="p-3 h-full">
          {widget.type === 'metric' && (
            <div className="flex flex-col items-center justify-center h-full">
              <div className={cn('text-2xl font-bold mb-2', getFontSizeClass(), getFontFamilyClass())} style={{ color: widget.color }}>
                {widget.data.value}%
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2">
                <motion.div
                  className="h-full rounded-full"
                  style={{ backgroundColor: widget.color }}
                  initial={{ width: 0 }}
                  animate={{ width: `${widget.data.value}%` }}
                  transition={{ duration: 1 }}
                />
              </div>
            </div>
          )}

          {widget.type === 'chart' && (
            <div className="flex items-center justify-center h-full">
              <LineChart className="w-full h-full" style={{ color: widget.color }} />
              <div className="text-center mt-2">
                <div className={cn('text-xs', getFontSizeClass(), getFontFamilyClass())} style={{ color: widget.color }}>
                  Real-time data
                </div>
              </div>
            </div>
          )}

          {widget.type === 'status' && (
            <div className="flex flex-col items-center justify-center h-full">
              <div className={cn('text-lg font-bold mb-2', getFontSizeClass(), getFontFamilyClass())} style={{ color: widget.color }}>
                {widget.data.status}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>Threats: {widget.data.threats}</div>
                <div>Blocked: {widget.data.blocked}</div>
                <div>Alerts: {widget.data.alerts}</div>
                <div>Status: {widget.data.status}</div>
              </div>
            </div>
          )}

          {widget.type === 'alert' && (
            <div className="flex items-center justify-center h-full">
              <AlertTriangle className="w-8 h-8" style={{ color: widget.color }} />
              <div className="ml-2">
                <div className={cn('font-medium', getFontSizeClass(), getFontFamilyClass())} style={{ color: widget.color }}>
                  Alert
                </div>
                <div className={cn('text-xs', getFontSizeClass(), getFontFamilyClass())} style={{ color: widget.color }}>
                  System alert
                </div>
              </div>
            </div>
          )}

          {widget.type === 'control' && (
            <div className="flex items-center justify-center h-full space-x-2">
              <motion.button
                className="p-2 rounded"
                style={{ backgroundColor: widget.color }}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
              >
                <Play className="w-4 h-4 text-white" />
              </motion.button>
              <motion.button
                className="p-2 rounded"
                style={{ backgroundColor: widget.color }}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
              >
                <Pause className="w-4 h-4 text-white" />
              </motion.button>
              <motion.button
                className="p-2 rounded"
                style={{ backgroundColor: widget.color }}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
              >
                <Square className="w-4 h-4 text-white" />
              </motion.button>
            </div>
          )}
        </div>
      </motion.div>
    );
  };

  const currentTheme = themes.find(t => t.name === selectedTheme);

  return (
    <div className="relative w-full h-screen overflow-hidden" style={{ 
      backgroundColor: currentTheme?.colors.background || 'rgba(0, 0, 0, 0.9)',
      backgroundImage: selectedTheme === 'matrix' 
        ? 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0, 255, 0, 0.03) 2px, rgba(0, 255, 0, 0.03) 4px)'
        : undefined
    }}>
      {/* Grid Overlay */}
      {showGrid && (
        <div 
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: `
              linear-gradient(${currentTheme?.colors.border}20 1px, transparent 1px),
              linear-gradient(90deg, ${currentTheme?.colors.border}20 1px, transparent 1px)
            `,
            backgroundSize: '20px 20px'
          }}
        />
      )}

      {/* HUD Widgets */}
      {widgets.filter(w => w.isVisible).map(widget => renderWidget(widget))}

      {/* HUD Controls */}
      <AnimatePresence>
        {showControls && (
          <motion.div
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 50 }}
            className="absolute top-4 right-4 bg-black/80 backdrop-blur-lg rounded-lg p-4 border"
            style={{ borderColor: currentTheme?.colors.border }}
          >
            <div className="space-y-4">
              {/* Theme Selector */}
              <div>
                <label className="text-xs font-medium mb-2 block" style={{ color: currentTheme?.colors.text }}>
                  Theme
                </label>
                <select
                  value={selectedTheme}
                  onChange={(e) => setSelectedTheme(e.target.value)}
                  className="w-full bg-black/50 border rounded px-2 py-1 text-xs"
                  style={{ borderColor: currentTheme?.colors.border, color: currentTheme?.colors.text }}
                >
                  {themes.map(theme => (
                    <option key={theme.name} value={theme.name}>
                      {theme.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Widget Controls */}
              <div>
                <label className="text-xs font-medium mb-2 block" style={{ color: currentTheme?.colors.text }}>
                  Add Widget
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {(['metric', 'chart', 'alert', 'control'] as const).map(type => (
                    <motion.button
                      key={type}
                      onClick={() => addWidget(type)}
                      className="px-2 py-1 rounded text-xs capitalize"
                      style={{ 
                        backgroundColor: currentTheme?.colors.primary,
                        color: currentTheme?.colors.background
                      }}
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                    >
                      {type}
                    </motion.button>
                  ))}
                </div>
              </div>

              {/* View Controls */}
              <div className="space-y-2">
                <motion.button
                  onClick={() => setShowGrid(!showGrid)}
                  className="w-full px-2 py-1 rounded text-xs"
                  style={{ 
                    backgroundColor: showGrid ? currentTheme?.colors.primary : 'transparent',
                    color: showGrid ? currentTheme?.colors.background : currentTheme?.colors.text,
                    border: `1px solid ${currentTheme?.colors.border}`
                  }}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  {showGrid ? 'Hide Grid' : 'Show Grid'}
                </motion.button>

                <motion.button
                  onClick={() => setIsLocked(!isLocked)}
                  className="w-full px-2 py-1 rounded text-xs"
                  style={{ 
                    backgroundColor: isLocked ? currentTheme?.colors.warning : 'transparent',
                    color: isLocked ? currentTheme?.colors.background : currentTheme?.colors.text,
                    border: `1px solid ${currentTheme?.colors.border}`
                  }}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  {isLocked ? 'Unlock HUD' : 'Lock HUD'}
                </motion.button>

                <motion.button
                  onClick={toggleFullscreen}
                  className="w-full px-2 py-1 rounded text-xs"
                  style={{ 
                    backgroundColor: currentTheme?.colors.primary,
                    color: currentTheme?.colors.background,
                    border: `1px solid ${currentTheme?.colors.border}`
                  }}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  {isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
                </motion.button>

                <motion.button
                  onClick={() => setShowControls(false)}
                  className="w-full px-2 py-1 rounded text-xs"
                  style={{ 
                    backgroundColor: currentTheme?.colors.error,
                    color: currentTheme?.colors.background,
                    border: `1px solid ${currentTheme?.colors.border}`
                  }}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  Hide Controls
                </motion.button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Show Controls Button */}
      <AnimatePresence>
        {!showControls && (
          <motion.button
            initial={{ opacity: 0, scale: 0 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0 }}
            onClick={() => setShowControls(true)}
            className="absolute top-4 right-4 p-3 rounded-full"
            style={{ 
              backgroundColor: currentTheme?.colors.primary,
              color: currentTheme?.colors.background
            }}
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
          >
            <Settings className="w-4 h-4" />
          </motion.button>
        )}
      </AnimatePresence>

      {/* System Status Bar */}
      <div className="absolute bottom-0 left-0 right-0 bg-black/80 backdrop-blur-lg border-t p-2" style={{ borderColor: currentTheme?.colors.border }}>
        <div className="flex items-center justify-between text-xs" style={{ color: currentTheme?.colors.text }}>
          <div className="flex items-center space-x-4">
            <span>CPU: {hudData.system.cpu}%</span>
            <span>Memory: {hudData.system.memory}%</span>
            <span>Network: {hudData.network.download.toFixed(1)}MB/s</span>
            <span>FPS: {hudData.performance.fps}</span>
          </div>
          <div className="flex items-center space-x-4">
            <span>Security: {hudData.security.firewall}</span>
            <span>VPN: {hudData.security.vpn}</span>
            <span>Uptime: {Math.floor(hudData.performance.uptime / 3600)}h</span>
          </div>
        </div>
      </div>

      {/* Custom CSS for animations */}
      <style jsx>{`
        @keyframes glow {
          0%, 100% { box-shadow: 0 0 5px currentColor; }
          50% { box-shadow: 0 0 20px currentColor, 0 0 30px currentColor; }
        }
        
        @keyframes slide {
          0%, 100% { transform: translateX(0); }
          50% { transform: translateX(5px); }
        }
        
        @keyframes fade {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.7; }
        }
        
        @keyframes rotate {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        
        .animate-glow {
          animation: glow 2s ease-in-out infinite;
        }
        
        .animate-slide {
          animation: slide 2s ease-in-out infinite;
        }
        
        .animate-fade {
          animation: fade 2s ease-in-out infinite;
        }
        
        .animate-rotate {
          animation: rotate 2s linear infinite;
        }
      `}</style>
    </div>
  );
};

export default AdvancedHUDSystem;
