'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  Activity, CheckCircle, XCircle, AlertTriangle, RefreshCw,
  TrendingUp, Server,
} from 'lucide-react';
import {
  AreaChart, Area, ResponsiveContainer,
} from 'recharts';
import { useMonitoringStore } from '@/features/monitoring/store';
import { usePlatformStore, useActivity, useBackend, useSystemUsage } from '@/stores/platform-store';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';
import { ActivityFabric } from '@/components/shell/activity-fabric';
import { UniversalInspector } from '@/components/shell/universal-inspector';
import type { InspectorObject } from '@/components/shell/universal-inspector';
import type { ResourceStatus } from '@/lib/types/platform';
import monitoringApi from '@/features/monitoring/api';

/** Build a real time-series from the monitoring store's data.
 *  The metrics endpoint returns flat {cpu_percent, memory:{percent,...}, disk, processes}
 *  and the health-report returns {health_score, status, system:{...}, checks:[...]}. */
function buildTimeSeries(metrics: any, healthReport: any): Array<{ time: string; value: number; p95: number; p50: number; requests: number }> {
  const now = new Date();
  // The actual backend returns flat metrics at top level
  const currentCpu = typeof metrics?.cpu_percent === 'number' ? metrics.cpu_percent
    : typeof metrics?.system?.cpu_percent === 'number' ? metrics.system.cpu_percent
    : typeof healthReport?.health_score === 'number' ? 100 - healthReport.health_score
    : 0;

  // If we have no history points, show a single live sample
  const pts: any[] = metrics?.history ?? healthReport?.history ?? [];
  if (pts.length === 0) {
    const v = Math.max(0, Math.min(100, currentCpu));
    return [{ time: 'now', value: v, p95: v + 5, p50: Math.max(0, v - 2), requests: 0 }];
  }

  return pts.slice(-30).map((pt: any, idx: number) => {
    const t = new Date(pt.timestamp || now.getTime() - (30 - idx) * 60000);
    const cpu = typeof pt.cpu_percent === 'number' ? pt.cpu_percent
      : typeof pt.system?.cpu_percent === 'number' ? pt.system.cpu_percent
      : currentCpu;
    const v = Math.max(0, Math.min(100, cpu));
    return {
      time: t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      value: v,
      p95: v + 5,
      p50: Math.max(0, v - 2),
      requests: typeof pt.requests === 'number' ? pt.requests : 0,
    };
  });
}

