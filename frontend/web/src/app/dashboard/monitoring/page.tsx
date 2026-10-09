'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  Activity, CheckCircle, XCircle, AlertTriangle, RefreshCw, TrendingUp, Server,
} from 'lucide-react';
import {
  AreaChart, Area, ResponsiveContainer,
} from 'recharts';
import { useMonitoringStore } from '@/features/monitoring/store';
import { usePlatformStore, useBackend, useSystemUsage } from '@/stores/platform-store';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { ActivityFabric } from '@/components/shell/activity-fabric';
import { UniversalInspector } from '@/components/shell/universal-inspector';
import type { InspectorObject } from '@/components/shell/universal-inspector';
import type { ResourceStatus } from '@/lib/types/platform';

type JsonRecord = Record<string, unknown>;

interface CpuSample {
  time: string;
  value: number;
}

function isRecord(value: unknown): value is JsonRecord {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function readCpuPercent(value: unknown): number | null {
  if (!isRecord(value)) return null;
  const system = isRecord(value.system) ? value.system : null;
  const cpu = typeof value.cpu_percent === 'number'
    ? value.cpu_percent
    : typeof system?.cpu_percent === 'number'
      ? system.cpu_percent
      : null;
  return cpu === null ? null : Math.max(0, Math.min(100, cpu));
}

function parseCpuSample(value: unknown): CpuSample | null {
  if (!isRecord(value)) return null;
  const cpu = readCpuPercent(value);
  if (cpu === null) return null;

  const timestamp = value.timestamp;
  const date = typeof timestamp === 'number' || typeof timestamp === 'string'
    ? new Date(timestamp)
    : null;
  return {
    time: date && !Number.isNaN(date.getTime())
      ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : 'Time unavailable',
    value: cpu,
  };
}

function buildTimeSeries(metrics: unknown, healthReport: unknown): CpuSample[] {
  const metricHistory = isRecord(metrics) && Array.isArray(metrics.history) ? metrics.history : [];
  const reportHistory = isRecord(healthReport) && Array.isArray(healthReport.history) ? healthReport.history : [];
  const history = metricHistory.length > 0 ? metricHistory : reportHistory;
  const samples = history.map(parseCpuSample).filter((sample): sample is CpuSample => sample !== null).slice(-30);
  if (samples.length > 0) return samples;

  const currentCpu = readCpuPercent(metrics) ?? readCpuPercent(healthReport);
  return currentCpu === null ? [] : [{ time: 'Current', value: currentCpu }];
}

interface HealthCheck {
  name: string;
  status: string;
}

export default function MonitoringPage() {
  const monitoring = useMonitoringStore();
  const { healthReport, metrics, isLoading, error, loadHealthReport, loadMetrics, loadHealth, loadRecoveryHistory } = monitoring;
  const [inspectorObject, setInspectorObject] = useState<InspectorObject | null>(null);

  const addActivity = usePlatformStore((state) => state.addActivity);
  const backend = useBackend();
  const systemUsage = useSystemUsage();

  const fetchData = useCallback(async (recordActivity = false) => {
    try {
      await Promise.all([
        loadHealthReport(),
        loadMetrics(),
        loadHealth(),
        loadRecoveryHistory(),
      ]);
      if (recordActivity) {
        addActivity({
          domain: 'system',
          operation: 'refresh',
          title: 'Monitoring refresh requested',
          detail: 'A manual request for monitoring reports was made.',
          severity: 'info',
        });
      }
    } catch (error) {
      if (recordActivity) {
        addActivity({
          domain: 'system',
          operation: 'refresh_failed',
          title: 'Monitoring refresh failed',
          detail: error instanceof Error ? error.message : 'Unknown error',
          severity: 'high',
        });
      }
    }
  }, [loadHealthReport, loadMetrics, loadHealth, loadRecoveryHistory, addActivity]);

  useEffect(() => {
    void fetchData();
    const interval = setInterval(() => void fetchData(), 15000);
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

  const timeData = buildTimeSeries(metrics, healthReport);

  // The actual backend returns: { health_score, status, system, checks }
  // The type HealthReport says: { current_status, health_rate_percent, latest_checks, ... }
  // We access both shapes safely with optional chaining.
  const rawHR: JsonRecord = isRecord(healthReport) ? healthReport : {};
  const displayStatus = typeof rawHR.status === 'string'
    ? rawHR.status
    : typeof rawHR.current_status === 'string'
      ? rawHR.current_status
      : 'not reported';
  const reportedHealthScore = typeof rawHR.health_score === 'number'
    ? rawHR.health_score
    : typeof rawHR.health_rate_percent === 'number'
      ? rawHR.health_rate_percent
      : null;
  const healthScore = reportedHealthScore === null
    ? null
    : Math.max(0, Math.min(100, reportedHealthScore));
  const rawChecks: unknown[] = Array.isArray(rawHR.checks)
    ? rawHR.checks
    : Array.isArray(rawHR.latest_checks)
      ? rawHR.latest_checks
      : [];
  const checks: HealthCheck[] = rawChecks.filter(isRecord).map((check: JsonRecord) => ({
    name: typeof check.name === 'string' ? check.name : 'Unnamed check',
    status: typeof check.status === 'string' ? check.status : 'unknown',
  }));
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
          { key: 'health_score', label: 'Health Score', value: healthScore === null ? 'Not reported' : `${Math.round(healthScore)}%` },
          { key: 'timestamp', label: 'Timestamp', value: typeof rawHR.timestamp === 'string' ? rawHR.timestamp : typeof rawHR.last_check === 'string' ? rawHR.last_check : '—' },
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
            <Activity className="h-8 w-8 text-indigo-300" />
            Monitoring &amp; Observatory
          </h1>
          <p className="text-muted-foreground">System health, reported performance telemetry, and recorded workspace activity</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void fetchData(true)} disabled={isLoading}>
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
                  <p className="text-4xl font-bold text-indigo-300">{healthScore === null ? '—' : `${Math.round(healthScore)}%`}</p>
                </div>
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">Backend Latency</p>
                  <p className="text-2xl font-bold">{backend.latencyMs ? `${backend.latencyMs}ms` : '—'}</p>
                </div>
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">Health Checks</p>
                  <p className="text-2xl font-bold">{totalChecks > 0 ? `${healthyChecks}/${totalChecks}` : '—'}</p>
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
                <CardTitle className="flex items-center gap-2"><Server className="h-5 w-5" />System resources</CardTitle>
                <CardDescription>Latest resource values reported by the monitoring service</CardDescription>
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

        {/* CPU chart uses only measurements returned by monitoring endpoints. */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="mb-6"
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><TrendingUp className="h-5 w-5" />CPU Usage</CardTitle>
              <CardDescription>CPU measurements returned by the monitoring service</CardDescription>
            </CardHeader>
            <CardContent>
              {timeData.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={timeData}>
                    <Area type="monotone" dataKey="value" stroke="#818cf8" fill="#818cf8" fillOpacity={0.3} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <p className="py-16 text-center text-sm text-muted-foreground" role="status">
                  {isLoading ? 'Loading CPU measurements…' : 'CPU measurements have not been reported.'}
                </p>
              )}
            </CardContent>
          </Card>
        </motion.div>

        {/* Recorded activity + health checks */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Health Checks */}
          <div className="lg:col-span-1">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><CheckCircle className="h-5 w-5" />Health Checks</CardTitle>
                <CardDescription>{totalChecks > 0 ? `${totalChecks} checks reported` : 'Health-check data from the monitoring service'}</CardDescription>
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
                  <p className="text-xs text-muted-foreground" role="status">
                    {isLoading ? 'Loading health checks…' : error ? `Unable to load health checks: ${error}` : 'No health checks were reported.'}
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Activity Stream — real platform events */}
          <div className="lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><Activity className="h-5 w-5" />Recent activity</CardTitle>
                <CardDescription>Recorded workspace activity. Server-pushed live events are not configured.</CardDescription>
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
