'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  BarChart3,
  PieChart,
  TrendingUp,
  TrendingDown,
  Activity,
  Users,
  Eye,
  MousePointer,
  Clock,
  Calendar,
  Filter,
  Download,
  RefreshCw,
  Settings,
  Maximize2,
  Minimize2,
  ArrowUp,
  ArrowDown,
  ArrowRight,
  ArrowLeft,
  Zap,
  Target,
  Award,
  Star,
  Hash,
  Percent,
  DollarSign,
  Timer,
  Globe,
  MapPin,
  Smartphone,
  Tablet,
  Laptop,
  Monitor,
  Server,
  Database,
  Cloud,
  Wifi,
  Cpu,
  HardDrive,
  MemoryStick,
  Usb,
  Network,
  Router,
  ToggleLeft,
  Antenna,
  Satellite,
  Radio,
  Tv,
  Gamepad2,
  Headphones,
  Speaker,
  Webcam,
  Mic,
  Keyboard,
  Mouse as MouseIcon,
  Touchpad,
  Pen,
  Eraser,
  Paintbrush,
  Palette,
  Scissors,
  Paperclip,
  Clipboard,
  Calculator,
  Ruler,
  Compass,
  Triangle,
  Square,
  Circle,
  Hexagon,
  Pentagon,
  Octagon,
  Star as StarIcon,
  Heart,
  Diamond,
  Club,
  Spade,
  Music,
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
  Heart as HeartIcon,
  Diamond as DiamondIcon,
  Club as ClubIcon,
  Spade as SpadeIcon,
  Watch, AlertTriangle, LineChart, MoreVertical 
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface AnalyticsData {
  timestamp: number;
  users: number;
  pageViews: number;
  sessions: number;
  bounceRate: number;
  avgSessionDuration: number;
  conversionRate: number;
  revenue: number;
  cpuUsage: number;
  memoryUsage: number;
  networkTraffic: number;
  errorRate: number;
  responseTime: number;
}

interface MetricCard {
  title: string;
  value: string | number;
  change: number;
  changeType: 'increase' | 'decrease' | 'neutral';
  icon: React.ComponentType<any>;
  color: string;
  trend: number[];
  unit?: string;
  format?: 'number' | 'percentage' | 'currency' | 'time';
}

interface ChartData {
  labels: string[];
  datasets: {
    label: string;
    data: number[];
    color: string;
    type: 'line' | 'bar' | 'area';
  }[];
}

interface DeviceBreakdown {
  device: string;
  count: number;
  percentage: number;
  icon: React.ComponentType<any>;
  color: string;
}

interface GeographicData {
  country: string;
  users: number;
  percentage: number;
  flag: string;
  coordinates: { lat: number; lng: number };
}

interface PerformanceMetric {
  name: string;
  value: number;
  threshold: number;
  status: 'good' | 'warning' | 'critical';
  trend: number;
  icon: React.ComponentType<any>;
  unit: string;
}