export default function MonitoringPage() {
  const monitoring = useMonitoringStore();
  const { healthReport, metrics, isLoading, error, loadHealthReport, loadMetrics, loadHealth, loadRecoveryHistory } = monitoring;
  const [isRunning, setIsRunning] = useState(false);
  const [inspectorObject, setInspectorObject] = useState<InspectorObject | null>(null);

  const platform = usePlatformStore();
  const backend = useBackend();
  const systemUsage = useSystemUsage();

  const fetchData = useCallback(async () => {
    try {
      await Promise.all([
        loadHealthReport(),
        loadMetrics(),
        loadHealth(),
        loadRecoveryHistory(),
      ]);
      await platform.refreshSystem();
      await platform.refreshBackend();
      // Record an activity event for the manual refresh
      platform.addActivity({
        domain: 'system',
        operation: 'refresh',
        title: 'Monitoring data refreshed',
        detail: systemUsage ? `CPU ${systemUsage.cpu_percent.toFixed(1)}% · Memory ${systemUsage.memory_percent.toFixed(1)}%` : 'Data refreshed',
        severity: 'info',
      });
    } catch (error) {
      platform.addActivity({
        domain: 'system',
        operation: 'refresh_failed',
        title: 'Monitoring refresh failed',
        detail: error instanceof Error ? error.message : 'Unknown error',
        severity: 'high',
      });
    }
  }, [loadHealthReport, loadMetrics, loadHealth, loadRecoveryHistory, platform, systemUsage]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Sync platform store on mount
  useEffect(() => {
    platform.refreshAll();
    const unsub = platform.subscribeToEvents();
    return unsub;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRunOptimization = async () => {
    setIsRunning(true);
    try {
      const result = await monitoringApi.triggerOptimization();
      if (result?.success) {
        platform.addActivity({
          domain: 'system',
          operation: 'optimization',
          title: 'Self-optimization completed',
          detail: 'Optimization cycle applied',
          severity: 'info',
        });
        toast.success('Optimization cycle completed');
        fetchData();
      } else {
        toast.warning('Optimization returned no report');
      }
    } catch (error: any) {
      platform.addActivity({
        domain: 'system',
        operation: 'optimization_failed',
        title: 'Self-optimization failed',
        detail: error.message,
        severity: 'high',
      });
      toast.error(`Optimization failed: ${error.message}`);
    } finally {
      setIsRunning(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'healthy': return 'bg-green-500';
      case 'degraded': return 'bg-yellow-500';
      case 'unhealthy': return 'bg-orange-500';
      case 'critical': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case 'healthy': return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'degraded': return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
      case 'unhealthy': return <XCircle className="h-4 w-4 text-orange-500" />;
      case 'critical': return <XCircle className="h-4 w-4 text-red-500" />;
      default: return <Activity className="h-4 w-4 text-gray-500" />;
    }
  };

  const timeData = buildTimeSeries(metrics, healthReport);

  // The actual backend returns: { health_score, status, system, checks }
  // The type HealthReport says: { current_status, health_rate_percent, latest_checks, ... }
  // We access both shapes safely with optional chaining.
  const rawHR: any = healthReport as any;
  const displayStatus = rawHR?.status || rawHR?.current_status || 'unknown';
  const healthScore = Math.min(100, rawHR?.health_score ?? rawHR?.health_rate_percent ?? 0);
  const checks = rawHR?.checks ?? rawHR?.latest_checks ?? [];
  const totalChecks = checks.length;
  const healthyChecks = checks.filter((c: any) => c.status === 'ok' || c.status === 'healthy').length;

  // Build an inspector object for the health report
  const healthInspectorObject: InspectorObject | null = healthReport ? {
    id: 'health-report',
    type: 'health',
    title: 'Health Report',
    subtitle: displayStatus,
    status: displayStatus === 'healthy' ? 'completed' : 'degraded' as ResourceStatus,
    sections: [
      {
        id: 'identity',
        label: 'Identity',
        fields: [
          { key: 'status', label: 'Status', value: displayStatus },
          { key: 'health_score', label: 'Health Score', value: `${Math.round(healthScore)}%` },
          { key: 'timestamp', label: 'Timestamp', value: rawHR?.timestamp || '—' },
        ],
      },
      {
        id: 'metrics',
        label: 'System Metrics',
        fields: systemUsage ? [
          { key: 'cpu', label: 'CPU %', value: `${systemUsage.cpu_percent.toFixed(1)}` },
          { key: 'memory', label: 'Memory %', value: `${systemUsage.memory_percent.toFixed(1)}` },
          { key: 'disk', label: 'Disk %', value: `${systemUsage.disk_percent.toFixed(1)}` },
          { key: 'processes', label: 'Processes', value: systemUsage.processes.toString() },
          { key: 'memory_avail', label: 'Memory Available', value: `${Math.round(systemUsage.memory_available_mb)} MB` },
        ] : [{ key: 'no-data', label: 'Data', value: 'No system metrics available' }],
      },
      {
        id: 'checks',
        label: `Health Checks (${totalChecks})`,
        fields: checks.map((c: any) => ({
          key: c.name,
          label: c.name,
          value: c.status,
        })) || [],
      },
    ],
    relatedObjects: [
      { type: 'metrics', id: 'system-metrics', label: 'System Resources', onClick: () => setInspectorObject(null) },
    ],
  } : null;

  const handleHealthClick = () => {
    if (healthInspectorObject) setInspectorObject(healthInspectorObject);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)]">
      {/* Header */}
      <div className="flex items-center justify-between p-6 pb-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Activity className="h-8 w-8 text-blue-500" />
            Monitoring &amp; Observatory
          </h1>
          <p className="text-muted-foreground">System health, performance telemetry, and activity stream</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchData} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          {backend.lastChecked && (
            <span className="text-xs text-muted-foreground">
              Last checked {backend.lastChecked.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-y-auto px-6 pb-6">
        {/* Health Status Header */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
          <Card
            className="cursor-pointer hover:bg-white/[0.03] transition-colors"
            onClick={handleHealthClick}
          >
            <CardContent className="p-6">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                <div className="flex items-center gap-4">
                  <div className={`w-4 h-4 rounded-full ${getStatusColor(displayStatus)} animate-pulse`} />
                  <div>
                    <p className="text-sm text-muted-foreground">Overall Status</p>
                    <p className="text-2xl font-bold capitalize">{displayStatus}</p>
                  </div>
                </div>
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">Health Score</p>
                  <p className="text-4xl font-bold text-blue-500">{Math.round(healthScore)}%</p>
                </div>
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">Backend Latency</p>
                  <p className="text-2xl font-bold">{backend.latencyMs ? `${backend.latencyMs}ms` : '—'}</p>
                </div>
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">Health Checks</p>
                  <p className="text-2xl font-bold">{healthyChecks}/{totalChecks}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* System resource progress bars (real data) */}
        {systemUsage && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="mb-6"
          >
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><Server className="h-5 w-5" />System Resources (Real)</CardTitle>
                <CardDescription>Live resource usage from backend monitoring endpoints</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <div className="flex justify-between mb-2">
                    <span className="text-sm flex items-center gap-2">
                      <TrendingUp className="h-4 w-4" /> CPU
                    </span>
                    <span className="text-sm font-medium">{systemUsage.cpu_percent.toFixed(1)}%</span>
                  </div>
                  <Progress value={systemUsage.cpu_percent} className="h-2" />
                </div>
                <div>
                  <div className="flex justify-between mb-2">
                    <span className="text-sm">Memory</span>
                    <span className="text-sm font-medium">{systemUsage.memory_percent.toFixed(1)}%</span>
                  </div>
                  <Progress value={systemUsage.memory_percent} className="h-2" />
                </div>
                <div>
                  <div className="flex justify-between mb-2">
                    <span className="text-sm">Disk</span>
                    <span className="text-sm font-medium">{systemUsage.disk_percent.toFixed(1)}%</span>
                  </div>
                  <Progress value={systemUsage.disk_percent} className="h-2" />
                </div>
                <div className="text-[10px] text-muted-foreground/40 flex gap-4">
                  <span>{Math.round(systemUsage.memory_available_mb)} MB available</span>
                  <span>{systemUsage.processes} processes</span>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* CPU chart — real data, no Math.random */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="mb-6"
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><TrendingUp className="h-5 w-5" />CPU Usage</CardTitle>
              <CardDescription>Live CPU utilization (sampled every 15s)</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={timeData}>
                  <Area type="monotone" dataKey="value" stroke="#00d4ff" fill="#00d4ff" fillOpacity={0.3} />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </motion.div>

        {/* Activity stream + health checks */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Health Checks */}
          <div className="lg:col-span-1">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><CheckCircle className="h-5 w-5" />Health Checks</CardTitle>
                <CardDescription>{totalChecks} checks monitored</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {checks.map((check: any) => (
                  <div key={check.name} className="flex items-center justify-between p-2 rounded-lg bg-[hsl(222,47%,6%)] border border-white/5">
                    <div className="flex items-center gap-2">
                      {getStatusIcon(check.status)}
                      <span className="text-sm capitalize">{check.name}</span>
                    </div>
                    <Badge variant={check.status === 'ok' || check.status === 'healthy' ? 'default' : 'destructive'} className="text-xs">
                      {check.status}
                    </Badge>
                  </div>
                ))}
                {!checks.length && (
                  <p className="text-xs text-muted-foreground">Loading health checks...</p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Activity Stream — real platform events */}
          <div className="lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><Activity className="h-5 w-5" />Activity Stream</CardTitle>
                <CardDescription>Real-time platform events from the unified activity fabric</CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                <div className="h-[280px]">
                  <ActivityFabric maxItems={30} compact showFilters />
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      {/* Universal Inspector for health report */}
      <UniversalInspector
        object={inspectorObject}
        open={!!inspectorObject}
        onClose={() => setInspectorObject(null)}
      />
    </div>
  );
}
