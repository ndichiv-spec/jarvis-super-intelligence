'use client';

import { useEffect, useMemo, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  Activity, CheckCircle, XCircle, AlertTriangle, RefreshCw,
  TrendingUp, Server,
} from 'lucide-react';
import { Area, AreaChart, ResponsiveContainer, Tooltip } from 'recharts';
import { useMonitoringStore } from '@/features/monitoring/store';
import { useBackend, useSystemUsage, usePlatformStore } from '@/stores/platform-store';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { ActivityFabric } from '@/components/shell/activity-fabric';
import { UniversalInspector } from '@/components/shell/universal-inspector';
import type { InspectorObject } from '@/components/shell/universal-inspector';
import type { ResourceStatus } from '@/lib/types/platform';

export default function MonitoringPage() {
  const healthReport = useMonitoringStore((state) => state.healthReport);
  const isLoading = useMonitoringStore((state) => state.isLoading);
  const error = useMonitoringStore((state) => state.error);
  const loadHealthReport = useMonitoringStore((state) => state.loadHealthReport);
  const [inspectorObject, setInspectorObject] = useState<InspectorObject | null>(null);

  const backend = useBackend();
  const systemUsage = useSystemUsage();
  const refreshBackend = usePlatformStore((state) => state.refreshBackend);
  const systemHistory = usePlatformStore((state) => state.systemHistory);
  const cpuHistory = useMemo(
    () => systemHistory.map((sample) => ({
      time: new Date(sample.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      value: sample.cpu_percent,
    })),
    [systemHistory],
  );

  const fetchData = useCallback(async () => {
    await Promise.all([loadHealthReport(), refreshBackend()]);
  }, [loadHealthReport, refreshBackend]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

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

  const displayStatus = healthReport?.status ?? (error ? 'unavailable' : 'loading');
  const healthScore = healthReport?.health_score ?? null;
  const checks = healthReport?.checks ?? [];
  const totalChecks = checks.length;
  const healthyChecks = checks.filter((check) => check.status === 'ok' || check.status === 'healthy').length;

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
          { key: 'health_score', label: 'Health Score', value: healthScore === null ? 'Unavailable' : `${Math.round(healthScore)}%` },
          { key: 'timestamp', label: 'Timestamp', value: healthReport.timestamp || '—' },
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
        fields: checks.map((check) => ({
          key: check.name,
          label: check.name,
          value: check.status,
        })),
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
                  <div className={`w-4 h-4 rounded-full ${getStatusColor(displayStatus)}`} />
                  <div>
                    <p className="text-sm text-muted-foreground">Overall Status</p>
                    <p className="text-2xl font-bold capitalize">{displayStatus}</p>
                  </div>
                </div>
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">Health Score</p>
                  <p className="text-4xl font-bold text-blue-500">{healthScore === null ? '—' : `${Math.round(healthScore)}%`}</p>
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
        {systemUsage ? (
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
        ) : (
          <div role="status" className="mb-6 rounded-lg border border-amber-400/20 bg-amber-400/5 p-4 text-sm text-muted-foreground">
            Host resource metrics are unavailable{backend.error ? `: ${backend.error}` : ' for the latest sample'}.
          </div>
        )}

        {/* Keep only CPU samples collected by the shared runtime monitor. */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="mb-6"
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><TrendingUp className="h-5 w-5" />CPU Usage</CardTitle>
              <CardDescription>Recent CPU samples from the shared monitoring runtime.</CardDescription>
            </CardHeader>
            <CardContent>
              {cpuHistory.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={cpuHistory}>
                    <Tooltip formatter={(value) => [`${value}%`, 'CPU']} />
                    <Area type="monotone" dataKey="value" stroke="#00d4ff" fill="#00d4ff" fillOpacity={0.3} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : <p role="status" className="py-16 text-center text-sm text-muted-foreground">CPU telemetry is unavailable.</p>}
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
                {checks.map((check) => (
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
                  <p role={error ? "alert" : "status"} className="text-xs text-muted-foreground">
                    {error || (isLoading ? "Loading health checks..." : "No health checks were returned.")}
                  </p>
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
