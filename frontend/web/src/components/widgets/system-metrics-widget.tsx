'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Cpu, MemoryStick as Memory, HardDrive, Activity, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';

interface SystemMetrics {
  cpu_percent: number;
  memory_percent: number;
  memory_available_mb: number;
  disk_percent: number;
  process_count: number;
}

export function SystemMetricsWidget() {
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [consecutiveErrors, setConsecutiveErrors] = useState(0);

  const fetchMetrics = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/dashboard/widgets/data/system-metrics', {
        method: 'GET',
        headers: {
          'Cache-Control': 'no-cache',
        },
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const data = await response.json();
      
      if (data.success) {
        setMetrics(data.metrics);
        setError(null);
        setConsecutiveErrors(0);
      } else {
        throw new Error(data.message || 'Failed to fetch metrics');
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error';
      console.error('Failed to fetch system metrics:', errorMsg);
      setError(errorMsg);
      setConsecutiveErrors(prev => prev + 1);
      
      // Show toast notification after 3 consecutive errors
      if (consecutiveErrors >= 2) {
        toast.error('System Metrics Unavailable', {
          description: 'Unable to connect to backend. Retrying...',
        });
      }
    } finally {
      setLoading(false);
    }
  }, [consecutiveErrors]);

  useEffect(() => {
    fetchMetrics();
    
    // Adaptive polling: faster when errors occur
    const pollInterval = consecutiveErrors > 0 ? 2000 : 5000;
    const interval = setInterval(fetchMetrics, pollInterval);
    
    return () => clearInterval(interval);
  }, [fetchMetrics, consecutiveErrors]);

  if (error && !metrics) {
    return (
      <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-red-500/30 backdrop-blur-xl">
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2 text-white">
            <AlertTriangle className="h-4 w-4 text-red-400" />
            System Metrics
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <div className="text-center space-y-2">
              <AlertTriangle className="h-8 w-8 text-red-400 mx-auto" />
              <p className="text-xs text-red-300">Connection Error</p>
              <button
                onClick={fetchMetrics}
                className="text-xs text-blue-400 hover:text-blue-300 underline"
              >
                Retry
              </button>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (loading || !metrics) {
    return (
      <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-blue-500/30 backdrop-blur-xl">
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2 text-white">
            <Activity className="h-4 w-4 text-blue-400 animate-pulse" />
            System Metrics
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="animate-pulse">
                <div className="h-2 bg-slate-700 rounded mb-2" />
                <div className="h-4 bg-slate-700 rounded w-3/4" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const getMetricColor = (value: number) => {
    if (value < 50) return 'text-emerald-400';
    if (value < 75) return 'text-amber-400';
    return 'text-red-400';
  };

  const getProgressColor = (value: number) => {
    if (value < 50) return 'bg-emerald-500';
    if (value < 75) return 'bg-amber-500';
    return 'bg-red-500';
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
    >
      <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-blue-500/30 backdrop-blur-xl hover:border-blue-400/50 transition-all duration-300">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center justify-between text-white">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-blue-400" />
              System Metrics
            </div>
            <Badge variant="outline" className="bg-emerald-500/20 text-emerald-300 border-emerald-400/50 text-[10px]">
              Live
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* CPU */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Cpu className="h-3 w-3 text-cyan-400" />
                <span className="text-xs text-cyan-200/70">CPU Usage</span>
              </div>
              <span className={`text-sm font-bold ${getMetricColor(metrics.cpu_percent)}`}>
                {metrics.cpu_percent}%
              </span>
            </div>
            <Progress value={metrics.cpu_percent} className={`h-2 ${getProgressColor(metrics.cpu_percent)}`} />
          </div>

          {/* Memory */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Memory className="h-3 w-3 text-purple-400" />
                <span className="text-xs text-cyan-200/70">Memory</span>
              </div>
              <div className="text-right">
                <span className={`text-sm font-bold ${getMetricColor(metrics.memory_percent)}`}>
                  {metrics.memory_percent}%
                </span>
                <p className="text-[10px] text-cyan-200/50">
                  {Math.round(metrics.memory_available_mb / 1024)} GB available
                </p>
              </div>
            </div>
            <Progress value={metrics.memory_percent} className={`h-2 ${getProgressColor(metrics.memory_percent)}`} />
          </div>

          {/* Disk */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <HardDrive className="h-3 w-3 text-amber-400" />
                <span className="text-xs text-cyan-200/70">Disk Usage</span>
              </div>
              <span className={`text-sm font-bold ${getMetricColor(metrics.disk_percent)}`}>
                {metrics.disk_percent}%
              </span>
            </div>
            <Progress value={metrics.disk_percent} className={`h-2 ${getProgressColor(metrics.disk_percent)}`} />
          </div>

          {/* Processes */}
          <div className="pt-2 border-t border-blue-500/20">
            <div className="flex items-center justify-between">
              <span className="text-xs text-cyan-200/70">Active Processes</span>
              <span className="text-sm font-bold text-white">{metrics.process_count}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
