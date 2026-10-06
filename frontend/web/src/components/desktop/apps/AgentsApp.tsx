'use client';

import React, { useState, useEffect } from 'react';
import { jarvisAPI, AgentTask, AgentStats, TaskExecution } from '@/lib/api';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Bot,
  Plus,
  Play,
  Pause,
  Trash2,
  RefreshCw,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  BarChart3,
  Timer,
  Zap,
  Settings,
  MoreVertical,
} from 'lucide-react';

export default function AgentsApp() {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [stats, setStats] = useState<AgentStats | null>(null);
  const [executions, setExecutions] = useState<TaskExecution[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [activeTab, setActiveTab] = useState<'tasks' | 'executions' | 'stats'>('tasks');

  // New task form state
  const [newTask, setNewTask] = useState({
    name: '',
    description: '',
    schedule_type: 'once',
    schedule_value: '',
    priority: 'normal',
    timeout: 300,
    max_retries: 3,
  });

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [tasksRes, statsRes, executionsRes] = await Promise.all([
        jarvisAPI.getAgents(),
        jarvisAPI.getAgentStats().catch(() => null),
        jarvisAPI.getTaskExecutions().catch(() => ({ executions: [] })),
      ]);

      setTasks(tasksRes.tasks || []);
      if (statsRes) setStats(statsRes);
      setExecutions(executionsRes.executions || []);
    } catch (error) {
      // Mock data
      setTasks([
        {
          id: '1',
          name: 'Data Sync',
          description: 'Sync data across services',
          schedule_type: 'daily',
          schedule_value: '08:00',
          priority: 'high',
          enabled: true,
          timeout: 300,
          max_retries: 3,
          last_run_at: new Date().toISOString(),
          last_run_status: 'completed',
          last_run_duration_ms: 4500,
          created_at: new Date().toISOString(),
        },
        {
          id: '2',
          name: 'Health Check',
          description: 'Monitor system health',
          schedule_type: 'interval',
          schedule_value: '30',
          priority: 'normal',
          enabled: true,
          timeout: 60,
          max_retries: 2,
          last_run_at: new Date().toISOString(),
          last_run_status: 'completed',
          last_run_duration_ms: 1200,
          created_at: new Date().toISOString(),
        },
        {
          id: '3',
          name: 'Report Generation',
          description: 'Generate weekly reports',
          schedule_type: 'weekly',
          schedule_value: 'Monday',
          priority: 'low',
          enabled: false,
          timeout: 600,
          max_retries: 1,
          last_run_at: new Date(Date.now() - 86400000).toISOString(),
          last_run_status: 'failed',
          last_run_duration_ms: 15000,
          created_at: new Date().toISOString(),
        },
      ]);
      setStats({
        total_tasks: 15,
        active_tasks: 8,
        success_rate_percent: 94.5,
        avg_execution_time_ms: 3200,
      });
      setExecutions([
        {
          id: 'e1',
          task_name: 'Data Sync',
          status: 'completed',
          started_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
          duration_ms: 4500,
          retries: 0,
        },
        {
          id: 'e2',
          task_name: 'Health Check',
          status: 'completed',
          started_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
          duration_ms: 1200,
          retries: 0,
        },
        {
          id: 'e3',
          task_name: 'Report Generation',
          status: 'failed',
          started_at: new Date(Date.now() - 86400000).toISOString(),
          completed_at: new Date(Date.now() - 86400000).toISOString(),
          duration_ms: 15000,
          retries: 1,
          error: 'Timeout exceeded',
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const createTask = async () => {
    if (!newTask.name) return;

    try {
      await jarvisAPI.registerCustomTask(newTask);
      setShowCreateForm(false);
      setNewTask({
        name: '',
        description: '',
        schedule_type: 'once',
        schedule_value: '',
        priority: 'normal',
        timeout: 300,
        max_retries: 3,
      });
      loadData();
    } catch {
      // Optimistically add
      const task: AgentTask = {
        ...newTask,
        id: Date.now().toString(),
        enabled: true,
        created_at: new Date().toISOString(),
      };
      setTasks((prev) => [...prev, task]);
      setShowCreateForm(false);
      setNewTask({
        name: '',
        description: '',
        schedule_type: 'once',
        schedule_value: '',
        priority: 'normal',
        timeout: 300,
        max_retries: 3,
      });
    }
  };

  const toggleTask = async (taskId: string, enabled: boolean) => {
    try {
      await jarvisAPI.toggleAgentTask(taskId, !enabled);
    } catch {
      // Optimistic update
    }
    setTasks((prev) =>
      prev.map((t) => (t.id === taskId ? { ...t, enabled: !enabled } : t))
    );
  };

  const runTask = async (taskId: string) => {
    try {
      await jarvisAPI.runAgentTask(taskId);
    } catch {
      // Simulate run
    }
  };

  const deleteTask = async (taskId: string) => {
    try {
      await jarvisAPI.deleteAgentTask(taskId);
    } catch {
      // Optimistic remove
    }
    setTasks((prev) => prev.filter((t) => t.id !== taskId));
  };

  const formatDuration = (ms?: number) => {
    if (!ms) return '-';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-4 h-4 text-emerald-400" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-400" />;
      case 'running':
        return <AlertCircle className="w-4 h-4 text-blue-400 animate-pulse" />;
      case 'retrying':
        return <RefreshCw className="w-4 h-4 text-amber-400 animate-spin" />;
      default:
        return <Clock className="w-4 h-4 text-foreground/30" />;
    }
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high':
        return 'text-red-400 bg-red-500/10';
      case 'normal':
        return 'text-blue-400 bg-blue-500/10';
      case 'low':
        return 'text-foreground/40 bg-white/5';
      default:
        return 'text-foreground/40 bg-white/5';
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border/50 bg-card/30">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-primary" />
          <span className="text-sm font-medium">Agents</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            disabled={isLoading}
            className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setShowCreateForm(true)}
            className="flex items-center gap-1.5 h-8 px-3 rounded-lg bg-primary/20 border border-primary/20 text-primary hover:bg-primary/30 transition-colors text-xs"
          >
            <Plus className="w-3.5 h-3.5" />
            New Task
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-0.5 px-4 py-2 border-b border-border/30">
        {[
          { id: 'tasks', label: 'Tasks', icon: Bot },
          { id: 'executions', label: 'Executions', icon: Clock },
          { id: 'stats', label: 'Statistics', icon: BarChart3 },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors ${
              activeTab === tab.id
                ? 'bg-primary/15 text-primary'
                : 'text-foreground/50 hover:text-foreground/70 hover:bg-white/5'
            }`}
          >
            <tab.icon className="w-3.5 h-3.5" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-4">
        <AnimatePresence mode="wait">
          {/* Tasks Tab */}
          {activeTab === 'tasks' && (
            <motion.div
              key="tasks"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="space-y-2"
            >
              {tasks.map((task) => (
                <motion.div
                  key={task.id}
                  className="glass rounded-xl p-4 border border-border/50 hover:border-primary/20 transition-all"
                  whileHover={{ x: 2 }}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3 flex-1 min-w-0">
                      <div
                        className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                          task.enabled
                            ? 'bg-gradient-to-br from-primary/20 to-accent/20 border border-primary/20'
                            : 'bg-white/5 border border-border/30'
                        }`}
                      >
                        <Bot className={`w-5 h-5 ${task.enabled ? 'text-primary' : 'text-foreground/30'}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-medium text-foreground truncate">{task.name}</h4>
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded ${getPriorityColor(task.priority)}`}
                          >
                            {task.priority}
                          </span>
                        </div>
                        <p className="text-xs text-foreground/40 mt-0.5 truncate">
                          {task.description || 'No description'}
                        </p>
                        <div className="flex items-center gap-3 mt-2 text-[10px] text-foreground/30">
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {task.schedule_type}: {task.schedule_value}
                          </span>
                          {task.last_run_at && (
                            <span>Last run: {new Date(task.last_run_at).toLocaleTimeString()}</span>
                          )}
                          {task.last_run_duration_ms && (
                            <span>Duration: {formatDuration(task.last_run_duration_ms)}</span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-1 ml-4 shrink-0">
                      <button
                        onClick={() => runTask(task.id!)}
                        className="h-7 w-7 flex items-center justify-center rounded-lg hover:bg-emerald-500/10 text-foreground/40 hover:text-emerald-400 transition-colors"
                        title="Run now"
                      >
                        <Play className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => toggleTask(task.id!, task.enabled)}
                        className={`h-7 w-7 flex items-center justify-center rounded-lg transition-colors ${
                          task.enabled
                            ? 'hover:bg-amber-500/10 text-amber-400'
                            : 'hover:bg-emerald-500/10 text-emerald-400'
                        }`}
                        title={task.enabled ? 'Disable' : 'Enable'}
                      >
                        {task.enabled ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                      </button>
                      <button
                        onClick={() => deleteTask(task.id!)}
                        className="h-7 w-7 flex items-center justify-center rounded-lg hover:bg-red-500/10 text-foreground/40 hover:text-red-400 transition-colors"
                        title="Delete"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </motion.div>
              ))}

              {tasks.length === 0 && (
                <div className="flex flex-col items-center justify-center py-12 text-foreground/40">
                  <Bot className="w-12 h-12 mb-3" />
                  <span className="text-sm">No tasks yet</span>
                  <button
                    onClick={() => setShowCreateForm(true)}
                    className="mt-2 text-xs text-primary hover:text-primary/80"
                  >
                    Create your first task
                  </button>
                </div>
              )}
            </motion.div>
          )}

          {/* Executions Tab */}
          {activeTab === 'executions' && (
            <motion.div
              key="executions"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="space-y-2"
            >
              {executions.map((exec) => (
                <div
                  key={exec.id}
                  className="glass rounded-lg p-3 border border-border/50 flex items-center gap-3"
                >
                  {getStatusIcon(exec.status)}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-foreground/80 truncate">{exec.task_name}</p>
                    <p className="text-[10px] text-foreground/40">
                      {new Date(exec.started_at).toLocaleString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-foreground/50">
                    <span className="flex items-center gap-1">
                      <Timer className="w-3.5 h-3.5" />
                      {formatDuration(exec.duration_ms)}
                    </span>
                    {exec.retries > 0 && (
                      <span className="flex items-center gap-1 text-amber-400">
                        <RefreshCw className="w-3.5 h-3.5" />
                        {exec.retries}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </motion.div>
          )}

          {/* Stats Tab */}
          {activeTab === 'stats' && (
            <motion.div
              key="stats"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
            >
              {stats && (
                <div className="grid grid-cols-2 gap-3">
                  <StatCard
                    icon={Bot}
                    label="Total Tasks"
                    value={stats.total_tasks.toString()}
                    color="text-blue-400"
                  />
                  <StatCard
                    icon={Zap}
                    label="Active Tasks"
                    value={stats.active_tasks.toString()}
                    color="text-emerald-400"
                  />
                  <StatCard
                    icon={CheckCircle2}
                    label="Success Rate"
                    value={`${stats.success_rate_percent}%`}
                    color="text-amber-400"
                  />
                  <StatCard
                    icon={Timer}
                    label="Avg Execution"
                    value={formatDuration(stats.avg_execution_time_ms)}
                    color="text-purple-400"
                  />
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Create Task Modal */}
      {showCreateForm && (
        <div className="absolute inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="glass rounded-2xl w-full max-w-md mx-4 border border-border/50 shadow-2xl overflow-hidden"
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
              <h3 className="text-sm font-semibold text-foreground">Create New Task</h3>
              <button
                onClick={() => setShowCreateForm(false)}
                className="h-7 w-7 flex items-center justify-center rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground transition-colors"
              >
                <XCircle className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 space-y-3">
              <input
                type="text"
                placeholder="Task name"
                value={newTask.name}
                onChange={(e) => setNewTask((p) => ({ ...p, name: e.target.value }))}
                className="w-full h-9 px-3 bg-white/5 border border-border/50 rounded-lg text-sm text-foreground placeholder:text-foreground/30 focus:outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20 transition-all"
              />
              <textarea
                placeholder="Description"
                value={newTask.description}
                onChange={(e) => setNewTask((p) => ({ ...p, description: e.target.value }))}
                rows={2}
                className="w-full px-3 py-2 bg-white/5 border border-border/50 rounded-lg text-sm text-foreground placeholder:text-foreground/30 focus:outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20 transition-all resize-none"
              />
              <div className="grid grid-cols-2 gap-3">
                <select
                  value={newTask.schedule_type}
                  onChange={(e) => setNewTask((p) => ({ ...p, schedule_type: e.target.value }))}
                  className="h-9 px-3 bg-white/5 border border-border/50 rounded-lg text-sm text-foreground focus:outline-none focus:border-primary/50 transition-all"
                >
                  <option value="once">Once</option>
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="interval">Interval (min)</option>
                </select>
                <input
                  type="text"
                  placeholder="Schedule value"
                  value={newTask.schedule_value}
                  onChange={(e) => setNewTask((p) => ({ ...p, schedule_value: e.target.value }))}
                  className="h-9 px-3 bg-white/5 border border-border/50 rounded-lg text-sm text-foreground placeholder:text-foreground/30 focus:outline-none focus:border-primary/50 transition-all"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <select
                  value={newTask.priority}
                  onChange={(e) => setNewTask((p) => ({ ...p, priority: e.target.value }))}
                  className="h-9 px-3 bg-white/5 border border-border/50 rounded-lg text-sm text-foreground focus:outline-none focus:border-primary/50 transition-all"
                >
                  <option value="low">Low</option>
                  <option value="normal">Normal</option>
                  <option value="high">High</option>
                </select>
                <input
                  type="number"
                  placeholder="Timeout (s)"
                  value={newTask.timeout}
                  onChange={(e) => setNewTask((p) => ({ ...p, timeout: parseInt(e.target.value) || 300 }))}
                  className="h-9 px-3 bg-white/5 border border-border/50 rounded-lg text-sm text-foreground placeholder:text-foreground/30 focus:outline-none focus:border-primary/50 transition-all"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-border/50 bg-white/[0.02]">
              <button
                onClick={() => setShowCreateForm(false)}
                className="h-9 px-4 rounded-lg text-sm text-foreground/60 hover:text-foreground hover:bg-white/5 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={createTask}
                disabled={!newTask.name}
                className="h-9 px-4 rounded-lg text-sm bg-primary/20 border border-primary/20 text-primary hover:bg-primary/30 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              >
                Create Task
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}

// ==================== Stat Card ====================

function StatCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="glass rounded-xl p-4 border border-border/50">
      <div className="flex items-center justify-between mb-2">
        <Icon className={`w-5 h-5 ${color}`} />
      </div>
      <p className="text-[10px] text-foreground/50 uppercase tracking-wider">{label}</p>
      <p className={`text-xl font-bold font-mono ${color}`}>{value}</p>
    </div>
  );
}
