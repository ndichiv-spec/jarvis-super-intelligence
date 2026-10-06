'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Activity, Wifi, WifiOff, Server, Database, Brain, 
  CheckCircle2, XCircle, AlertTriangle, RefreshCw 
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
  icon: string;
}

interface SystemHealth {
  overall_status: 'healthy' | 'degraded' | 'unhealthy';
  checks: HealthCheck[];
  uptime_seconds: number;
  last_check: string;
}

export function HealthMonitorWidget() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  const checkHealth = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/health/status', {
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
        setHealth(data.health);
        
        // Show recovery notification if status improved
        if (health && health.overall_status !== data.health.overall_status) {
          if (data.health.overall_status === 'healthy') {
            toast.success('System Restored', {
              description: 'All systems are now operational',
            });
          } else if (data.health.overall_status === 'degraded') {
            toast.warning('System Degraded', {
              description: 'Some services are experiencing issues',
            });
          }
        }
      }
    } catch (error) {
      console.error('Health check failed:', error);
      // Set degraded status on error
      setHealth({
        overall_status: 'unhealthy',
        checks: [],
        uptime_seconds: 0,
        last_check: new Date().toISOString(),
      });
    } finally {
      setLoading(false);
    }
  }, [health]);

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30000); // Check every 30 seconds
    return () => clearInterval(interval);
  }, [checkHealth]);

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
        return <CheckCircle2 className="h-4 w-4" />;
      case 'degraded':
        return <AlertTriangle className="h-4 w-4" />;
      case 'unhealthy':
        return <XCircle className="h-4 w-4" />;
      default:
        return <Activity className="h-4 w-4" />;
    }
  };

  const formatUptime = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  };

  if (loading) {
    return (
      <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-blue-500/30 backdrop-blur-xl">
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2 text-white">
            <Activity className="h-4 w-4 text-blue-400 animate-pulse" />
            System Health
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-8 bg-slate-700 rounded" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
    >
      <Card className={`bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 backdrop-blur-xl transition-all duration-300 ${
        health?.overall_status === 'healthy' 
          ? 'border-emerald-500/30 hover:border-emerald-400/50'
          : health?.overall_status === 'degraded'
          ? 'border-amber-500/30 hover:border-amber-400/50'
          : 'border-red-500/30 hover:border-red-400/50'
      }`}>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center justify-between text-white">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-blue-400" />
              System Health
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={checkHealth}
                className="h-6 w-6 p-0 text-cyan-300 hover:text-cyan-200"
              >
                <RefreshCw className="h-3 w-3" />
              </Button>
              <Badge 
                variant="outline" 
                className={`text-[10px] ${getStatusColor(health?.overall_status || 'unknown')}`}
              >
                {getStatusIcon(health?.overall_status || 'unknown')}
                <span className="ml-1 capitalize">{health?.overall_status}</span>
              </Badge>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Uptime */}
          <div className="p-3 rounded-lg bg-slate-800/50 border border-blue-500/20">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-cyan-200/70">System Uptime</span>
              <Server className="h-3 w-3 text-cyan-400" />
            </div>
            <p className="text-lg font-bold text-white">
              {formatUptime(health?.uptime_seconds || 0)}
            </p>
          </div>

          {/* Health Checks Summary */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-cyan-200/70">Service Status</span>
              <span className="text-xs text-white">
                {health?.checks.filter(c => c.status === 'healthy').length}/{health?.checks.length || 0}
              </span>
            </div>

            {/* Progress Bar */}
            <Progress 
              value={health?.checks.length ? 
                (health.checks.filter(c => c.status === 'healthy').length / health.checks.length) * 100 : 0
              } 
              className="h-2 bg-emerald-500" 
            />
          </div>

          {/* Expandable Details */}
          {expanded && health?.checks && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="space-y-2 pt-2 border-t border-blue-500/20"
            >
              {health.checks.map((check, idx) => (
                <div key={idx} className="flex items-center justify-between p-2 rounded bg-slate-800/30">
                  <div className="flex items-center gap-2">
                    {getStatusIcon(check.status)}
                    <span className="text-xs text-cyan-200/80 capitalize">
                      {check.name.replace(/_/g, ' ')}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-slate-400">
                      {check.response_time_ms}ms
                    </span>
                    <Badge 
                      variant="outline" 
                      className={`text-[9px] ${getStatusColor(check.status)}`}
                    >
                      {check.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </motion.div>
          )}

          {/* Toggle Details */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setExpanded(!expanded)}
            className="w-full text-xs text-cyan-300 hover:text-cyan-200 hover:bg-blue-500/10"
          >
            {expanded ? 'Hide Details' : 'Show Details'}
          </Button>

          {/* Last Check */}
          <div className="pt-2 border-t border-blue-500/20">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-cyan-200/50">Last Check</span>
              <span className="text-[10px] text-cyan-200/70">
                {health?.last_check ? new Date(health.last_check).toLocaleTimeString() : 'N/A'}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
