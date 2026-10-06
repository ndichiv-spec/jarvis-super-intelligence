'use client';

import { useEffect } from 'react';
import { motion } from 'framer-motion';
import { Brain, Activity, Bot, Library, Volume2, Cpu, Zap } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useMonitoringStore } from '@/features/monitoring/store';
import { useAgentsStore } from '@/features/agents/store';

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.08 },
  },
};

const item = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0 },
};

export function DashboardWidgets() {
  const { metrics, health, loadHealth, loadMetrics } = useMonitoringStore();
  const { stats, loadStats } = useAgentsStore();

  useEffect(() => {
    loadHealth();
    loadMetrics();
    loadStats();
  }, [loadHealth, loadMetrics, loadStats]);

  const widgets = [
    {
      title: 'System Health',
      value: health?.status || 'Unknown',
      icon: Activity,
      color: health?.status === 'healthy' ? 'text-emerald-400' : 'text-amber-400',
      bg: health?.status === 'healthy' ? 'bg-emerald-500/10' : 'bg-amber-500/10',
      detail: `v${health?.version || '3.0.0'}`,
    },
    {
      title: 'CPU Usage',
      value: metrics?.system?.cpu_percent != null ? `${metrics.system.cpu_percent.toFixed(1)}%` : '--',
      icon: Cpu,
      color: (metrics?.system?.cpu_percent || 0) > 80 ? 'text-red-400' : 'text-cyan-400',
      bg: 'bg-cyan-500/10',
      detail: `${metrics?.system?.process_count || 0} processes`,
    },
    {
      title: 'Memory',
      value: metrics?.system?.memory_percent != null ? `${metrics.system.memory_percent.toFixed(1)}%` : '--',
      icon: Brain,
      color: (metrics?.system?.memory_percent || 0) > 80 ? 'text-red-400' : 'text-blue-400',
      bg: 'bg-blue-500/10',
      detail: metrics?.system?.memory_available_mb ? `${(metrics.system.memory_available_mb / 1024).toFixed(1)} GB free` : '',
    },
    {
      title: 'Agent Tasks',
      value: stats?.total_tasks?.toString() || '0',
      icon: Bot,
      color: 'text-purple-400',
      bg: 'bg-purple-500/10',
      detail: `${stats?.active_tasks || 0} active · ${stats?.success_rate_percent || 0}% success`,
    },
  ];

  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="show"
      className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
    >
      {widgets.map((widget) => (
        <motion.div key={widget.title} variants={item}>
          <Card className="border-white/10 bg-white/[0.03] overflow-hidden group hover:border-white/20 transition-all">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${widget.bg}`}>
                  <widget.icon className={`h-5 w-5 ${widget.color}`} />
                </div>
                <Zap className="h-4 w-4 text-muted-foreground/20 group-hover:text-muted-foreground/40 transition-colors" />
              </div>
              <div className="mt-3">
                <p className="text-2xl font-bold text-foreground">{widget.value}</p>
                <p className="text-xs text-muted-foreground/50">{widget.title}</p>
                {widget.detail && (
                  <p className="mt-1 text-[10px] text-muted-foreground/30">{widget.detail}</p>
                )}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      ))}
    </motion.div>
  );
}
