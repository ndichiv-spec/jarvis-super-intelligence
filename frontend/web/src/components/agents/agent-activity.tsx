'use client';

import { useEffect } from 'react';
import { motion } from 'framer-motion';
import { Bot, Play, Square, Clock, CheckCircle, XCircle, Loader2, Activity } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useAgentsStore } from '@/features/agents/store';

export function AgentActivity() {
  const {
    tasks,
    executions,
    stats,
    schedulerStatus,
    loadTasks,
    loadExecutions,
    loadStats,
    loadSchedulerStatus,
    toggleTask,
    runTask,
    toggleScheduler,
  } = useAgentsStore();

  useEffect(() => {
    loadTasks();
    loadExecutions();
    loadStats();
    loadSchedulerStatus();
  }, [loadTasks, loadExecutions, loadStats, loadSchedulerStatus]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-3.5 w-3.5 text-emerald-400" />;
      case 'failed':
        return <XCircle className="h-3.5 w-3.5 text-red-400" />;
      case 'running':
        return <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-400" />;
      default:
        return <Clock className="h-3.5 w-3.5 text-muted-foreground/40" />;
    }
  };

  return (
    <div className="space-y-4">
      {/* Stats Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="border-white/10 bg-white/[0.03]">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10">
                <Bot className="h-5 w-5 text-blue-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{stats?.total_tasks || 0}</p>
                <p className="text-xs text-muted-foreground/50">Total Tasks</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-white/10 bg-white/[0.03]">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10">
                <Activity className="h-5 w-5 text-emerald-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{stats?.active_tasks || 0}</p>
                <p className="text-xs text-muted-foreground/50">Active Tasks</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-white/10 bg-white/[0.03]">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/10">
                <CheckCircle className="h-5 w-5 text-cyan-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{stats?.success_rate_percent || 0}%</p>
                <p className="text-xs text-muted-foreground/50">Success Rate</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-white/10 bg-white/[0.03]">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-500/10">
                <Clock className="h-5 w-5 text-purple-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">
                  {stats?.avg_execution_time_ms ? `${(stats.avg_execution_time_ms / 1000).toFixed(1)}s` : '0s'}
                </p>
                <p className="text-xs text-muted-foreground/50">Avg Time</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Scheduler Toggle */}
      <div className="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.02] p-3">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-cyan-400" />
          <span className="text-sm font-medium">Scheduler</span>
          <Badge className={schedulerStatus?.running ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}>
            {schedulerStatus?.running ? 'Running' : 'Stopped'}
          </Badge>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="border-white/10"
          onClick={() => toggleScheduler(!schedulerStatus?.running)}
        >
          {schedulerStatus?.running ? <Square className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}
          {schedulerStatus?.running ? 'Stop' : 'Start'}
        </Button>
      </div>

      {/* Recent Executions */}
      <Card className="border-white/10 bg-white/[0.03]">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <Activity className="h-4 w-4 text-cyan-400" />
            Recent Executions
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[200px]">
            <div className="space-y-2">
              {executions.map((execution) => (
                <motion.div
                  key={execution.id}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-center justify-between rounded-lg border border-white/5 bg-white/[0.01] px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    {getStatusIcon(execution.status)}
                    <div>
                      <p className="text-xs font-medium text-foreground/80">{execution.task_name}</p>
                      <p className="text-[10px] text-muted-foreground/40">
                        {new Date(execution.started_at).toLocaleString()} · {(execution.duration_ms / 1000).toFixed(1)}s
                      </p>
                    </div>
                  </div>
                  <span className="text-[10px] text-muted-foreground/40">
                    {execution.retries > 0 ? `${execution.retries} retries` : ''}
                  </span>
                </motion.div>
              ))}
              {executions.length === 0 && (
                <p className="text-center text-sm text-muted-foreground/40 py-8">No recent executions</p>
              )}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