export const AnalyticsDashboard: React.FC = () => {
  const [timeRange, setTimeRange] = useState('7d');
  const [selectedMetric, setSelectedMetric] = useState('overview');
  const [isRealtime, setIsRealtime] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [analyticsData, setAnalyticsData] = useState<AnalyticsData[]>([]);
  const [metrics, setMetrics] = useState<MetricCard[]>([]);
  const [chartData, setChartData] = useState<ChartData>({ labels: [], datasets: [] });
  const [deviceBreakdown, setDeviceBreakdown] = useState<DeviceBreakdown[]>([]);
  const [geographicData, setGeographicData] = useState<GeographicData[]>([]);
  const [performanceMetrics, setPerformanceMetrics] = useState<PerformanceMetric[]>([]);

  const timeRanges = [
    { value: '1h', label: 'Last Hour' },
    { value: '24h', label: 'Last 24 Hours' },
    { value: '7d', label: 'Last 7 Days' },
    { value: '30d', label: 'Last 30 Days' },
    { value: '90d', label: 'Last 90 Days' },
    { value: '1y', label: 'Last Year' }
  ];

  const metricsCategories = [
    { value: 'overview', label: 'Overview', icon: BarChart3 },
    { value: 'traffic', label: 'Traffic', icon: Activity },
    { value: 'users', label: 'Users', icon: Users },
    { value: 'performance', label: 'Performance', icon: Zap },
    { value: 'revenue', label: 'Revenue', icon: DollarSign },
    { value: 'devices', label: 'Devices', icon: Smartphone },
    { value: 'geography', label: 'Geography', icon: Globe },
    { value: 'behavior', label: 'Behavior', icon: Eye }
  ];

  useEffect(() => {
    // Generate mock analytics data
    const generateData = () => {
      const now = Date.now();
      const data: AnalyticsData[] = [];
      
      for (let i = 0; i < 100; i++) {
        data.push({
          timestamp: now - (i * 3600000), // 1 hour intervals
          users: Math.floor(Math.random() * 1000) + 500,
          pageViews: Math.floor(Math.random() * 5000) + 2000,
          sessions: Math.floor(Math.random() * 800) + 300,
          bounceRate: Math.random() * 0.5 + 0.2,
          avgSessionDuration: Math.random() * 300 + 60,
          conversionRate: Math.random() * 0.05 + 0.01,
          revenue: Math.random() * 10000 + 1000,
          cpuUsage: Math.random() * 80 + 20,
          memoryUsage: Math.random() * 70 + 30,
          networkTraffic: Math.random() * 1000000 + 500000,
          errorRate: Math.random() * 0.05,
          responseTime: Math.random() * 500 + 100
        });
      }
      
      return data.reverse();
    };

    const data = generateData();
    setAnalyticsData(data);

    // Calculate metrics
    const latestData = data[data.length - 1];
    const previousData = data[data.length - 2];

    const calculatedMetrics: MetricCard[] = [
      {
        title: 'Total Users',
        value: latestData.users,
        change: ((latestData.users - previousData.users) / previousData.users) * 100,
        changeType: latestData.users > previousData.users ? 'increase' : 'decrease',
        icon: Users,
        color: 'from-blue-500 to-cyan-400',
        trend: data.slice(-7).map(d => d.users),
        format: 'number'
      },
      {
        title: 'Page Views',
        value: latestData.pageViews,
        change: ((latestData.pageViews - previousData.pageViews) / previousData.pageViews) * 100,
        changeType: latestData.pageViews > previousData.pageViews ? 'increase' : 'decrease',
        icon: Eye,
        color: 'from-purple-500 to-pink-400',
        trend: data.slice(-7).map(d => d.pageViews),
        format: 'number'
      },
      {
        title: 'Avg Session Duration',
        value: latestData.avgSessionDuration,
        change: ((latestData.avgSessionDuration - previousData.avgSessionDuration) / previousData.avgSessionDuration) * 100,
        changeType: latestData.avgSessionDuration > previousData.avgSessionDuration ? 'increase' : 'decrease',
        icon: Clock,
        color: 'from-green-500 to-emerald-400',
        trend: data.slice(-7).map(d => d.avgSessionDuration),
        format: 'time'
      },
      {
        title: 'Conversion Rate',
        value: latestData.conversionRate * 100,
        change: ((latestData.conversionRate - previousData.conversionRate) / previousData.conversionRate) * 100,
        changeType: latestData.conversionRate > previousData.conversionRate ? 'increase' : 'decrease',
        icon: Target,
        color: 'from-orange-500 to-red-400',
        trend: data.slice(-7).map(d => d.conversionRate * 100),
        format: 'percentage'
      },
      {
        title: 'Revenue',
        value: latestData.revenue,
        change: ((latestData.revenue - previousData.revenue) / previousData.revenue) * 100,
        changeType: latestData.revenue > previousData.revenue ? 'increase' : 'decrease',
        icon: DollarSign,
        color: 'from-yellow-500 to-amber-400',
        trend: data.slice(-7).map(d => d.revenue),
        format: 'currency'
      },
      {
        title: 'Bounce Rate',
        value: latestData.bounceRate * 100,
        change: ((latestData.bounceRate - previousData.bounceRate) / previousData.bounceRate) * 100,
        changeType: latestData.bounceRate < previousData.bounceRate ? 'increase' : 'decrease',
        icon: TrendingDown,
        color: 'from-red-500 to-pink-400',
        trend: data.slice(-7).map(d => d.bounceRate * 100),
        format: 'percentage'
      }
    ];

    setMetrics(calculatedMetrics);

    // Generate chart data
    const chartLabels = data.slice(-24).map(d => 
      new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    );

    setChartData({
      labels: chartLabels,
      datasets: [
        {
          label: 'Users',
          data: data.slice(-24).map(d => d.users),
          color: 'rgb(59, 130, 246)',
          type: 'line'
        },
        {
          label: 'Page Views',
          data: data.slice(-24).map(d => d.pageViews),
          color: 'rgb(168, 85, 247)',
          type: 'area'
        },
        {
          label: 'Sessions',
          data: data.slice(-24).map(d => d.sessions),
          color: 'rgb(34, 197, 94)',
          type: 'bar'
        }
      ]
    });

    // Generate device breakdown
    const devices: DeviceBreakdown[] = [
      { device: 'Monitor', count: 4567, percentage: 45.2, icon: Monitor, color: 'from-blue-500 to-cyan-400' },
      { device: 'Mobile', count: 3234, percentage: 32.1, icon: Smartphone, color: 'from-purple-500 to-pink-400' },
      { device: 'Tablet', count: 1234, percentage: 12.3, icon: Tablet, color: 'from-green-500 to-emerald-400' },
      { device: 'Smart TV', count: 567, percentage: 5.6, icon: Tv, color: 'from-orange-500 to-red-400' },
      { device: 'Gaming Console', count: 234, percentage: 2.3, icon: Gamepad2, color: 'from-yellow-500 to-amber-400' },
      { device: 'Wearable', count: 123, percentage: 1.2, icon: Watch, color: 'from-indigo-500 to-purple-400' }
    ];

    setDeviceBreakdown(devices);

    // Generate geographic data
    const geoData: GeographicData[] = [
      { country: 'United States', users: 5678, percentage: 35.2, flag: '🇺🇸', coordinates: { lat: 40.7128, lng: -74.0060 } },
      { country: 'United Kingdom', users: 2345, percentage: 14.5, flag: '🇬🇧', coordinates: { lat: 51.5074, lng: -0.1278 } },
      { country: 'Germany', users: 1890, percentage: 11.7, flag: '🇩🇪', coordinates: { lat: 52.5200, lng: 13.4050 } },
      { country: 'France', users: 1567, percentage: 9.7, flag: '🇫🇷', coordinates: { lat: 48.8566, lng: 2.3522 } },
      { country: 'Japan', users: 1234, percentage: 7.6, flag: '🇯🇵', coordinates: { lat: 35.6762, lng: 139.6503 } },
      { country: 'Canada', users: 987, percentage: 6.1, flag: '🇨🇦', coordinates: { lat: 43.6532, lng: -79.3832 } },
      { country: 'Australia', users: 876, percentage: 5.4, flag: '🇦🇺', coordinates: { lat: -33.8688, lng: 151.2093 } },
      { country: 'India', users: 654, percentage: 4.0, flag: '🇮🇳', coordinates: { lat: 28.6139, lng: 77.2090 } }
    ];

    setGeographicData(geoData);

    // Generate performance metrics
    const perfMetrics: PerformanceMetric[] = [
      {
        name: 'CPU Usage',
        value: latestData.cpuUsage,
        threshold: 80,
        status: latestData.cpuUsage > 80 ? 'critical' : latestData.cpuUsage > 60 ? 'warning' : 'good',
        trend: Math.random() * 20 - 10,
        icon: Cpu,
        unit: '%'
      },
      {
        name: 'Memory Usage',
        value: latestData.memoryUsage,
        threshold: 85,
        status: latestData.memoryUsage > 85 ? 'critical' : latestData.memoryUsage > 70 ? 'warning' : 'good',
        trend: Math.random() * 20 - 10,
        icon: HardDrive,
        unit: '%'
      },
      {
        name: 'Network Traffic',
        value: latestData.networkTraffic / 1000000,
        threshold: 10,
        status: latestData.networkTraffic > 10000000 ? 'critical' : latestData.networkTraffic > 5000000 ? 'warning' : 'good',
        trend: Math.random() * 20 - 10,
        icon: Wifi,
        unit: 'MB/s'
      },
      {
        name: 'Error Rate',
        value: latestData.errorRate * 100,
        threshold: 5,
        status: latestData.errorRate > 0.05 ? 'critical' : latestData.errorRate > 0.02 ? 'warning' : 'good',
        trend: Math.random() * 20 - 10,
        icon: AlertTriangle,
        unit: '%'
      },
      {
        name: 'Response Time',
        value: latestData.responseTime,
        threshold: 1000,
        status: latestData.responseTime > 1000 ? 'critical' : latestData.responseTime > 500 ? 'warning' : 'good',
        trend: Math.random() * 20 - 10,
        icon: Timer,
        unit: 'ms'
      }
    ];

    setPerformanceMetrics(perfMetrics);
  }, [timeRange]);

  useEffect(() => {
    if (isRealtime) {
      const interval = setInterval(() => {
        // Update with new data
        const now = Date.now();
        const newData: AnalyticsData = {
          timestamp: now,
          users: Math.floor(Math.random() * 1000) + 500,
          pageViews: Math.floor(Math.random() * 5000) + 2000,
          sessions: Math.floor(Math.random() * 800) + 300,
          bounceRate: Math.random() * 0.5 + 0.2,
          avgSessionDuration: Math.random() * 300 + 60,
          conversionRate: Math.random() * 0.05 + 0.01,
          revenue: Math.random() * 10000 + 1000,
          cpuUsage: Math.random() * 80 + 20,
          memoryUsage: Math.random() * 70 + 30,
          networkTraffic: Math.random() * 1000000 + 500000,
          errorRate: Math.random() * 0.05,
          responseTime: Math.random() * 500 + 100
        };

        setAnalyticsData(prev => [...prev.slice(-99), newData]);
      }, 5000);

      return () => clearInterval(interval);
    }
  }, [isRealtime]);

  const formatValue = (value: number, format?: string): string => {
    switch (format) {
      case 'currency':
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
      case 'percentage':
        return `${value.toFixed(1)}%`;
      case 'time':
        return `${Math.floor(value / 60)}m ${Math.floor(value % 60)}s`;
      case 'number':
      default:
        return value.toLocaleString();
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'good': return 'text-green-400';
      case 'warning': return 'text-yellow-400';
      case 'critical': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  const getStatusBg = (status: string) => {
    switch (status) {
      case 'good': return 'bg-green-500/20';
      case 'warning': return 'bg-yellow-500/20';
      case 'critical': return 'bg-red-500/20';
      default: return 'bg-gray-500/20';
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-400 to-purple-600 bg-clip-text text-transparent mb-2">
              Analytics Dashboard
            </h1>
            <p className="text-gray-400">
              Real-time analytics and performance monitoring
            </p>
          </div>
          
          <div className="flex items-center space-x-4">
            {/* Time Range Selector */}
            <div className="flex items-center space-x-2">
              <Calendar className="w-5 h-5 text-gray-400" />
              <select
                value={timeRange}
                onChange={(e) => setTimeRange(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
              >
                {timeRanges.map(range => (
                  <option key={range.value} value={range.value}>
                    {range.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Metric Category Selector */}
            <div className="flex items-center space-x-2">
              <BarChart3 className="w-5 h-5 text-gray-400" />
              <select
                value={selectedMetric}
                onChange={(e) => setSelectedMetric(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
              >
                {metricsCategories.map(category => (
                  <option key={category.value} value={category.value}>
                    {category.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Realtime Toggle */}
            <motion.button
              onClick={() => setIsRealtime(!isRealtime)}
              className={cn(
                'px-4 py-2 rounded-lg transition-colors',
                isRealtime ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-300'
              )}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              {isRealtime ? 'Realtime' : 'Historical'}
            </motion.button>

            {/* Fullscreen Toggle */}
            <motion.button
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="p-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              {isFullscreen ? <Minimize2 className="w-5 h-5" /> : <Maximize2 className="w-5 h-5" />}
            </motion.button>

            {/* Refresh Button */}
            <motion.button
              onClick={() => window.location.reload()}
              className="p-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
              whileHover={{ scale: 1.05, rotate: 180 }}
              whileTap={{ scale: 0.95 }}
            >
              <RefreshCw className="w-5 h-5" />
            </motion.button>
          </div>
        </div>
      </header>

      {/* Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-6 mb-8">
        {metrics.map((metric, index) => (
          <motion.div
            key={metric.title}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
            className="bg-gray-800 border border-gray-700 rounded-xl p-6 hover:border-blue-500 transition-all duration-200"
          >
            <div className="flex items-center justify-between mb-4">
              <div className={`w-12 h-12 rounded-lg bg-gradient-to-r ${metric.color} flex items-center justify-center`}>
                <metric.icon className="w-6 h-6 text-white" />
              </div>
              <div className="flex items-center space-x-1">
                {metric.changeType === 'increase' && <ArrowUp className="w-4 h-4 text-green-400" />}
                {metric.changeType === 'decrease' && <ArrowDown className="w-4 h-4 text-red-400" />}
                <span className={cn(
                  'text-sm font-medium',
                  metric.changeType === 'increase' ? 'text-green-400' : 'text-red-400'
                )}>
                  {Math.abs(metric.change).toFixed(1)}%
                </span>
              </div>
            </div>
            
            <div className="mb-2">
              <div className="text-2xl font-bold text-white">
                {formatValue(metric.value as number, metric.format)}
              </div>
              <div className="text-sm text-gray-400">{metric.title}</div>
            </div>

            {/* Mini Trend Chart */}
            <div className="flex items-end space-x-1 h-8">
              {metric.trend.map((value, i) => (
                <div
                  key={i}
                  className="flex-1 bg-blue-500 rounded-t"
                  style={{ height: `${(value / Math.max(...metric.trend)) * 100}%` }}
                />
              ))}
            </div>
          </motion.div>
        ))}
      </div>

      {/* Main Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Traffic Chart */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className="bg-gray-800 border border-gray-700 rounded-xl p-6"
        >
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-semibold text-white">Traffic Overview</h3>
            <div className="flex space-x-2">
              <button className="px-3 py-1 bg-gray-700 text-white rounded-lg text-sm">1D</button>
              <button className="px-3 py-1 bg-blue-600 text-white rounded-lg text-sm">1W</button>
              <button className="px-3 py-1 bg-gray-700 text-white rounded-lg text-sm">1M</button>
            </div>
          </div>
          
          <div className="h-64 flex items-center justify-center">
            <LineChart className="w-full h-full text-blue-400" />
          </div>
        </motion.div>

        {/* Device Breakdown */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          className="bg-gray-800 border border-gray-700 rounded-xl p-6"
        >
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-semibold text-white">Device Breakdown</h3>
            <button className="p-2 hover:bg-gray-700 rounded-lg transition-colors">
              <MoreVertical className="w-4 h-4" />
            </button>
          </div>
          
          <div className="space-y-3">
            {deviceBreakdown.map((device) => (
              <div key={device.device} className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <device.icon className="w-5 h-5 text-gray-400" />
                  <span className="text-sm text-gray-300">{device.device}</span>
                </div>
                <div className="flex items-center space-x-3">
                  <div className="w-24 bg-gray-700 rounded-full h-2">
                    <div 
                      className={`h-full rounded-full bg-gradient-to-r ${device.color}`}
                      style={{ width: `${device.percentage}%` }}
                    />
                  </div>
                  <span className="text-sm text-gray-400 w-12 text-right">
                    {device.percentage}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Geographic Distribution */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-gray-800 border border-gray-700 rounded-xl p-6 mb-8"
      >
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold text-white">Geographic Distribution</h3>
          <button className="p-2 hover:bg-gray-700 rounded-lg transition-colors">
            <Download className="w-4 h-4" />
          </button>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {geographicData.map((country) => (
            <div key={country.country} className="flex items-center space-x-3 p-3 bg-gray-700 rounded-lg">
              <div className="text-2xl">{country.flag}</div>
              <div className="flex-1">
                <div className="text-sm font-medium text-white">{country.country}</div>
                <div className="text-xs text-gray-400">{country.users.toLocaleString()} users</div>
              </div>
              <div className="text-sm text-gray-300">{country.percentage}%</div>
            </div>
          ))}
        </div>
      </motion.div>

      {/* Performance Metrics */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-gray-800 border border-gray-700 rounded-xl p-6"
      >
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold text-white">Performance Metrics</h3>
          <div className="flex items-center space-x-2">
            <div className="flex items-center space-x-1">
              <div className="w-3 h-3 bg-green-400 rounded-full"></div>
              <span className="text-xs text-gray-400">Good</span>
            </div>
            <div className="flex items-center space-x-1">
              <div className="w-3 h-3 bg-yellow-400 rounded-full"></div>
              <span className="text-xs text-gray-400">Warning</span>
            </div>
            <div className="flex items-center space-x-1">
              <div className="w-3 h-3 bg-red-400 rounded-full"></div>
              <span className="text-xs text-gray-400">Critical</span>
            </div>
          </div>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          {performanceMetrics.map((metric) => (
            <div key={metric.name} className={`p-4 rounded-lg ${getStatusBg(metric.status)}`}>
              <div className="flex items-center justify-between mb-2">
                <metric.icon className={cn('w-5 h-5', getStatusColor(metric.status))} />
                <span className={cn('text-xs font-medium', getStatusColor(metric.status))}>
                  {metric.status.toUpperCase()}
                </span>
              </div>
              <div className="text-lg font-bold text-white mb-1">
                {metric.value.toFixed(1)}{metric.unit}
              </div>
              <div className="text-xs text-gray-400">{metric.name}</div>
              <div className="flex items-center mt-2">
                {metric.trend > 0 ? (
                  <ArrowUp className="w-3 h-3 text-green-400 mr-1" />
                ) : (
                  <ArrowDown className="w-3 h-3 text-red-400 mr-1" />
                )}
                <span className={cn('text-xs', metric.trend > 0 ? 'text-green-400' : 'text-red-400')}>
                  {Math.abs(metric.trend).toFixed(1)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
};

export default AnalyticsDashboard;
