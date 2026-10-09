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
  ListTodo,
  Users,
  Network,
  Share2,
  Zap,
  RefreshCw,
} from "lucide-react";
import { format, formatDistanceToNow, isValid, parseISO } from "date-fns";
import { toast } from "sonner";

import {
  jarvisAPI,
  type AgentTask,
  type TaskExecution,
  type Agent,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

// ─── Types ───────────────────────────────────────────────────────────────────

type SortField = "task_name" | "started_at";
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

interface CollabAgent {
  id: string;
  name: string | null;
  role: string | null;
  status: string | null;
}

interface CollabTask {
  id: string;
  description: string;
  agents_needed: string[];
  collaboration_pattern: string;
  status: string;
  created_at: string;
  completed_at?: string;
  result?: string;
}


// ─── Constants ───────────────────────────────────────────────────────────────

const SCHEDULE_TYPES = [{ value: "manual", label: "Manual" }];

const PRIORITY_OPTIONS = [
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "normal", label: "Normal" },
  { value: "low", label: "Low" },
];

const INITIAL_FORM: TaskFormData = {
  name: "",
  description: "",
  schedule_type: "manual",
  schedule_value: "",
  priority: "normal",
  timeout: 300,
  max_retries: 3,
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getErrorMessage(error: unknown, fallback = 'Unknown error'): string {
  if (error instanceof Error) {
    const status = getErrorStatus(error);
    if (status === 401) return `Session expired: ${error.message}`;
    if (status === 403) return `Permission denied: ${error.message}`;
    if (status && status >= 500) return `Server error (${status}): ${error.message}`;
    return error.message;
  }
  if (typeof error === 'string' && error.trim()) return error;
  if (error && typeof error === 'object' && 'message' in error && typeof (error as { message?: unknown }).message === 'string') {
    return (error as { message: string }).message;
  }
  return fallback;
}

function getErrorStatus(error: unknown): number | undefined {
  return error && typeof error === 'object' && 'status' in error
    ? Number((error as { status?: unknown }).status)
    : undefined;
}

function AgentRequestFailure({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const status = getErrorStatus(error);
  const title = status === 401 ? 'Session expired' : status === 403 ? 'Permission denied' : status && status >= 500 ? `Server error (${status})` : 'Data unavailable';
  const description = status === 401
    ? 'Sign in again to load this data.'
    : status === 403
      ? 'Your account is not permitted to read this resource.'
      : getErrorMessage(error, 'The service could not be reached.');
  return (
    <div role="alert" className="flex flex-col gap-3 rounded-md border border-destructive/40 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div><p className="font-medium">{title}</p><p className="text-sm text-muted-foreground">{description}</p></div>
      <Button variant="outline" size="sm" onClick={onRetry} className="shrink-0"><RefreshCw className="mr-2 h-4 w-4" />Retry</Button>
    </div>
  );
}

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

function formatScheduleDisplay(type: string, value?: string | null): string {
  if (!value && type === 'manual') return 'Manual run';
  if (!value) return 'No schedule configured';
  switch (type) {
    case 'manual':
      return 'Manual run';
    case 'interval':
      return `Every ${value}`;
    case 'cron':
      return `Cron: ${value}`;
    case 'once':
      return `Once: ${value}`;
    case 'event-driven':
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
}: {
  title: string;
  value: string | number;
  icon: React.ElementType;
  description?: string;
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
  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleRun = async () => {
    setIsRunning(true);
    try {
      await onRun(task.id!);
      toast.success(`Task "${task.name}" triggered`);
    } catch (error: unknown) {
      toast.error(`Failed to run task: ${getErrorMessage(error)}`);
    } finally {
      setIsRunning(false);
    }
  };

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await onDelete(task.id!);
      setConfirmDelete(false);
      toast.success(`Task "${task.name}" deleted`);
    } catch (error: unknown) {
      toast.error(`Failed to delete task: ${getErrorMessage(error)}`);
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
          {task.description && <p className="line-clamp-3 text-sm text-muted-foreground">{task.description}</p>}
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>Status: {task.status || (task.enabled ? 'enabled' : 'disabled')}</span>
            {task.created_at && isValid(parseISO(task.created_at)) && (
              <span>Created {formatDistanceToNow(parseISO(task.created_at), { addSuffix: true })}</span>
            )}
          </div>
          {/* Schedule display */}
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Clock className="h-3.5 w-3.5" />
            <span>
              {formatScheduleDisplay(task.schedule_type, task.schedule_value)}
            </span>
          </div>

          {/* Last execution */}
          {task.last_run_at && isValid(new Date(task.last_run_at)) ? (
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
              onClick={() => setConfirmDelete(true)}
              aria-label={`Delete ${task.name}`}
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
      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete task?</DialogTitle>
            <DialogDescription>This permanently removes “{task.name}”. This action cannot be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete} disabled={isDeleting}>
              {isDeleting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Delete task
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}

// ─── Execution History Table ─────────────────────────────────────────────────

function SortIcon({
  field,
  sortField,
  sortDirection,
}: {
  field: SortField;
  sortField: SortField;
  sortDirection: SortDirection;
}) {
  if (sortField !== field) return <ArrowUpDown className="h-3.5 w-3.5 ml-1 inline" />;
  if (sortDirection === "asc") return <ArrowUp className="h-3.5 w-3.5 ml-1 inline" />;
  return <ArrowDown className="h-3.5 w-3.5 ml-1 inline" />;
}

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
      }
      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [executions, sortField, sortDirection]);

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
                <SortIcon field="task_name" sortField={sortField} sortDirection={sortDirection} />
              </TableHead>
              <TableHead>Status</TableHead>
              <TableHead
                className="cursor-pointer select-none hover:text-foreground"
                onClick={() => handleSort("started_at")}
              >
                Started At
                <SortIcon field="started_at" sortField={sortField} sortDirection={sortDirection} />
              </TableHead>
              <TableHead>Completed</TableHead>
              <TableHead>Provider / model</TableHead>
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
                    {isValid(new Date(exec.started_at)) ? format(new Date(exec.started_at), "MMM d, h:mm:ss a") : "Timestamp unavailable"}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {exec.completed_at && isValid(new Date(exec.completed_at)) ? format(new Date(exec.completed_at), "MMM d, h:mm:ss a") : "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {[exec.provider, exec.model].filter(Boolean).join(" / ") || "Not reported"}
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

    if (form.schedule_type !== 'manual' && !form.schedule_value.trim()) {
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
    } catch (error: unknown) {
      toast.error(`Failed to create task: ${getErrorMessage(error)}`);
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
                Schedule Value {form.schedule_type !== 'manual' && <span className="text-red-400">*</span>}
              </Label>
              <Input
                id="schedule-value"
                placeholder={form.schedule_type === 'manual' ? 'Manual runs only; no recurrence configured' : 'Schedule value'}
                value={form.schedule_value}
                onChange={(e) => updateField("schedule_value", e.target.value)}
                className={errors.schedule_value ? "border-red-500" : ""}
                disabled={form.schedule_type === 'manual'}
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

// ─── Agent Graph Visualization ───────────────────────────────────────────────

function AgentGraph({ agents }: { agents: CollabAgent[] }) {
  if (!agents || agents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <Network className="h-12 w-12 text-muted-foreground/30 mb-3" />
        <p className="text-sm text-muted-foreground">
          No agents available for collaboration graph.
        </p>
      </div>
    );
  }

  // Layout agents in a circular arrangement for the graph
  const centerX = 180;
  const centerY = 180;
  const radius = 130;
  const positions = agents.map((_, i) => {
    const angle = (2 * Math.PI * i) / agents.length - Math.PI / 2;
    return {
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
    };
  });

  return (
    <div className="w-full h-96 flex items-center justify-center">
      <svg width="360" height="360" className="overflow-visible">
        {/* Background grid */}
        <defs>
          <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
            <path
              d="M 30 0 L 0 0 0 30"
              fill="none"
              stroke="hsl(var(--border))"
              strokeWidth="0.5"
              opacity="0.3"
            />
          </pattern>
          <linearGradient
            id="nodeGradient"
            x1="0%"
            y1="0%"
            x2="100%"
            y2="100%"
          >
            <stop offset="0%" stopColor="#3b82f6" />
            <stop offset="100%" stopColor="#06b6d4" />
          </linearGradient>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" rx="8" />

        {/* Connecting edges */}
        {agents.map((agent, i) => {
          const targetIndex = (i + 1) % agents.length;
          const startX = positions[i].x;
          const startY = positions[i].y;
          const endX = positions[targetIndex].x;
          const endY = positions[targetIndex].y;
          return (
            <line
              key={`${agent.id}-${targetIndex}`}
              x1={startX}
              y1={startY}
              x2={endX}
              y2={endY}
              stroke="hsl(var(--primary))"
              strokeWidth="1.5"
              opacity="0.4"
              strokeDasharray="4 2"
            />
          );
        })}

        {/* Agent nodes */}
        {agents.map((agent, i) => {
          const { x, y } = positions[i];
          const statusColor =
            agent.status === "active"
              ? "text-emerald-400"
              : agent.status === "busy"
              ? "text-amber-400"
              : "text-muted-foreground";
          return (
            <g key={agent.id}>
              <circle
                cx={x}
                cy={y}
                r="24"
                fill="url(#nodeGradient)"
                stroke="hsl(var(--border))"
                strokeWidth="2"
              />
              <text
                x={x}
                y={y - 32}
                textAnchor="middle"
                className="text-xs font-medium fill-muted-foreground"
              >
                {agent.name || agent.role || `Agent ${i + 1}`}
              </text>
              <circle
                cx={x}
                cy={y + 32}
                r="4"
                fill="currentColor"
                className={statusColor}
              />
            </g>
          );
        })}

        {/* Center hub */}
        <circle
          cx={centerX}
          cy={centerY}
          r="16"
          fill="hsl(var(--primary))"
          stroke="hsl(var(--border))"
          strokeWidth="1"
        />
        <text
          x={centerX}
          y={centerY + 3}
          textAnchor="middle"
          className="text-[8px] font-bold fill-white"
        >
          JARVIS
        </text>
      </svg>
    </div>
  );
}

// ─── Agent Collaboration Section ─────────────────────────────────────────────

function AgentCollaboration({
  collabAgents,
  collabTasks,
  collabAgentError,
  collabTaskError,
  onExecute,
  onRefresh,
  loading,
}: {
  collabAgents: CollabAgent[];
  collabTasks: CollabTask[];
  collabAgentError: unknown;
  collabTaskError: unknown;
  onExecute: (taskId: string) => void;
  onRefresh: () => void;
  loading: boolean;
}) {
  const [activeCollabTab, setActiveCollabTab] = useState("agents");

  return (
    <>
      {/* Collaboration Stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          title="Collaboration tasks"
          value={collabTaskError ? "Unavailable" : collabTasks.length}
          icon={ListTodo}
          description="Tasks returned for this account"
        />
        <StatCard
          title="Completed"
          value={collabTaskError ? "Unavailable" : collabTasks.filter((task) => task.status === "completed").length}
          icon={CheckCircle2}
          description="Completed tasks in the returned list"
        />
        <StatCard
          title="Agents"
          value={collabAgentError ? "Unavailable" : collabAgents.length}
          icon={Users}
          description="Registered collaboration agents"
        />
      </div>

      <Tabs
        value={activeCollabTab}
        onValueChange={setActiveCollabTab}
        className="w-full"
      >
        <TabsList className="grid w-full grid-cols-3 mb-4">
          <TabsTrigger value="agents">Agents & Graph</TabsTrigger>
          <TabsTrigger value="tasks">Collab Tasks</TabsTrigger>
          <TabsTrigger value="self-organize">Self-Organize</TabsTrigger>
        </TabsList>

        {/* Agents & Graph Tab */}
        <TabsContent value="agents" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Agent List */}
            <Card className="bg-card/50 border-border backdrop-blur-sm">
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Users className="h-5 w-5 text-purple-400" />
                    Collaboration Agents
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onRefresh}
                    disabled={loading}
                  >
                    <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                  </Button>
                </CardTitle>
                <CardDescription>
                  {collabAgents.length} agents available for collaborative tasks
                </CardDescription>
              </CardHeader>
              <CardContent>
                {collabAgentError ? (
                  <AgentRequestFailure error={collabAgentError} onRetry={onRefresh} />
                ) : collabAgents.length === 0 ? (
                  <div className="text-center py-8">
                    <Users className="h-10 w-10 text-muted-foreground/30 mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">
                      No collaboration agents registered.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {collabAgents.map((agent) => (
                      <div
                        key={agent.id}
                        className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-muted/20 transition-colors"
                      >
                        <div className="flex items-center gap-3">
                          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-purple-500 to-pink-400">
                            <Bot className="h-4 w-4 text-white" />
                          </div>
                          <div>
                            <p className="font-medium text-sm">
                              {agent.name || agent.role || `Agent`}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              Role: {agent.role || "unassigned"} • ID: {agent.id}
                            </p>
                          </div>
                        </div>
                        <Badge
                          variant={
                            agent.status === "active" ? "default" : "secondary"
                          }
                          className="text-xs"
                        >
                          {agent.status || "unknown"}
                        </Badge>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Agent Graph */}
            <Card className="bg-card/50 border-border backdrop-blur-sm">
              <CardHeader>
                <CardTitle>Agent Collaboration Graph</CardTitle>
                <CardDescription>
                  Visual topology of agent collaboration network
                </CardDescription>
              </CardHeader>
              <CardContent>
                <AgentGraph agents={collabAgents} />
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Collaboration Tasks Tab */}
        <TabsContent value="tasks" className="space-y-4">
          {collabTaskError ? (
            <AgentRequestFailure error={collabTaskError} onRetry={onRefresh} />
          ) : collabTasks.length === 0 ? (
            <Card className="bg-card/50 border-border backdrop-blur-sm">
              <CardContent className="flex flex-col items-center justify-center py-12 text-center">
                <Share2 className="h-12 w-12 text-muted-foreground/30 mb-3" />
                <h3 className="text-lg font-medium mb-1">
                  No collaboration tasks
                </h3>
                <p className="text-sm text-muted-foreground">
                  No collaboration tasks were returned for this account.
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {collabTasks.map((task) => (
                <Card
                  key={task.id}
                  className="bg-card/50 border-border backdrop-blur-sm"
                >
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Share2 className="h-5 w-5 text-cyan-400" />
                        <CardTitle className="text-sm font-semibold">
                          {task.description}
                        </CardTitle>
                      </div>
                      <Badge
                        variant="outline"
                        className={`text-xs ${getStatusBadge(task.status).className}`}
                      >
                        {task.status}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="pt-0 space-y-3">
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="secondary" className="text-xs">
                        Pattern: {task.collaboration_pattern}
                      </Badge>
                      <Badge variant="outline" className="text-xs">
                        Agents: {task.agents_needed.length}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        Created: {formatDistanceToNow(new Date(task.created_at), { addSuffix: true })}
                      </span>
                    </div>
                    {task.result && (
                      <div className="text-xs text-muted-foreground bg-muted/20 p-2 rounded">
                        <pre className="whitespace-pre-wrap break-all">
                          {task.result}
                        </pre>
                      </div>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => onExecute(task.id)}
                      disabled={task.status === "running"}
                    >
                      {task.status === "running" ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                      ) : (
                        <Play className="h-3.5 w-3.5 mr-1" />
                      )}
                      {task.status === "completed" ? "Re-run" : "Execute"}
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* Self-Organize Tab */}
        <TabsContent value="self-organize" className="space-y-4">
          <Card className="bg-card/50 border-border backdrop-blur-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-amber-400" />
                Automatic planning
              </CardTitle>
              <CardDescription>
                The backend reports automatic planning is not configured. No task can be submitted here.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="self-organize-desc">
                  Task Description
                </Label>
                <Textarea
                  id="self-organize-desc"
                  value=""
                  disabled
                  placeholder="Unavailable while automatic planning is not configured"
                  rows={3}
                />
              </div>
              {(
                <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
                  Automatic planning is not configured in this backend. This action is disabled because the endpoint returns “not configured”.
                </div>
              )}
              <Button
                disabled
                className="gap-2"
              >
                <Zap className="h-4 w-4" />
                Self-Organize
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function AgentsPage() {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [executions, setExecutions] = useState<TaskExecution[]>([]);
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null);
  const [serviceTailoring, setServiceTailoring] = useState<ServiceTailoringStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [collabLoading, setCollabLoading] = useState(true);
  const [dataErrors, setDataErrors] = useState<Partial<Record<'agents' | 'tasks' | 'scheduler' | 'executions' | 'tailoring', unknown>>>({});
  const [collabErrors, setCollabErrors] = useState<Partial<Record<'agents' | 'tasks', unknown>>>({});
  const [dialogOpen, setDialogOpen] = useState(false);
  const [collabAgents, setCollabAgents] = useState<CollabAgent[]>([]);
  const [collabTasks, setCollabTasks] = useState<CollabTask[]>([]);
  const [activeTab, setActiveTab] = useState('tasks');
  const [taskSearch, setTaskSearch] = useState('');
  const [taskStatusFilter, setTaskStatusFilter] = useState('all');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const visibleTasks = useMemo(() => tasks.filter((task) => {
    const query = taskSearch.trim().toLowerCase();
    return (!query || `${task.name} ${task.description || ''}`.toLowerCase().includes(query))
      && (taskStatusFilter === 'all' || task.status === taskStatusFilter);
  }), [tasks, taskSearch, taskStatusFilter]);

  // ── Fetch all data ──────────────────────────────────────────────────────

  const fetchData = useCallback(async () => {
    const [agentsRes, tasksRes, schedulerRes, executionsRes, tailoringRes] = await Promise.allSettled([
      jarvisAPI.getAgents(),
      jarvisAPI.getAgentTasks(50),
      jarvisAPI.getSchedulerStatus(),
      jarvisAPI.getTaskExecutions(20),
      jarvisAPI.getServiceTailoringStatus(),
    ]);
    const errors: Partial<Record<'agents' | 'tasks' | 'scheduler' | 'executions' | 'tailoring', unknown>> = {};
    if (agentsRes.status === 'fulfilled') {
      setAgents(agentsRes.value.agents ?? []);
    } else {
      setAgents([]);
      errors.agents = agentsRes.reason;
    }
    if (tasksRes.status === 'fulfilled') setTasks(tasksRes.value.tasks ?? []);
    else {
      setTasks([]);
      errors.tasks = tasksRes.reason;
    }
    if (schedulerRes.status === 'fulfilled') setSchedulerStatus(schedulerRes.value);
    else {
      setSchedulerStatus(null);
      errors.scheduler = schedulerRes.reason;
    }
    if (executionsRes.status === 'fulfilled') setExecutions(executionsRes.value.executions ?? []);
    else {
      setExecutions([]);
      errors.executions = executionsRes.reason;
    }
    if (tailoringRes.status === 'fulfilled') setServiceTailoring(tailoringRes.value);
    else {
      setServiceTailoring(null);
      errors.tailoring = tailoringRes.reason;
    }
    setDataErrors(errors);
    setLoading(false);
  }, []);

  const fetchCollabData = useCallback(async () => {
    setCollabLoading(true);
    const [agentsRes, tasksRes] = await Promise.allSettled([
      jarvisAPI.getCollaborationAgents(),
      jarvisAPI.getCollaborationTasks(),
    ]);
    const errors: Partial<Record<'agents' | 'tasks', unknown>> = {};
    if (agentsRes.status === "fulfilled") {
      setCollabAgents(agentsRes.value.agents || []);
    } else {
      setCollabAgents([]);
      errors.agents = agentsRes.reason;
    }
    if (tasksRes.status === "fulfilled") {
      setCollabTasks(tasksRes.value.tasks || []);
    } else {
      setCollabTasks([]);
      errors.tasks = tasksRes.reason;
    }
    setCollabErrors(errors);
    setCollabLoading(false);
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchData();
  }, [fetchData]);

  // Auto-refresh: poll agents data + collaboration data every 15s
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      fetchData();
      fetchCollabData();
    }, 15000);
    return () => clearInterval(interval);
  }, [fetchData, fetchCollabData, autoRefresh]);

  // Initial load of collaboration data
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchCollabData();
  }, [fetchCollabData]);

  // ── Handlers ────────────────────────────────────────────────────────────

  const handleCreateTask = async (formData: TaskFormData) => {
    await jarvisAPI.registerCustomTask({
      name: formData.name,
      description: formData.description,
      schedule_type: 'manual',
      schedule_value: null,
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
    } catch (error: unknown) {
      toast.error(`Failed to toggle task: ${getErrorMessage(error)}`);
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
      if (!schedulerStatus || schedulerStatus.status === 'NOT_CONFIGURED') {
        toast.error('The legacy scheduler is not configured for this environment.');
        return;
      }
      const newRunning = !schedulerStatus.running;
      await jarvisAPI.toggleScheduler(newRunning);
      setSchedulerStatus((prev) => prev ? ({ ...prev, running: newRunning }) : prev);
      toast.success(`Scheduler ${newRunning ? 'started' : 'stopped'}`);
    } catch (error: unknown) {
      toast.error(`Failed to toggle scheduler: ${getErrorMessage(error)}`);
    }
  };

  const handleExecuteCollabTask = async (taskId: string) => {
    try {
      await jarvisAPI.executeCollaborationTask(taskId);
      await fetchCollabData();
      toast.success("Collaboration task executed");
    } catch (error: unknown) {
      toast.error(`Failed to execute task: ${getErrorMessage(error)}`);
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
              Agents & tasks
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Inspect registered agents and run your own manual tasks
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Auto-refresh toggle */}
            <div className="flex items-center gap-2 rounded-lg border border-border bg-card/50 px-3 py-2 backdrop-blur-sm">
              <RefreshCw
                className={`h-4 w-4 ${autoRefresh ? "text-emerald-400 animate-spin-slow" : "text-muted-foreground"}`}
              />
              <span className="text-xs font-medium">
                Auto-refresh {autoRefresh ? "on" : "off"}
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={() => setAutoRefresh(!autoRefresh)}
              >
                {autoRefresh ? "Pause" : "Resume"}
              </Button>
            </div>

            {/* Scheduler toggle */}
            <div className="flex items-center gap-2 rounded-lg border border-border bg-card/50 px-3 py-2 backdrop-blur-sm">
              {schedulerStatus?.running ? (
                <Power className="h-4 w-4 text-emerald-400" />
              ) : (
                <PowerOff className="h-4 w-4 text-muted-foreground" />
              )}
              <span className="text-xs font-medium">
                {schedulerStatus?.status === 'NOT_CONFIGURED'
                  ? 'Scheduler not configured'
                  : schedulerStatus
                    ? `Scheduler ${schedulerStatus.running ? 'running' : 'stopped'}`
                    : 'Scheduler status unavailable'}
              </span>
              <span
                className={`relative flex h-2 w-2 rounded-full ${
                  schedulerStatus?.running ? "bg-emerald-500" : "bg-muted-foreground/40"
                }`}
              >
                {schedulerStatus?.running && (
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                )}
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={handleToggleScheduler}
                disabled={!schedulerStatus || schedulerStatus.status === 'NOT_CONFIGURED' || Boolean(dataErrors.scheduler)}
              >
                {!schedulerStatus || schedulerStatus.status === 'NOT_CONFIGURED' ? 'Unavailable' : schedulerStatus.running ? 'Stop' : 'Start'}
              </Button>
            </div>

            <Button onClick={() => setDialogOpen(true)} className="gap-1.5">
              <Plus className="h-4 w-4" />
              Create Task
            </Button>
          </div>
        </div>

        {dataErrors.scheduler !== undefined && <AgentRequestFailure error={dataErrors.scheduler} onRetry={() => void fetchData()} />}

        {/* ── Tab Navigation ── */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-2 mb-4">
            <TabsTrigger value="tasks" className="gap-2">
              <ListTodo className="h-4 w-4" />
              Manual task queue
            </TabsTrigger>
            <TabsTrigger value="collaboration" className="gap-2">
              <Users className="h-4 w-4" />
              Agent Collaboration
            </TabsTrigger>
          </TabsList>


        {/* ── Stats Cards ─────────────────────────────────────────────── */}
        <TabsContent value="tasks" className="space-y-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard title="Registered agents" value={dataErrors.agents ? 'Unavailable' : agents.length} icon={Bot} description="From the agent registry" />
            <StatCard title="Active agents" value={dataErrors.agents ? 'Unavailable' : agents.filter((agent) => agent.status === 'active').length} icon={Activity} description="Registry status = active" />
            <StatCard title="Tasks returned" value={dataErrors.tasks ? 'Unavailable' : tasks.length} icon={ListTodo} description="Owned manual tasks in this response" />
            <StatCard title="Enabled tasks" value={dataErrors.tasks ? 'Unavailable' : tasks.filter((task) => task.enabled).length} icon={Power} description="Task records marked enabled" />
          </div>

        <Card className="bg-card/50 border-border backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="text-lg">Service tailoring</CardTitle>
            <CardDescription>
              Backend-reported service profile configuration
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {dataErrors.tailoring ? (
              <AgentRequestFailure error={dataErrors.tailoring} onRetry={() => void fetchData()} />
            ) : serviceTailoring?.status === 'NOT_CONFIGURED' ? (
              <p className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
                Not configured by the backend. Sync counts, timestamps, and service profile are not available.
              </p>
            ) : !serviceTailoring ? (
              <p className="text-sm text-muted-foreground">Service-tailoring status has not been reported.</p>
            ) : (
              <>
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              {serviceTailoring.last_synced_at && isValid(new Date(serviceTailoring.last_synced_at)) && <span>Last sync: {formatDistanceToNow(new Date(serviceTailoring.last_synced_at), { addSuffix: true })}</span>}
              {serviceTailoring.changes_detected !== undefined && <span>Changes detected: {serviceTailoring.changes_detected}</span>}
              {serviceTailoring.sync_count !== undefined && <span>Syncs: {serviceTailoring.sync_count}</span>}
              {schedulerStatus?.single_worker_required && (
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
                <span className="text-sm text-muted-foreground">No configured services were reported.</span>
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
              </>
            )}
          </CardContent>
        </Card>

        <section aria-labelledby="agent-roster-heading" className="space-y-3">
          <div className="flex items-baseline justify-between">
            <h2 id="agent-roster-heading" className="text-lg font-semibold">Agent registry</h2>
            <span className="text-sm text-muted-foreground">Capabilities and statuses from the registry response</span>
          </div>
          {dataErrors.agents ? <AgentRequestFailure error={dataErrors.agents} onRetry={() => void fetchData()} /> : agents.length === 0 ? (
            <Card><CardContent className="py-6 text-sm text-muted-foreground">No agents were returned by the registry.</CardContent></Card>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {agents.map((agent) => (
                <Card key={agent.id}>
                  <CardContent className="flex items-start justify-between gap-3 p-4">
                    <div className="min-w-0">
                      <p className="font-medium">{agent.name || 'Unnamed agent'}</p>
                      <p className="text-sm text-muted-foreground">{agent.role || 'Role not reported'}</p>
                      <p className="mt-1 break-all font-mono text-xs text-muted-foreground">{agent.id}</p>
                      {agent.capabilities && agent.capabilities.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {agent.capabilities.map((capability) => <Badge key={capability} variant="secondary" className="text-xs">{capability}</Badge>)}
                        </div>
                      )}
                    </div>
                    <Badge variant="outline">{agent.status || 'unknown'}</Badge>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </section>

        {/* ── Task Cards Grid ─────────────────────────────────────────── */}
        <div>
          <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2 className="text-lg font-semibold">Task queue</h2>
              <p className="text-sm text-muted-foreground">Filters apply to the latest task response; recurring scheduling is not configured.</p>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(12rem,1fr)_10rem]">
              <Input aria-label="Search tasks" placeholder="Search name or description" value={taskSearch} onChange={(event) => setTaskSearch(event.target.value)} />
              <Select value={taskStatusFilter} onValueChange={setTaskStatusFilter}>
                <SelectTrigger aria-label="Filter tasks by status"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="running">Running</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          {dataErrors.tasks ? <AgentRequestFailure error={dataErrors.tasks} onRetry={() => void fetchData()} /> : tasks.length === 0 ? (
            <Card className="bg-card/50 border-border backdrop-blur-sm">
              <CardContent className="flex flex-col items-center justify-center py-12 text-center">
                <Bot className="h-12 w-12 text-muted-foreground/40 mb-3" />
                <h3 className="text-lg font-medium mb-1">No tasks yet</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  Create a manual task to add it to your queue.
                </p>
                <Button onClick={() => setDialogOpen(true)} className="gap-1.5">
                  <Plus className="h-4 w-4" />
                  Create Task
                </Button>
              </CardContent>
            </Card>
          ) : visibleTasks.length === 0 ? (
            <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">No tasks in this response match those filters.</CardContent></Card>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              <AnimatePresence>
                {visibleTasks.map((task) => (
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
        {dataErrors.executions
          ? <AgentRequestFailure error={dataErrors.executions} onRetry={() => void fetchData()} />
          : <ExecutionHistoryTable executions={executions} />}
        </TabsContent>

        {/* ── Agent Collaboration Tab ─────────────────────────────────── */}
        <TabsContent value="collaboration" className="space-y-6">
          <AgentCollaboration
            collabAgents={collabAgents}
            collabTasks={collabTasks}
            onExecute={handleExecuteCollabTask}
            onRefresh={fetchCollabData}
            loading={collabLoading}
            collabAgentError={collabErrors.agents}
            collabTaskError={collabErrors.tasks}
          />
        </TabsContent>
      </Tabs>

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
