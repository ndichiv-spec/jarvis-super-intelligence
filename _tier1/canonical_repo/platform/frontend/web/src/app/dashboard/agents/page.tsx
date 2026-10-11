"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bot,
  Plus,
  Play,
  Trash2,
  Loader2,
  Clock,
  AlertCircle,
  CheckCircle2,
  RotateCcw,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Power,
  PowerOff,
  Activity,
  Percent,
  Timer,
  ListTodo,
} from "lucide-react";
import { format, formatDistanceToNow } from "date-fns";
import { toast } from "sonner";

import {
  jarvisAPI,
  type AgentTask,
  type TaskExecution,
  type AgentStats,
  type SchedulerStatus,
  type ServiceTailoringStatus,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

// ─── Types ───────────────────────────────────────────────────────────────────

type SortField = "task_name" | "started_at" | "duration_ms" | "retries";
type SortDirection = "asc" | "desc";

interface TaskFormData {
  name: string;
  description: string;
  schedule_type: string;
  schedule_value: string;
  priority: string;
  timeout: number;
  max_retries: number;
}

// ─── Constants ───────────────────────────────────────────────────────────────

const SCHEDULE_TYPES = [
  { value: "interval", label: "Interval" },
  { value: "cron", label: "Cron" },
  { value: "once", label: "Once" },
  { value: "event-driven", label: "Event-Driven" },
];

const PRIORITY_OPTIONS = [
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "normal", label: "Normal" },
  { value: "low", label: "Low" },
];

