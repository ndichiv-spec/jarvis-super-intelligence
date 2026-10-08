"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Activity, Cpu, HardDrive, Wifi, Zap, Server, Database,
  AlertTriangle, TrendingUp, TrendingDown, RefreshCw, Settings,
  BarChart3, LineChart, PieChart, Radar, Gauge, Timer,
  MemoryStick, Globe, Shield, Cloud, Terminal, Code
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

interface SystemMetrics {
  timestamp: string;
  cpu_usage: number;
  memory_usage: number;
  disk_usage: number;
  network_in: number;
  network_out: number;
  gpu_usage?: number;
  temperature: number;
  active_processes: number;
  uptime: string;
  response_time: number;
  error_rate: number;
  throughput: number;
}

interface ServiceStatus {
  name: string;
  status: 'healthy' | 'warning' | 'critical' | 'offline';
  response_time: number;
  last_check: string;
  dependencies: string[];
  metrics: {
    cpu: number;
    memory: number;
    requests_per_second: number;
  };
}

interface Alert {
  id: string;
  type: 'error' | 'warning' | 'info';
  message: string;
  timestamp: string;
  acknowledged: boolean;
  severity: 'low' | 'medium' | 'high' | 'critical';
}

export default function RealTimeMonitoring() {
  const [metrics, setMetrics] = useState<SystemMetrics>({
    timestamp: new Date().toISOString(),
    cpu_usage: 0,
    memory_usage: 0,
    disk_usage: 0,
    network_in: 0,
    network_out: 0,
    gpu_usage: 0,
    temperature: 0,
    active_processes: 0,
    uptime: "0h 0m 0s",
    response_time: 0,
    error_rate: 0,
    throughput: 0,
  });

  const [services, setServices] = useState<ServiceStatus[]>([
    {
      name: "AI Engine",
      status: "healthy",
      response_time: 45,
      last_check: new Date().toISOString(),
      dependencies: ["Database", "Redis"],
      metrics: { cpu: 25, memory: 40, requests_per_second: 120 }
    },
    {
      name: "API Gateway",
      status: "healthy",
      response_time: 12,
      last_check: new Date().toISOString(),
      dependencies: ["Auth Service", "Load Balancer"],
      metrics: { cpu: 15, memory: 30, requests_per_second: 450 }
    },
    {
      name: "Database",
      status: "healthy",
      response_time: 8,
      last_check: new Date().toISOString(),
      dependencies: [],
      metrics: { cpu: 35, memory: 60, requests_per_second: 280 }
    },
    {
      name: "Redis Cache",
      status: "healthy",
      response_time: 2,
      last_check: new Date().toISOString(),
      dependencies: [],
      metrics: { cpu: 5, memory: 20, requests_per_second: 1200 }
    },
    {
      name: "File Storage",
      status: "warning",
      response_time: 120,
      last_check: new Date().toISOString(),
      dependencies: ["Database"],
      metrics: { cpu: 45, memory: 70, requests_per_second: 85 }
    }
  ]);

  const [alerts, setAlerts] = useState<Alert[]>([
    {
      id: "1",
      type: "warning",
      message: "File Storage response time exceeding threshold",
      timestamp: new Date().toISOString(),
      acknowledged: false,
      severity: "medium"
    },
    {
      id: "2",
      type: "info",
      message: "Scheduled maintenance in 2 hours",
      timestamp: new Date().toISOString(),
      acknowledged: false,
      severity: "low"
    }
  ]);

  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState("5");
  const [historicalData, setHistoricalData] = useState<SystemMetrics[]>([]);

  // Simulate real-time data updates
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      const newMetrics: SystemMetrics = {
        timestamp: new Date().toISOString(),
        cpu_usage: Math.random() * 30 + 20,
        memory_usage: Math.random() * 20 + 40,
        disk_usage: 45 + Math.random() * 10,
        network_in: Math.random() * 1000000,
        network_out: Math.random() * 800000,
        gpu_usage: Math.random() * 40 + 10,
        temperature: 45 + Math.random() * 20,
        active_processes: Math.floor(Math.random() * 50 + 100),
        uptime: calculateUptime(),
        response_time: Math.random() * 50 + 10,
        error_rate: Math.random() * 0.5,
        throughput: Math.random() * 1000 + 500,
      };

      setMetrics(newMetrics);
      setHistoricalData(prev => [...prev.slice(-100), newMetrics]);

      // Update service statuses
      setServices(prev => prev.map(service => ({
        ...service,
        status: Math.random() > 0.9 ? 'warning' : 'healthy',
        response_time: Math.max(5, service.response_time + (Math.random() - 0.5) * 20),
        last_check: new Date().toISOString(),
        metrics: {
          cpu: Math.max(0, Math.min(100, service.metrics.cpu + (Math.random() - 0.5) * 10)),
          memory: Math.max(0, Math.min(100, service.metrics.memory + (Math.random() - 0.5) * 10)),
          requests_per_second: Math.max(0, service.metrics.requests_per_second + (Math.random() - 0.5) * 50)
        }
      })));
    }, parseInt(refreshInterval) * 1000);

    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval]);

  const calculateUptime = () => {
    const hours = Math.floor(Math.random() * 720);
    const minutes = Math.floor(Math.random() * 60);
    return `${hours}h ${minutes}m`;
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy': return 'text-green-400';
      case 'warning': return 'text-yellow-400';
      case 'critical': return 'text-red-400';
      case 'offline': return 'text-gray-400';
      default: return 'text-gray-400';
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'healthy': return <Badge className="bg-green-500">Healthy</Badge>;
      case 'warning': return <Badge className="bg-yellow-500">Warning</Badge>;
      case 'critical': return <Badge className="bg-red-500">Critical</Badge>;
      case 'offline': return <Badge className="bg-gray-500">Offline</Badge>;
      default: return <Badge className="bg-gray-500">Unknown</Badge>;
    }
  };

  const getAlertIcon = (type: string) => {
    switch (type) {
      case 'error': return <AlertTriangle className="w-4 h-4 text-red-400" />;
      case 'warning': return <AlertTriangle className="w-4 h-4 text-yellow-400" />;
      case 'info': return <Activity className="w-4 h-4 text-blue-400" />;
      default: return <Activity className="w-4 h-4 text-gray-400" />;
    }
  };

  const acknowledgeAlert = (alertId: string) => {
    setAlerts(prev => prev.map(alert => 
      alert.id === alertId ? { ...alert, acknowledged: true } : alert
    ));
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-cyan-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
            Real-Time Monitoring
          </h1>
          <p className="text-muted-foreground/60 mt-1">
            Live system performance and health metrics
          </p>
        </div>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <Switch
              checked={autoRefresh}
              onCheckedChange={setAutoRefresh}
            />
            <span className="text-sm">Auto Refresh</span>
          </div>
          <Select value={refreshInterval} onValueChange={setRefreshInterval}>
            <SelectTrigger className="w-20">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1">1s</SelectItem>
              <SelectItem value="5">5s</SelectItem>
              <SelectItem value="10">10s</SelectItem>
              <SelectItem value="30">30s</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm">
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </Button>
        </div>
      </motion.div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1 }}
        >
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium text-gray-400">CPU Usage</CardTitle>
                <Cpu className="w-4 h-4 text-blue-400" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-white">
                {metrics.cpu_usage.toFixed(1)}%
              </div>
              <Progress value={metrics.cpu_usage} className="mt-2" />
              <p className="text-xs text-gray-400 mt-1">
                {metrics.active_processes} active processes
              </p>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2 }}
        >
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium text-gray-400">Memory Usage</CardTitle>
                <MemoryStick className="w-4 h-4 text-green-400" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-white">
                {metrics.memory_usage.toFixed(1)}%
              </div>
              <Progress value={metrics.memory_usage} className="mt-2" />
              <p className="text-xs text-gray-400 mt-1">
                {metrics.gpu_usage ? `GPU: ${metrics.gpu_usage.toFixed(1)}%` : 'No GPU'}
              </p>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.3 }}
        >
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium text-gray-400">Response Time</CardTitle>
                <Gauge className="w-4 h-4 text-purple-400" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-white">
                {metrics.response_time.toFixed(0)}ms
              </div>
              <div className="flex items-center mt-2">
                <TrendingUp className="w-3 h-3 text-green-400 mr-1" />
                <span className="text-xs text-green-400">-5% from last hour</span>
              </div>
              <p className="text-xs text-gray-400 mt-1">
                {metrics.throughput.toFixed(0)} req/s
              </p>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.4 }}
        >
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium text-gray-400">System Health</CardTitle>
                <Shield className="w-4 h-4 text-emerald-400" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-white">
                {metrics.error_rate < 0.1 ? 'Excellent' : metrics.error_rate < 0.5 ? 'Good' : 'Fair'}
              </div>
              <div className="flex items-center mt-2">
                <Activity className="w-3 h-3 text-green-400 mr-1" />
                <span className="text-xs text-green-400">All systems operational</span>
              </div>
              <p className="text-xs text-gray-400 mt-1">
                Error rate: {metrics.error_rate.toFixed(2)}%
              </p>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* Detailed Monitoring */}
      <Tabs defaultValue="services" className="w-full">
        <TabsList className="bg-white/[0.02] border-white/5">
          <TabsTrigger value="services">Services</TabsTrigger>
          <TabsTrigger value="network">Network</TabsTrigger>
          <TabsTrigger value="storage">Storage</TabsTrigger>
          <TabsTrigger value="alerts">Alerts</TabsTrigger>
        </TabsList>

        <TabsContent value="services" className="mt-4">
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="h-5 w-5 text-blue-400" />
                Service Status
              </CardTitle>
              <CardDescription>
                Real-time status of all microservices
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {services.map((service, index) => (
                  <motion.div
                    key={service.name}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.1 }}
                    className="p-4 rounded-lg bg-white/[0.02] border border-white/5"
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-lg bg-white/[0.02]`}>
                          <Server className={`h-5 w-5 ${getStatusColor(service.status)}`} />
                        </div>
                        <div>
                          <h3 className="font-semibold text-white">{service.name}</h3>
                          <p className="text-sm text-gray-400">
                            Last check: {new Date(service.last_check).toLocaleTimeString()}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {getStatusBadge(service.status)}
                        <span className="text-sm text-gray-400">
                          {service.response_time}ms
                        </span>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-gray-400">CPU</span>
                          <span className="text-white">{service.metrics.cpu}%</span>
                        </div>
                        <Progress value={service.metrics.cpu} className="h-1" />
                      </div>
                      <div>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-gray-400">Memory</span>
                          <span className="text-white">{service.metrics.memory}%</span>
                        </div>
                        <Progress value={service.metrics.memory} className="h-1" />
                      </div>
                      <div>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-gray-400">Requests/s</span>
                          <span className="text-white">{service.metrics.requests_per_second}</span>
                        </div>
                        <Progress value={(service.metrics.requests_per_second / 1000) * 100} className="h-1" />
                      </div>
                    </div>
                    <div className="flex gap-2 mt-3">
                      {service.dependencies.map((dep) => (
                        <Badge key={dep} variant="outline" className="text-xs">
                          {dep}
                        </Badge>
                      ))}
                    </div>
                  </motion.div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="network" className="mt-4">
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Wifi className="h-5 w-5 text-green-400" />
                Network Traffic
              </CardTitle>
              <CardDescription>
                Real-time network performance and bandwidth usage
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <h3 className="text-lg font-semibold mb-4">Bandwidth Usage</h3>
                  <div className="space-y-4">
                    <div>
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-gray-400">Incoming</span>
                        <span className="text-white">{(metrics.network_in / 1000000).toFixed(2)} MB/s</span>
                      </div>
                      <Progress value={(metrics.network_in / 10000000) * 100} className="h-2" />
                    </div>
                    <div>
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-gray-400">Outgoing</span>
                        <span className="text-white">{(metrics.network_out / 1000000).toFixed(2)} MB/s</span>
                      </div>
                      <Progress value={(metrics.network_out / 10000000) * 100} className="h-2" />
                    </div>
                  </div>
                </div>
                <div>
                  <h3 className="text-lg font-semibold mb-4">Connection Status</h3>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between p-3 rounded bg-white/[0.02]">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 bg-green-400 rounded-full"></div>
                        <span className="text-sm">API Gateway</span>
                      </div>
                      <span className="text-sm text-green-400">Connected</span>
                    </div>
                    <div className="flex items-center justify-between p-3 rounded bg-white/[0.02]">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 bg-green-400 rounded-full"></div>
                        <span className="text-sm">Database</span>
                      </div>
                      <span className="text-sm text-green-400">Connected</span>
                    </div>
                    <div className="flex items-center justify-between p-3 rounded bg-white/[0.02]">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 bg-yellow-400 rounded-full"></div>
                        <span className="text-sm">External API</span>
                      </div>
                      <span className="text-sm text-yellow-400">High latency</span>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="storage" className="mt-4">
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <HardDrive className="h-5 w-5 text-purple-400" />
                Storage Systems
              </CardTitle>
              <CardDescription>
                Disk usage and storage performance metrics
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-gray-400">Primary Storage</span>
                    <span className="text-white">{metrics.disk_usage}% used</span>
                  </div>
                  <Progress value={metrics.disk_usage} className="h-2" />
                  <p className="text-xs text-gray-400 mt-1">450 GB of 1 TB used</p>
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-gray-400">Cache Storage</span>
                    <span className="text-white">32% used</span>
                  </div>
                  <Progress value={32} className="h-2" />
                  <p className="text-xs text-gray-400 mt-1">3.2 GB of 10 GB used</p>
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-gray-400">Backup Storage</span>
                    <span className="text-white">78% used</span>
                  </div>
                  <Progress value={78} className="h-2" />
                  <p className="text-xs text-gray-400 mt-1">780 GB of 1 TB used</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="alerts" className="mt-4">
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-yellow-400" />
                System Alerts
              </CardTitle>
              <CardDescription>
                Active alerts and system notifications
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {alerts.filter(alert => !alert.acknowledged).map((alert) => (
                  <motion.div
                    key={alert.id}
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex items-center justify-between p-3 rounded-lg bg-white/[0.02] border border-white/5"
                  >
                    <div className="flex items-center gap-3">
                      {getAlertIcon(alert.type)}
                      <div>
                        <p className="text-sm font-medium text-white">{alert.message}</p>
                        <p className="text-xs text-gray-400">
                          {new Date(alert.timestamp).toLocaleString()}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-xs">
                        {alert.severity}
                      </Badge>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => acknowledgeAlert(alert.id)}
                      >
                        Acknowledge
                      </Button>
                    </div>
                  </motion.div>
                ))}
                {alerts.filter(alert => !alert.acknowledged).length === 0 && (
                  <div className="text-center py-8 text-gray-400">
                    <Shield className="w-12 h-12 mx-auto mb-4 opacity-50" />
                    <p>No active alerts</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
