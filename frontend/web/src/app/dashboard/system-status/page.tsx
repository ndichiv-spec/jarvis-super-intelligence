'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { 
  Activity, Server, Database, Brain, Zap, 
  CheckCircle2, XCircle, AlertTriangle, RefreshCw,
  Cpu, MemoryStick as Memory, HardDrive, Clock
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';

interface HealthCheck {
  name: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  message: string;
  response_time_ms: number;
}

interface SystemHealth {
  overall_status: 'healthy' | 'degraded' | 'unhealthy';
  checks: HealthCheck[];
  uptime_seconds: number;
  last_check: string;
}

interface SystemMetrics {
  cpu_percent: number;
  memory_percent: number;
  memory_available_mb: number;
  disk_percent: number;
  process_count: number;
}

export default function SystemStatusPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  const fetchData = async () => {
    try {
      // Fetch health status
      const healthRes = await fetch('/api/v1/health/status');
      const healthData = await healthRes.json();
      
      if (healthData.success) {
        setHealth(healthData.health);
      }

      // Fetch system metrics
      const metricsRes = await fetch('/api/v1/dashboard/widgets/data/system-metrics');
      const metricsData = await metricsRes.json();
      
      if (metricsData.success) {
        setMetrics(metricsData.metrics);
      }

      setLastUpdate(new Date());
    } catch (error) {
      console.error('Failed to fetch system status:', error);
      toast.error('Failed to fetch system status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000); // Update every 10 seconds
    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'text-emerald-400 bg-emerald-500/20 border-emerald-400/50';
      case 'degraded':
        return 'text-amber-400 bg-amber-500/20 border-amber-400/50';
      case 'unhealthy':
        return 'text-red-400 bg-red-500/20 border-red-400/50';
      default:
        return 'text-slate-400 bg-slate-500/20 border-slate-400/50';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle2 className="h-5 w-5" />;
      case 'degraded':
        return <AlertTriangle className="h-5 w-5" />;
      case 'unhealthy':
        return <XCircle className="h-5 w-5" />;
      default:
        return <Activity className="h-5 w-5" />;
    }
  };

  const formatUptime = (seconds: number) => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    
    if (days > 0) return `${days}d ${hours}h ${minutes}m`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0e27] flex items-center justify-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center"
        >
          <Activity className="h-12 w-12 text-blue-400 animate-pulse mx-auto mb-4" />
          <p className="text-cyan-200">Loading system status...</p>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0e27] relative overflow-hidden">
      {/* Animated Background */}
      <div className="absolute inset-0 opacity-20">
        <div className="absolute inset-0" style={{
          backgroundImage: `
            linear-gradient(rgba(59, 130, 246, 0.1) 1px, transparent 1px),
            linear-gradient(90deg, rgba(59, 130, 246, 0.1) 1px, transparent 1px)
          `,
          backgroundSize: '50px 50px',
        }} />
      </div>

      {/* Glowing Orbs */}
      <div className="absolute top-20 left-20 w-96 h-96 bg-blue-500/20 rounded-full blur-3xl animate-pulse" />
      <div className="absolute bottom-20 right-20 w-96 h-96 bg-cyan-500/20 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />

      <div className="container mx-auto px-6 py-8 max-w-[1600px] relative z-10">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6">
              <div className="relative group">
                <div className={`h-16 w-16 rounded-2xl flex items-center justify-center shadow-2xl ${
                  health?.overall_status === 'healthy'
                    ? 'bg-gradient-to-br from-emerald-500 via-green-400 to-emerald-600 shadow-emerald-500/50'
                    : health?.overall_status === 'degraded'
                    ? 'bg-gradient-to-br from-amber-500 via-yellow-400 to-amber-600 shadow-amber-500/50'
                    : 'bg-gradient-to-br from-red-500 via-orange-400 to-red-600 shadow-red-500/50'
                }`}>
                  <Activity className="h-8 w-8 text-white" />
                </div>
                <div className={`absolute -inset-3 rounded-2xl blur-2xl animate-pulse ${
                  health?.overall_status === 'healthy'
                    ? 'bg-gradient-to-br from-emerald-500/30 via-green-400/30 to-emerald-600/30'
                    : health?.overall_status === 'degraded'
                    ? 'bg-gradient-to-br from-amber-500/30 via-yellow-400/30 to-amber-600/30'
                    : 'bg-gradient-to-br from-red-500/30 via-orange-400/30 to-red-600/30'
                }`} />
              </div>
              <div>
                <h1 className="text-4xl font-black bg-gradient-to-r from-blue-400 via-cyan-300 to-blue-400 bg-clip-text text-transparent">
                  JARVIS System Status
                </h1>
                <p className="text-cyan-200/80 mt-1 text-base">
                  Real-time system health and performance monitoring
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Button
                onClick={fetchData}
                variant="outline"
                size="sm"
                className="bg-slate-900/60 border-blue-500/30 text-cyan-300 hover:bg-blue-500/20"
              >
                <RefreshCw className="h-4 w-4 mr-2" />
                Refresh
              </Button>
              <Badge 
                variant="outline" 
                className={`text-sm ${getStatusColor(health?.overall_status || 'unknown')}`}
              >
                {getStatusIcon(health?.overall_status || 'unknown')}
                <span className="ml-2 capitalize">{health?.overall_status}</span>
              </Badge>
            </div>
          </div>
        </motion.div>

        {/* Overall Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          {/* Uptime */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-blue-500/30 backdrop-blur-xl">
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2 text-white">
                  <Clock className="h-4 w-4 text-cyan-400" />
                  System Uptime
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold text-white">
                  {formatUptime(health?.uptime_seconds || 0)}
                </p>
                <p className="text-xs text-cyan-200/60 mt-2">
                  Last updated: {lastUpdate.toLocaleTimeString()}
                </p>
              </CardContent>
            </Card>
          </motion.div>

          {/* Healthy Services */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-emerald-500/30 backdrop-blur-xl">
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2 text-white">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  Healthy Services
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold text-emerald-400">
                  {health?.checks.filter(c => c.status === 'healthy').length}/{health?.checks.length || 0}
                </p>
                <Progress 
                  value={health?.checks.length ? 
                    (health.checks.filter(c => c.status === 'healthy').length / health.checks.length) * 100 : 0
                  } 
                  className="h-2 mt-2 bg-emerald-500" 
                />
              </CardContent>
            </Card>
          </motion.div>

          {/* Average Response Time */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-purple-500/30 backdrop-blur-xl">
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2 text-white">
                  <Zap className="h-4 w-4 text-purple-400" />
                  Avg Response Time
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold text-purple-400">
                  {health?.checks.length
                    ? Math.round(health.checks.reduce((sum, c) => sum + c.response_time_ms, 0) / health.checks.length)
                    : 0}ms
                </p>
                <p className="text-xs text-cyan-200/60 mt-2">
                  Across all services
                </p>
              </CardContent>
            </Card>
          </motion.div>
        </div>

        {/* Service Health Checks */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
        >
          <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-blue-500/30 backdrop-blur-xl mb-8">
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2 text-white">
                <Server className="h-5 w-5 text-blue-400" />
                Service Health Checks
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {health?.checks.map((check, idx) => (
                  <motion.div
                    key={idx}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.1 * idx }}
                    className="flex items-center justify-between p-4 rounded-lg bg-slate-800/50 border border-blue-500/20 hover:border-blue-400/40 transition-all"
                  >
                    <div className="flex items-center gap-4">
                      <div className={`p-2 rounded-lg ${getStatusColor(check.status)}`}>
                        {getStatusIcon(check.status)}
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-white capitalize">
                          {check.name.replace(/_/g, ' ')}
                        </p>
                        <p className="text-xs text-cyan-200/60 mt-1">
                          {check.message}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <p className="text-sm font-bold text-white">
                          {check.response_time_ms}ms
                        </p>
                        <p className="text-[10px] text-cyan-200/50">
                          Response Time
                        </p>
                      </div>
                      <Badge 
                        variant="outline" 
                        className={`text-xs ${getStatusColor(check.status)}`}
                      >
                        {check.status}
                      </Badge>
                    </div>
                  </motion.div>
                ))}
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* System Resources */}
        {metrics && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
          >
            <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-blue-500/30 backdrop-blur-xl">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2 text-white">
                  <Cpu className="h-5 w-5 text-blue-400" />
                  System Resources
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {/* CPU */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Cpu className="h-4 w-4 text-cyan-400" />
                        <span className="text-sm text-cyan-200/70">CPU Usage</span>
                      </div>
                      <span className="text-lg font-bold text-white">{metrics.cpu_percent}%</span>
                    </div>
                    <Progress value={metrics.cpu_percent} className="h-3" />
                  </div>

                  {/* Memory */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Memory className="h-4 w-4 text-purple-400" />
                        <span className="text-sm text-cyan-200/70">Memory</span>
                      </div>
                      <div className="text-right">
                        <span className="text-lg font-bold text-white">{metrics.memory_percent}%</span>
                        <p className="text-xs text-cyan-200/50">
                          {Math.round(metrics.memory_available_mb / 1024)} GB available
                        </p>
                      </div>
                    </div>
                    <Progress value={metrics.memory_percent} className="h-3" />
                  </div>

                  {/* Disk */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <HardDrive className="h-4 w-4 text-amber-400" />
                        <span className="text-sm text-cyan-200/70">Disk Usage</span>
                      </div>
                      <span className="text-lg font-bold text-white">{metrics.disk_percent}%</span>
                    </div>
                    <Progress value={metrics.disk_percent} className="h-3" />
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </div>
    </div>
  );
}