const INITIAL_FORM: TaskFormData = {
  name: "",
  description: "",
  schedule_type: "interval",
  schedule_value: "",
  priority: "normal",
  timeout: 300,
  max_retries: 3,
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getPriorityColors(priority: string) {
  switch (priority) {
    case "critical":
      return "bg-red-500/15 text-red-400 border-red-500/30";
    case "high":
      return "bg-orange-500/15 text-orange-400 border-orange-500/30";
    case "normal":
      return "bg-blue-500/15 text-blue-400 border-blue-500/30";
    case "low":
      return "bg-gray-500/15 text-gray-400 border-gray-500/30";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}

function getScheduleTypeBadgeColor(type: string) {
  switch (type) {
    case "interval":
      return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
    case "cron":
      return "bg-violet-500/15 text-violet-400 border-violet-500/30";
    case "once":
      return "bg-cyan-500/15 text-cyan-400 border-cyan-500/30";
    case "event-driven":
      return "bg-amber-500/15 text-amber-400 border-amber-500/30";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}

function getStatusBadge(status: string) {
  switch (status) {
    case "completed":
      return {
        className: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
        icon: CheckCircle2,
      };
    case "failed":
      return {
        className: "bg-red-500/15 text-red-400 border-red-500/30",
        icon: AlertCircle,
      };
    case "retrying":
      return {
        className: "bg-amber-500/15 text-amber-400 border-amber-500/30",
        icon: RotateCcw,
      };
    case "running":
      return {
        className: "bg-blue-500/15 text-blue-400 border-blue-500/30",
        icon: Loader2,
      };
    default:
      return {
        className: "bg-muted text-muted-foreground border-border",
        icon: Clock,
      };
  }
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSec = Math.floor(seconds % 60);
  return `${minutes}m ${remainingSec}s`;
}

function formatScheduleDisplay(type: string, value: string): string {
  switch (type) {
    case "interval":
      return `Every ${value}`;
    case "cron":
      return `Cron: ${value}`;
    case "once":
      return `Once: ${value}`;
    case "event-driven":
      return `On: ${value}`;
    default:
      return value;
  }
}

// ─── Stat Card ───────────────────────────────────────────────────────────────

function StatCard({
  title,
  value,
  icon: Icon,
  description,
  progressValue,
}: {
  title: string;
  value: string | number;
  icon: React.ElementType;
  description?: string;
  progressValue?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <Card className="bg-card/50 border-border backdrop-blur-sm">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            {title}
          </CardTitle>
          <Icon className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{value}</div>
          {description && (
            <p className="text-xs text-muted-foreground mt-1">{description}</p>
          )}
          {progressValue !== undefined && (
            <Progress value={progressValue} className="mt-2 h-1" />
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}

// ─── Task Card ───────────────────────────────────────────────────────────────

function TaskCard({
  task,
  onToggle,
  onRun,
  onDelete,
}: {
  task: AgentTask;
  onToggle: (id: string, enabled: boolean) => void;
  onRun: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const [isRunning, setIsRunning] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const handleRun = async () => {
    setIsRunning(true);
    try {
      await onRun(task.id!);
      toast.success(`Task "${task.name}" triggered`);
    } catch (error: any) {
      toast.error(`Failed to run task: ${error.message}`);
    } finally {
      setIsRunning(false);
    }
  };

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await onDelete(task.id!);
      toast.success(`Task "${task.name}" deleted`);
    } catch (error: any) {
      toast.error(`Failed to delete task: ${error.message}`);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
    >
      <Card
        className={`bg-card/50 border-border backdrop-blur-sm transition-all duration-200 hover:border-primary/30 ${
          !task.enabled ? "opacity-60" : ""
        }`}
      >
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <Bot className="h-5 w-5 text-primary flex-shrink-0" />
              <CardTitle className="text-sm font-semibold truncate">
                {task.name}
              </CardTitle>
            </div>
            <Switch
              checked={task.enabled}
              onCheckedChange={(checked) => onToggle(task.id!, checked)}
              aria-label={`Toggle ${task.name}`}
            />
          </div>
          <div className="flex flex-wrap gap-1.5 mt-1">
            <Badge
              variant="outline"
              className={`text-[10px] ${getScheduleTypeBadgeColor(task.schedule_type)}`}
            >
              {SCHEDULE_TYPES.find((s) => s.value === task.schedule_type)?.label || task.schedule_type}
            </Badge>
            <Badge
              variant="outline"
              className={`text-[10px] ${getPriorityColors(task.priority)}`}
            >
              {task.priority}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="pt-0 space-y-3">
          {/* Schedule display */}
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Clock className="h-3.5 w-3.5" />
            <span>
              {formatScheduleDisplay(task.schedule_type, task.schedule_value)}
            </span>
          </div>

          {/* Last execution */}
          {task.last_run_at ? (
            <div className="flex items-center gap-1.5 text-xs">
              <span className="text-muted-foreground">Last run:</span>
              <span className="text-foreground font-medium">
                {formatDistanceToNow(new Date(task.last_run_at), { addSuffix: true })}
              </span>
              {task.last_run_status && (
                <Badge
                  variant="outline"
                  className={`text-[10px] ml-auto ${getStatusBadge(task.last_run_status).className}`}
                >
                  {task.last_run_status}
                </Badge>
              )}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">Never executed</p>
          )}

          {/* Config row */}
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span>Timeout: {task.timeout}s</span>
            <span>Retries: {task.max_retries}</span>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1">
            <Button
              variant="outline"
              size="sm"
              className="flex-1 text-xs h-8"
              onClick={handleRun}
              disabled={isRunning || !task.enabled}
            >
              {isRunning ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
              {isRunning ? "Running..." : "Run Now"}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-destructive"
              onClick={handleDelete}
              disabled={isDeleting}
            >
              {isDeleting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Trash2 className="h-3.5 w-3.5" />
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

// ─── Execution History Table ─────────────────────────────────────────────────

function ExecutionHistoryTable({
  executions,
}: {
  executions: TaskExecution[];
}) {
  const [sortField, setSortField] = useState<SortField>("started_at");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  };

  const sortedExecutions = useMemo(() => {
    return [...executions].sort((a, b) => {
      let comparison = 0;
      switch (sortField) {
        case "task_name":
          comparison = a.task_name.localeCompare(b.task_name);
          break;
        case "started_at":
          comparison = new Date(a.started_at).getTime() - new Date(b.started_at).getTime();
          break;
        case "duration_ms":
          comparison = a.duration_ms - b.duration_ms;
          break;
        case "retries":
          comparison = a.retries - b.retries;
          break;
      }
      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [executions, sortField, sortDirection]);

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="h-3.5 w-3.5 ml-1 inline" />;
    if (sortDirection === "asc") return <ArrowUp className="h-3.5 w-3.5 ml-1 inline" />;
    return <ArrowDown className="h-3.5 w-3.5 ml-1 inline" />;
  };

  if (executions.length === 0) {
    return (
      <Card className="bg-card/50 border-border backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="text-lg">Execution History</CardTitle>
          <CardDescription>No executions recorded yet</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className="bg-card/50 border-border backdrop-blur-sm">
      <CardHeader>
        <CardTitle className="text-lg">Execution History</CardTitle>
        <CardDescription>
          Recent task executions (last {executions.length} entries)
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead
                className="cursor-pointer select-none hover:text-foreground"
                onClick={() => handleSort("task_name")}
              >
                Task Name
                <SortIcon field="task_name" />
              </TableHead>
              <TableHead>Status</TableHead>
              <TableHead
                className="cursor-pointer select-none hover:text-foreground"
                onClick={() => handleSort("started_at")}
              >
                Started At
                <SortIcon field="started_at" />
              </TableHead>
              <TableHead
                className="cursor-pointer select-none hover:text-foreground"
                onClick={() => handleSort("duration_ms")}
              >
                Duration
                <SortIcon field="duration_ms" />
              </TableHead>
              <TableHead
                className="cursor-pointer select-none hover:text-foreground"
                onClick={() => handleSort("retries")}
              >
                Retries
                <SortIcon field="retries" />
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedExecutions.map((exec) => {
              const statusBadge = getStatusBadge(exec.status);
              const StatusIcon = statusBadge.icon;
              return (
                <TableRow key={exec.id}>
                  <TableCell className="font-medium">{exec.task_name}</TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={`text-xs gap-1 ${statusBadge.className}`}
                    >
                      <StatusIcon
                        className={`h-3 w-3 ${exec.status === "running" ? "animate-spin" : ""}`}
                      />
                      {exec.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {format(new Date(exec.started_at), "MMM d, h:mm:ss a")}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDuration(exec.duration_ms)}
                  </TableCell>
                  <TableCell>
                    {exec.retries > 0 ? (
                      <Badge variant="outline" className="text-xs bg-amber-500/10 text-amber-400 border-amber-500/30">
                        {exec.retries}
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground text-xs">0</span>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// ─── Create Task Dialog ──────────────────────────────────────────────────────

function CreateTaskDialog({
  open,
  onOpenChange,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (task: TaskFormData) => Promise<void>;
}) {
  const [form, setForm] = useState<TaskFormData>(INITIAL_FORM);
  const [errors, setErrors] = useState<Partial<Record<keyof TaskFormData, string>>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const validate = (): boolean => {
    const newErrors: Partial<Record<keyof TaskFormData, string>> = {};

    if (!form.name.trim()) {
      newErrors.name = "Task name is required";
    } else if (form.name.length < 3) {
      newErrors.name = "Task name must be at least 3 characters";
    }

    if (!form.schedule_value.trim()) {
      newErrors.schedule_value = "Schedule value is required";
    }

    if (form.timeout < 1) {
      newErrors.timeout = "Timeout must be at least 1 second";
    } else if (form.timeout > 3600) {
      newErrors.timeout = "Timeout cannot exceed 3600 seconds";
    }

    if (form.max_retries < 0) {
      newErrors.max_retries = "Max retries cannot be negative";
    } else if (form.max_retries > 10) {
      newErrors.max_retries = "Max retries cannot exceed 10";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setIsSubmitting(true);
    try {
      await onSubmit(form);
      setForm(INITIAL_FORM);
      setErrors({});
      onOpenChange(false);
      toast.success(`Task "${form.name}" created successfully`);
    } catch (error: any) {
      toast.error(`Failed to create task: ${error.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const updateField = <K extends keyof TaskFormData>(
    field: K,
    value: TaskFormData[K]
  ) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    if (errors[field]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Create Autonomous Task</DialogTitle>
          <DialogDescription>
            Configure a new scheduled task for the autonomous agent system.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Name */}
          <div className="space-y-2">
            <Label htmlFor="task-name">
              Task Name <span className="text-red-400">*</span>
            </Label>
            <Input
              id="task-name"
              placeholder="e.g., System Health Check"
              value={form.name}
              onChange={(e) => updateField("name", e.target.value)}
              className={errors.name ? "border-red-500" : ""}
            />
            {errors.name && (
              <p className="text-xs text-red-400 flex items-center gap-1">
                <AlertCircle className="h-3 w-3" />
                {errors.name}
              </p>
            )}
          </div>

          {/* Description */}
          <div className="space-y-2">
            <Label htmlFor="task-desc">Description</Label>
            <Textarea
              id="task-desc"
              placeholder="Describe what this task does..."
              value={form.description}
              onChange={(e) => updateField("description", e.target.value)}
              rows={2}
            />
          </div>

          {/* Schedule Type & Value */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="schedule-type">Schedule Type</Label>
              <Select
                value={form.schedule_type}
                onValueChange={(v) => updateField("schedule_type", v)}
              >
                <SelectTrigger id="schedule-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SCHEDULE_TYPES.map((st) => (
                    <SelectItem key={st.value} value={st.value}>
                      {st.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="schedule-value">
                Schedule Value <span className="text-red-400">*</span>
              </Label>
              <Input
                id="schedule-value"
                placeholder={
                  form.schedule_type === "interval"
                    ? "5 minutes"
                    : form.schedule_type === "cron"
                    ? "0 */6 * * *"
                    : "2024-12-31 00:00"
                }
                value={form.schedule_value}
                onChange={(e) => updateField("schedule_value", e.target.value)}
                className={errors.schedule_value ? "border-red-500" : ""}
              />
              {errors.schedule_value && (
                <p className="text-xs text-red-400 flex items-center gap-1">
                  <AlertCircle className="h-3 w-3" />
                  {errors.schedule_value}
                </p>
              )}
            </div>
          </div>

          {/* Priority */}
          <div className="space-y-2">
            <Label htmlFor="priority">Priority</Label>
            <Select
              value={form.priority}
              onValueChange={(v) => updateField("priority", v)}
            >
              <SelectTrigger id="priority">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PRIORITY_OPTIONS.map((po) => (
                  <SelectItem key={po.value} value={po.value}>
                    {po.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Timeout & Max Retries */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="timeout">Timeout (seconds)</Label>
              <Input
                id="timeout"
                type="number"
                min={1}
                max={3600}
                value={form.timeout}
                onChange={(e) => updateField("timeout", parseInt(e.target.value) || 0)}
                className={errors.timeout ? "border-red-500" : ""}
              />
              {errors.timeout && (
                <p className="text-xs text-red-400 flex items-center gap-1">
                  <AlertCircle className="h-3 w-3" />
                  {errors.timeout}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="max-retries">Max Retries</Label>
              <Input
                id="max-retries"
                type="number"
                min={0}
                max={10}
                value={form.max_retries}
                onChange={(e) => updateField("max_retries", parseInt(e.target.value) || 0)}
                className={errors.max_retries ? "border-red-500" : ""}
              />
              {errors.max_retries && (
                <p className="text-xs text-red-400 flex items-center gap-1">
                  <AlertCircle className="h-3 w-3" />
                  {errors.max_retries}
                </p>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-1" />
                  Creating...
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4 mr-1" />
                  Create Task
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function AgentsPage() {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [executions, setExecutions] = useState<TaskExecution[]>([]);
  const [stats, setStats] = useState<AgentStats>({
    total_tasks: 0,
    active_tasks: 0,
    success_rate_percent: 0,
    avg_execution_time_ms: 0,
  });
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus>({
    running: false,
    total_scheduled: 0,
  });
  const [serviceTailoring, setServiceTailoring] = useState<ServiceTailoringStatus>({
    success: true,
    changed: false,
    sync_count: 0,
    changes_detected: 0,
    current_profile: {
      configured_service_count: 0,
      active_capabilities: [],
      configured_services: {},
    },
  });
  const [loading, setLoading] = useState(true);
  const [dataLoadError, setDataLoadError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  // ── Fetch all data ──────────────────────────────────────────────────────

  const fetchData = useCallback(async () => {
    try {
      const [agentsRes, statsRes, schedulerRes, executionsRes, tailoringRes] =
        await Promise.allSettled([
          jarvisAPI.getAgents(),
          jarvisAPI.getAgentStats(),
          jarvisAPI.getSchedulerStatus(),
          jarvisAPI.getTaskExecutions(20),
          jarvisAPI.getServiceTailoringStatus(),
        ]);
      const failures: string[] = [];

      if (agentsRes.status === "fulfilled") {
        setTasks(agentsRes.value.tasks || []);
      } else {
        setTasks([]);
        failures.push("scheduled tasks");
      }

      if (statsRes.status === "fulfilled") {
        setStats(statsRes.value);
      } else {
        failures.push("agent statistics");
      }

      if (schedulerRes.status === "fulfilled") {
        setSchedulerStatus(schedulerRes.value);
      } else {
        failures.push("scheduler status");
      }

      if (executionsRes.status === "fulfilled") {
        setExecutions(executionsRes.value.executions || []);
      } else {
        failures.push("execution history");
      }

      if (tailoringRes.status === "fulfilled") {
        setServiceTailoring(tailoringRes.value);
      } else {
        failures.push("service tailoring status");
      }
      setDataLoadError(
        failures.length
          ? `Could not load ${failures.join(", ")}. Displayed runtime data may be incomplete.`
          : null
      );
    } catch (error) {
      console.error("Failed to fetch agents data:", error);
      setDataLoadError("Agent runtime data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // ── Handlers ────────────────────────────────────────────────────────────

  const handleCreateTask = async (formData: TaskFormData) => {
    await jarvisAPI.registerCustomTask({
      name: formData.name,
      description: formData.description,
      schedule_type: formData.schedule_type,
      schedule_value: formData.schedule_value,
      priority: formData.priority,
      timeout: formData.timeout,
      max_retries: formData.max_retries,
    });
    await fetchData();
  };

  const handleToggleTask = async (taskId: string, enabled: boolean) => {
    try {
      await jarvisAPI.toggleAgentTask(taskId, enabled);
      setTasks((prev) =>
        prev.map((t) => (t.id === taskId ? { ...t, enabled } : t))
      );
      toast.success(`Task ${enabled ? "enabled" : "disabled"}`);
    } catch (error: any) {
      toast.error(`Failed to toggle task: ${error.message}`);
    }
  };

  const handleRunTask = async (taskId: string) => {
    await jarvisAPI.runAgentTask(taskId);
    await fetchData();
  };

  const handleDeleteTask = async (taskId: string) => {
    await jarvisAPI.deleteAgentTask(taskId);
    setTasks((prev) => prev.filter((t) => t.id !== taskId));
    await fetchData();
  };

  const handleToggleScheduler = async () => {
    try {
      const newRunning = !schedulerStatus.running;
      await jarvisAPI.toggleScheduler(newRunning);
      setSchedulerStatus((prev) => ({ ...prev, running: newRunning }));
      toast.success(`Scheduler ${newRunning ? "started" : "stopped"}`);
    } catch (error: any) {
      toast.error(`Failed to toggle scheduler: ${error.message}`);
    }
  };

  // ── Loading state ───────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Loading agents...</p>
        </div>
      </div>
    );
  }

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="h-full overflow-auto p-4 md:p-6 lg:p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        {/* ── Header ──────────────────────────────────────────────────── */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              Autonomous Agents
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Manage scheduled tasks and autonomous workflows
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Scheduler toggle */}
            <div className="flex items-center gap-2 rounded-lg border border-border bg-card/50 px-3 py-2 backdrop-blur-sm">
              {schedulerStatus.running ? (
                <Power className="h-4 w-4 text-emerald-400" />
              ) : (
                <PowerOff className="h-4 w-4 text-muted-foreground" />
              )}
              <span className="text-xs font-medium">
                Scheduler {schedulerStatus.running ? "Running" : "Stopped"}
              </span>
              <span
                className={`relative flex h-2 w-2 rounded-full ${
                  schedulerStatus.running ? "bg-emerald-500" : "bg-muted-foreground/40"
                }`}
              >
                {schedulerStatus.running && (
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                )}
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={handleToggleScheduler}
              >
                {schedulerStatus.running ? "Stop" : "Start"}
              </Button>
            </div>

            {dataLoadError && (
              <p
                role="alert"
                className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive"
              >
                {dataLoadError}
              </p>
            )}

            <Button onClick={() => setDialogOpen(true)} className="gap-1.5">
              <Plus className="h-4 w-4" />
              Create Task
            </Button>
          </div>
        </div>

        {/* ── Stats Cards ─────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            title="Total Tasks"
            value={stats.total_tasks || tasks.length}
            icon={ListTodo}
            description="Registered tasks"
          />
          <StatCard
            title="Active Tasks"
            value={stats.active_tasks || tasks.filter((t) => t.enabled).length}
            icon={Activity}
            description="Currently enabled"
          />
          <StatCard
            title="Success Rate"
            value={`${(stats?.success_rate_percent ?? 0).toFixed(1)}%`}
            icon={Percent}
            description="Last 24 hours"
            progressValue={stats?.success_rate_percent ?? 0}
          />
          <StatCard
            title="Avg Execution Time"
            value={
              stats?.avg_execution_time_ms > 0
                ? formatDuration(stats?.avg_execution_time_ms ?? 0)
                : "--"
            }
            icon={Timer}
            description="Mean duration"
          />
        </div>

        <Card className="bg-card/50 border-border backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="text-lg">Service Tailoring Sync</CardTitle>
            <CardDescription>
              Autonomous profile refresh for configured backend services
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>
                Last sync:{" "}
                {serviceTailoring.last_synced_at
                  ? formatDistanceToNow(new Date(serviceTailoring.last_synced_at), { addSuffix: true })
                  : "never"}
              </span>
              <span>Changes detected: {serviceTailoring.changes_detected}</span>
              <span>Syncs: {serviceTailoring.sync_count}</span>
              {schedulerStatus.single_worker_required && (
                <Badge variant="outline" className="text-amber-400 border-amber-500/30 bg-amber-500/10">
                  Single backend worker required for recurring runs
                </Badge>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(serviceTailoring.current_profile?.configured_services || {}).length > 0 ? (
                Object.entries(serviceTailoring.current_profile?.configured_services || {}).map(([name, service]) => (
                  <Badge key={name} variant="outline" className="bg-emerald-500/10 text-emerald-400 border-emerald-500/30">
                    {service.label}
                  </Badge>
                ))
              ) : (
                <span className="text-sm text-muted-foreground">No configured services detected yet.</span>
              )}
            </div>
            {(serviceTailoring.current_profile?.active_capabilities || []).length > 0 && (
              <div className="flex flex-wrap gap-2">
                {serviceTailoring.current_profile?.active_capabilities.slice(0, 8).map((capability) => (
                  <Badge key={capability} variant="outline" className="text-xs">
                    {capability}
                  </Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── Task Cards Grid ─────────────────────────────────────────── */}
        <div>
          <h2 className="text-lg font-semibold mb-3">Scheduled Tasks</h2>
          {tasks.length === 0 && dataLoadError ? (
            <Card className="bg-card/50 border-border backdrop-blur-sm">
              <CardContent className="flex flex-col items-center justify-center py-12 text-center">
                <AlertCircle className="h-12 w-12 text-destructive/70 mb-3" />
                <h3 className="text-lg font-medium mb-1">Scheduled tasks unavailable</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  The runtime did not return task data. Retry after the backend is available.
                </p>
                <Button onClick={() => void fetchData()} variant="outline">
                  <RotateCcw className="h-4 w-4 mr-2" />
                  Retry
                </Button>
              </CardContent>
            </Card>
          ) : tasks.length === 0 ? (
            <Card className="bg-card/50 border-border backdrop-blur-sm">
              <CardContent className="flex flex-col items-center justify-center py-12 text-center">
                <Bot className="h-12 w-12 text-muted-foreground/40 mb-3" />
                <h3 className="text-lg font-medium mb-1">No tasks yet</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  Create your first autonomous task to get started.
                </p>
                <Button onClick={() => setDialogOpen(true)} className="gap-1.5">
                  <Plus className="h-4 w-4" />
                  Create Task
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              <AnimatePresence>
                {tasks.map((task) => (
                  <TaskCard
                    key={task.id || task.name}
                    task={task}
                    onToggle={handleToggleTask}
                    onRun={handleRunTask}
                    onDelete={handleDeleteTask}
                  />
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>

        {/* ── Execution History ───────────────────────────────────────── */}
        <ExecutionHistoryTable executions={executions} />

        {/* ── Create Task Dialog ──────────────────────────────────────── */}
        <CreateTaskDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          onSubmit={handleCreateTask}
        />
      </div>
    </div>
  );
}
