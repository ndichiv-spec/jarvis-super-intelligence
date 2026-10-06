"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Cpu,
  MemoryStick as Memory,
  HardDrive,
  Clock,
  RefreshCw,
  Search,
  X,
  Trash2,
  Play,
  Clipboard,
  ClipboardPaste,
  Camera,
  Download,
  Copy,
  Check,
  AlertTriangle,
  Loader2,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  FileText,
  Globe,
  Terminal,
  FolderOpen,
  Calculator,
  Image as ImageIcon,
  Music,
  Video,
  Grid3X3,
  Eye,
  AlertCircle,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { toast } from "sonner";

import { jarvisAPI, type MetricsData } from "@/lib/api";
import { useSystemStore } from "@/stores/system-store";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

// ─── Types ───────────────────────────────────────────────────────────────────

interface SystemProcess {
  pid: number;
  name: string;
  cpu_percent: number;
  memory_percent: number;
  status: string;
  created_at?: string;
}

type ProcessSortField = "cpu_percent" | "memory_percent" | "name" | "status";
type SortDirection = "asc" | "desc";

interface AppItem {
  name: string;
  command: string;
  icon?: string;
}

interface ClipboardData {
  text: string;
  history?: Array<{ text: string; timestamp: string }>;
}

interface ScreenshotItem {
  filename: string;
  path: string;
  timestamp: string;
  dataUrl?: string;
}

// ─── Constants ───────────────────────────────────────────────────────────────

const REFRESH_INTERVAL_MS = 10_000;

const APP_ICONS: Record<string, React.ElementType> = {
  notepad: FileText,
  browser: Globe,
  cmd: Terminal,
  explorer: FolderOpen,
  calculator: Calculator,
  photos: ImageIcon,
  music: Music,
  video: Video,
  terminal: Terminal,
  files: FolderOpen,
  images: ImageIcon,
  default: Grid3X3,
};

const FALLBACK_APPS: AppItem[] = [
  { name: "Notepad", command: "notepad" },
  { name: "Browser", command: "browser" },
  { name: "Terminal", command: "cmd" },
  { name: "File Explorer", command: "explorer" },
  { name: "Calculator", command: "calculator" },
  { name: "Photos", command: "photos" },
  { name: "Music Player", command: "music" },
  { name: "Video Player", command: "video" },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  const parts: string[] = [];
  if (days > 0) parts.push(`${days}d`);
  if (hours > 0) parts.push(`${hours}h`);
  parts.push(`${minutes}m`);
  return parts.join(" ");
}

function getCpuColor(cpuPercent: number): string {
  if (cpuPercent > 50) return "text-red-400";
  if (cpuPercent > 25) return "text-amber-400";
  return "text-emerald-400";
}

function getCpuProgressColor(cpuPercent: number): string {
  if (cpuPercent > 50) return "bg-red-500";
  if (cpuPercent > 25) return "bg-amber-500";
  return "bg-emerald-500";
}

function getAppIcon(command: string): React.ElementType {
  const key = command.toLowerCase().replace(/\s+/g, "");
  return APP_ICONS[key] || APP_ICONS.default;
}

// ─── Gauge Component (CPU) ──────────────────────────────────────────────────

function CpuGauge({ value }: { value: number }) {
  const radius = 54;
  const circumference = Math.PI * radius;
  const progress = Math.min(value / 100, 1);
  const dashOffset = circumference * (1 - progress);
  const colorClass = getCpuProgressColor(value);

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative">
        <svg width="140" height="80" viewBox="0 0 140 80" className="overflow-visible">
          {/* Background arc */}
          <path
            d="M 10 70 A 54 54 0 0 1 130 70"
            fill="none"
            stroke="hsl(var(--muted))"
            strokeWidth="10"
            strokeLinecap="round"
          />
          {/* Progress arc */}
          <path
            d="M 10 70 A 54 54 0 0 1 130 70"
            fill="none"
            strokeWidth="10"
            strokeLinecap="round"
            className={colorClass}
            stroke="currentColor"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            style={{ transition: "stroke-dashoffset 0.8s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-end pb-1">
          <span className={`text-2xl font-bold ${getCpuColor(value)}`}>
            {value.toFixed(0)}%
          </span>
        </div>
      </div>
      <span className="text-xs text-muted-foreground">CPU Usage</span>
    </div>
  );
}

// ─── Status Card ─────────────────────────────────────────────────────────────

function StatusCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <Card className="bg-card/50 border-border backdrop-blur-sm">
        <CardContent className="flex flex-col items-center justify-center p-6">
          {children}
        </CardContent>
      </Card>
    </motion.div>
  );
}

// ─── System Status Cards ─────────────────────────────────────────────────────

function SystemStatusCards({
  metrics,
  lastRefreshed,
  onRefresh,
}: {
  metrics: MetricsData | null;
  lastRefreshed: Date | null;
  onRefresh: () => void;
}) {
  const cpu = metrics?.system.cpu_percent ?? 0;
  const memory = metrics?.system.memory_percent ?? 0;
  const disk = metrics?.system.disk_percent ?? 0;
  const uptime = metrics?.uptime_seconds ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">System Overview</h2>
        <div className="flex items-center gap-2">
          {lastRefreshed && (
            <span className="text-xs text-muted-foreground">
              Updated {formatDistanceToNow(lastRefreshed, { addSuffix: true })}
            </span>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onRefresh}
            aria-label="Refresh metrics"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* CPU */}
        <StatusCard title="CPU Usage">
          <CpuGauge value={cpu} />
        </StatusCard>

        {/* Memory */}
        <StatusCard title="Memory Usage">
          <div className="flex flex-col items-center gap-3 w-full">
            <div className="flex items-center gap-2">
              <Memory className="h-5 w-5 text-violet-400" />
              <span className="text-2xl font-bold">{memory.toFixed(1)}%</span>
            </div>
            <div className="relative h-2 w-full overflow-hidden rounded-full bg-secondary">
              <div
                className={`h-full transition-all ${
                  memory > 80
                    ? "bg-red-500"
                    : memory > 60
                    ? "bg-amber-500"
                    : "bg-violet-500"
                }`}
                style={{ width: `${memory}%` }}
              />
            </div>
            {metrics && (
              <span className="text-xs text-muted-foreground">
                {metrics.system.memory_available_mb.toFixed(0)} MB available
              </span>
            )}
          </div>
        </StatusCard>

        {/* Disk */}
        <StatusCard title="Disk Usage">
          <div className="flex flex-col items-center gap-3 w-full">
            <div className="flex items-center gap-2">
              <HardDrive className="h-5 w-5 text-cyan-400" />
              <span className="text-2xl font-bold">{disk.toFixed(1)}%</span>
            </div>
            <div className="relative h-2 w-full overflow-hidden rounded-full bg-secondary">
              <div
                className={`h-full transition-all ${
                  disk > 85
                    ? "bg-red-500"
                    : disk > 65
                    ? "bg-amber-500"
                    : "bg-cyan-500"
                }`}
                style={{ width: `${disk}%` }}
              />
            </div>
            {metrics && (
              <span className="text-xs text-muted-foreground">
                {metrics.system.disk_used_gb.toFixed(1)} GB used
              </span>
            )}
          </div>
        </StatusCard>

        {/* Uptime */}
        <StatusCard title="Uptime">
          <div className="flex flex-col items-center gap-3">
            <div className="flex items-center gap-2">
              <Clock className="h-5 w-5 text-emerald-400" />
              <span className="text-2xl font-bold tabular-nums">
                {formatUptime(uptime)}
              </span>
            </div>
            <span className="text-xs text-muted-foreground">
              {metrics?.system.process_count ?? 0} processes
            </span>
          </div>
        </StatusCard>
      </div>
    </div>
  );
}

// ─── Process Manager ─────────────────────────────────────────────────────────

function ProcessManager() {
  const { processes, setProcesses, isLoading, setLoading } = useSystemStore(
    (state) => ({
      processes: state.processes,
      setProcesses: state.setProcesses,
      isLoading: state.isLoading,
      setLoading: state.setLoading,
    })
  );

  const [search, setSearch] = useState("");
  const [sortField, setSortField] = useState<ProcessSortField>("cpu_percent");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [killTarget, setKillTarget] = useState<SystemProcess | null>(null);
  const [isKilling, setIsKilling] = useState(false);

  const fetchProcesses = useCallback(async () => {
    setLoading(true);
    try {
      const data = await jarvisAPI.getProcesses(50, sortField);
      setProcesses(data.processes || []);
    } catch (error: any) {
      toast.error(`Failed to load processes: ${error.message}`);
    } finally {
      setLoading(false);
    }
  }, [sortField, setProcesses, setLoading]);

  useEffect(() => {
    fetchProcesses();
  }, [fetchProcesses]);

  const handleSort = (field: ProcessSortField) => {
    if (sortField === field) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  };

  const handleKill = async () => {
    if (!killTarget) return;
    setIsKilling(true);
    try {
      await jarvisAPI.killProcess(killTarget.pid);
      toast.success(`Process "${killTarget.name}" (PID ${killTarget.pid}) terminated`);
      setKillTarget(null);
      fetchProcesses();
    } catch (error: any) {
      toast.error(`Failed to kill process: ${error.message}`);
    } finally {
      setIsKilling(false);
    }
  };

  const filtered = useMemo(() => {
    let result = processes;
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          String(p.pid).includes(q) ||
          p.status.toLowerCase().includes(q)
      );
    }
    return [...result].sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case "cpu_percent":
          cmp = a.cpu_percent - b.cpu_percent;
          break;
        case "memory_percent":
          cmp = a.memory_percent - b.memory_percent;
          break;
        case "name":
          cmp = a.name.localeCompare(b.name);
          break;
        case "status":
          cmp = a.status.localeCompare(b.status);
          break;
      }
      return sortDirection === "asc" ? cmp : -cmp;
    });
  }, [processes, search, sortField, sortDirection]);

  const SortIcon = ({ field }: { field: ProcessSortField }) => {
    if (sortField !== field) return <ArrowUpDown className="h-3.5 w-3.5 ml-1 inline opacity-50" />;
    return sortDirection === "asc"
      ? <ArrowUp className="h-3.5 w-3.5 ml-1 inline" />
      : <ArrowDown className="h-3.5 w-3.5 ml-1 inline" />;
  };

  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case "running":
        return <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30 text-xs">Running</Badge>;
      case "sleeping":
      case "sleep":
        return <Badge variant="secondary" className="text-xs">Sleeping</Badge>;
      case "idle":
        return <Badge variant="outline" className="text-xs">Idle</Badge>;
      default:
        return <Badge variant="outline" className="text-xs">{status}</Badge>;
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search processes..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
          {search && (
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7"
              onClick={() => setSearch("")}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={fetchProcesses}
          disabled={isLoading}
          className="gap-1.5"
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          Refresh
        </Button>
      </div>

      <Card className="bg-card/50 border-border backdrop-blur-sm">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-20">PID</TableHead>
                <TableHead
                  className="cursor-pointer select-none"
                  onClick={() => handleSort("name")}
                >
                  Name <SortIcon field="name" />
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none"
                  onClick={() => handleSort("cpu_percent")}
                >
                  CPU % <SortIcon field="cpu_percent" />
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none"
                  onClick={() => handleSort("memory_percent")}
                >
                  Memory % <SortIcon field="memory_percent" />
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none"
                  onClick={() => handleSort("status")}
                >
                  Status <SortIcon field="status" />
                </TableHead>
                <TableHead className="w-24">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && processes.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-12">
                    <Loader2 className="h-6 w-6 animate-spin mx-auto text-muted-foreground" />
                    <p className="text-sm text-muted-foreground mt-2">Loading processes...</p>
                  </TableCell>
                </TableRow>
              ) : filtered.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-12">
                    <Search className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
                    <p className="text-sm text-muted-foreground">No processes found</p>
                  </TableCell>
                </TableRow>
              ) : (
                filtered.map((proc) => (
                  <TableRow key={proc.pid}>
                    <TableCell className="font-mono text-xs">{proc.pid}</TableCell>
                    <TableCell className="font-medium">{proc.name}</TableCell>
                    <TableCell>
                      <span className={`font-semibold tabular-nums ${getCpuColor(proc.cpu_percent)}`}>
                        {proc.cpu_percent.toFixed(1)}%
                      </span>
                      {proc.cpu_percent > 50 && (
                        <AlertTriangle className="h-3.5 w-3.5 inline ml-1 text-red-400" />
                      )}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {proc.memory_percent.toFixed(1)}%
                    </TableCell>
                    <TableCell>{getStatusBadge(proc.status)}</TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-destructive"
                        onClick={() => setKillTarget(proc)}
                        title={`Kill ${proc.name}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Kill confirmation dialog */}
      <Dialog open={killTarget !== null} onOpenChange={(open) => !open && setKillTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-400" />
              Confirm Kill Process
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to terminate{" "}
              <span className="font-semibold text-foreground">{killTarget?.name}</span>{" "}
              (PID: {killTarget?.pid})? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setKillTarget(null)}
              disabled={isKilling}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleKill}
              disabled={isKilling}
            >
              {isKilling ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-1" />
                  Killing...
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4 mr-1" />
                  Kill Process
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── App Launcher ────────────────────────────────────────────────────────────

function AppLauncher() {
  const [apps, setApps] = useState<AppItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [launching, setLaunching] = useState<string | null>(null);

  const fetchApps = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await jarvisAPI.getCommonApps();
      const appList = (data.apps || data.common_apps || data) as AppItem[];
      if (Array.isArray(appList) && appList.length > 0) {
        setApps(appList);
      } else {
        setApps(FALLBACK_APPS);
      }
    } catch {
      setApps(FALLBACK_APPS);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchApps();
  }, [fetchApps]);

  const handleLaunch = async (app: AppItem) => {
    setLaunching(app.command);
    try {
      await jarvisAPI.launchApp(app.command);
      toast.success(`Launched ${app.name}`);
    } catch (error: any) {
      toast.error(`Failed to launch ${app.name}: ${error.message}`);
    } finally {
      setLaunching(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold">Applications</h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
        {apps.map((app, i) => {
          const Icon = getAppIcon(app.command);
          const isLaunching = launching === app.command;

          return (
            <motion.div
              key={app.command}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05, duration: 0.3 }}
            >
              <Card className="bg-card/50 border-border backdrop-blur-sm hover:border-primary/30 transition-colors">
                <CardContent className="flex flex-col items-center gap-3 p-5">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 border border-primary/20">
                    <Icon className="h-6 w-6 text-primary" />
                  </div>
                  <span className="text-sm font-medium text-center">{app.name}</span>
                  <Button
                    size="sm"
                    className="w-full gap-1.5 text-xs"
                    onClick={() => handleLaunch(app)}
                    disabled={isLaunching}
                  >
                    {isLaunching ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        Launching...
                      </>
                    ) : (
                      <>
                        <Play className="h-3.5 w-3.5" />
                        Launch
                      </>
                    )}
                  </Button>
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Clipboard Manager ───────────────────────────────────────────────────────

function ClipboardManager() {
  const [clipboardText, setClipboardText] = useState("");
  const [history, setHistory] = useState<Array<{ text: string; timestamp: string }>>([]);
  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSetting, setIsSetting] = useState(false);
  const [copiedFeedback, setCopiedFeedback] = useState(false);

  const fetchClipboard = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = (await jarvisAPI.getClipboard()) as ClipboardData;
      setClipboardText(data.text || "");
      if (data.history && Array.isArray(data.history)) {
        setHistory(data.history);
      }
    } catch (error: any) {
      toast.error(`Failed to read clipboard: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchClipboard();
  }, [fetchClipboard]);

  const handleCopyToClipboard = async () => {
    if (!inputText.trim()) {
      toast.error("Enter text to copy");
      return;
    }
    setIsSetting(true);
    try {
      await jarvisAPI.setClipboard(inputText);
      toast.success("Text set to clipboard");
      setInputText("");
      fetchClipboard();
    } catch (error: any) {
      toast.error(`Failed to set clipboard: ${error.message}`);
    } finally {
      setIsSetting(false);
    }
  };

  const handleCopyFromClipboard = async () => {
    try {
      await navigator.clipboard.writeText(clipboardText);
      setCopiedFeedback(true);
      toast.success("Copied to system clipboard");
      setTimeout(() => setCopiedFeedback(false), 2000);
    } catch {
      toast.error("Failed to copy");
    }
  };

  const handleHistoryRestore = async (text: string) => {
    setIsSetting(true);
    try {
      await jarvisAPI.setClipboard(text);
      toast.success("Clipboard restored from history");
      fetchClipboard();
    } catch (error: any) {
      toast.error(`Failed to restore: ${error.message}`);
    } finally {
      setIsSetting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Current clipboard */}
      <Card className="bg-card/50 border-border backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Clipboard className="h-5 w-5 text-primary" />
            Current Clipboard
          </CardTitle>
          <CardDescription>Content currently stored in the system clipboard</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : clipboardText ? (
            <>
              <div className="rounded-md border bg-muted/50 p-4 max-h-48 overflow-y-auto">
                <p className="text-sm whitespace-pre-wrap break-all font-mono">
                  {clipboardText}
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={handleCopyFromClipboard}
              >
                {copiedFeedback ? (
                  <>
                    <Check className="h-4 w-4 text-emerald-400" />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-4 w-4" />
                    Copy to System Clipboard
                  </>
                )}
              </Button>
            </>
          ) : (
            <div className="flex flex-col items-center py-8 text-muted-foreground">
              <Clipboard className="h-8 w-8 mb-2 opacity-50" />
              <p className="text-sm">Clipboard is empty</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Set clipboard */}
      <Card className="bg-card/50 border-border backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <ClipboardPaste className="h-5 w-5 text-primary" />
            Set Clipboard
          </CardTitle>
          <CardDescription>Enter text to set as the new clipboard content</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            placeholder="Enter text to copy to clipboard..."
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            rows={4}
          />
          <Button
            size="sm"
            className="gap-1.5"
            onClick={handleCopyToClipboard}
            disabled={isSetting || !inputText.trim()}
          >
            {isSetting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Setting...
              </>
            ) : (
              <>
                <ClipboardPaste className="h-4 w-4" />
                Set Clipboard
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* History */}
      {history.length > 0 && (
        <Card className="bg-card/50 border-border backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="text-lg">Clipboard History</CardTitle>
            <CardDescription>Recent clipboard items</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {history.map((item, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.03 }}
                  className="rounded-md border bg-muted/30 p-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-mono truncate">{item.text}</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        {formatDistanceToNow(new Date(item.timestamp), { addSuffix: true })}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 flex-shrink-0"
                      onClick={() => handleHistoryRestore(item.text)}
                      title="Restore to clipboard"
                    >
                      <ClipboardPaste className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </motion.div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ─── Screenshot Viewer ───────────────────────────────────────────────────────

function ScreenshotViewer() {
  const [screenshots, setScreenshots] = useState<ScreenshotItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [preview, setPreview] = useState<ScreenshotItem | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  const handleTakeScreenshot = async () => {
    setIsLoading(true);
    try {
      const filename = `screenshot_${Date.now()}.png`;
      const result = await jarvisAPI.takeScreenshot(filename);
      toast.success(`Screenshot taken: ${result.filename || filename}`);

      const newScreenshot: ScreenshotItem = {
        filename: result.filename || filename,
        path: result.path || "",
        timestamp: new Date().toISOString(),
        dataUrl: result.data_url || result.dataUrl || "",
      };
      setScreenshots((prev) => [newScreenshot, ...prev]);
    } catch (error: any) {
      toast.error(`Failed to take screenshot: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownload = async (screenshot: ScreenshotItem) => {
    setDownloading(screenshot.filename);
    try {
      if (screenshot.dataUrl) {
        const link = document.createElement("a");
        link.href = screenshot.dataUrl;
        link.download = screenshot.filename;
        link.click();
        toast.success(`Downloaded ${screenshot.filename}`);
      } else {
        toast.info("Download not available for this screenshot");
      }
    } catch {
      toast.error("Failed to download screenshot");
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Screenshots</h3>
        <Button
          size="sm"
          className="gap-1.5"
          onClick={handleTakeScreenshot}
          disabled={isLoading}
        >
          {isLoading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Capturing...
            </>
          ) : (
            <>
              <Camera className="h-4 w-4" />
              Take Screenshot
            </>
          )}
        </Button>
      </div>

      {screenshots.length === 0 ? (
        <Card className="bg-card/50 border-border backdrop-blur-sm">
          <CardContent className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <Camera className="h-12 w-12 mb-3 opacity-40" />
            <p className="text-sm font-medium">No screenshots yet</p>
            <p className="text-xs mt-1">Click "Take Screenshot" to capture your screen</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
          <AnimatePresence>
            {screenshots.map((ss, i) => (
              <motion.div
                key={ss.filename}
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ delay: i * 0.05 }}
              >
                <Card className="bg-card/50 border-border backdrop-blur-sm overflow-hidden hover:border-primary/30 transition-colors cursor-pointer group">
                  <div
                    className="relative aspect-video bg-muted/30 flex items-center justify-center"
                    onClick={() => setPreview(ss)}
                  >
                    {ss.dataUrl ? (
                      <img
                        src={ss.dataUrl}
                        alt={ss.filename}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="flex flex-col items-center text-muted-foreground">
                        <ImageIcon className="h-8 w-8 opacity-40 mb-1" />
                        <span className="text-xs">Preview unavailable</span>
                      </div>
                    )}
                    {/* Hover overlay */}
                    <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 bg-white/10 hover:bg-white/20 text-white"
                        onClick={(e) => {
                          e.stopPropagation();
                          setPreview(ss);
                        }}
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                      {ss.dataUrl && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 bg-white/10 hover:bg-white/20 text-white"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDownload(ss);
                          }}
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                  <div className="p-2">
                    <p className="text-xs font-mono truncate">{ss.filename}</p>
                    <p className="text-[10px] text-muted-foreground">
                      {formatDistanceToNow(new Date(ss.timestamp), { addSuffix: true })}
                    </p>
                  </div>
                </Card>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Preview Modal */}
      <Dialog open={preview !== null} onOpenChange={(open) => !open && setPreview(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{preview?.filename}</DialogTitle>
            <DialogDescription>
              {preview && formatDistanceToNow(new Date(preview.timestamp), { addSuffix: true })}
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-lg overflow-hidden border bg-muted/20">
            {preview?.dataUrl ? (
              <img
                src={preview.dataUrl}
                alt={preview.filename}
                className="w-full h-auto"
              />
            ) : (
              <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                <ImageIcon className="h-12 w-12 opacity-40 mb-2" />
                <p className="text-sm">Image data not available</p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPreview(null)}>
              Close
            </Button>
            {preview?.dataUrl && (
              <Button
                className="gap-1.5"
                onClick={() => preview && handleDownload(preview)}
                disabled={downloading === preview?.filename}
              >
                {downloading === preview?.filename ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Downloading...
                  </>
                ) : (
                  <>
                    <Download className="h-4 w-4" />
                    Download
                  </>
                )}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── Main System Page ────────────────────────────────────────────────────────

export default function SystemPage() {
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const [isFetchingMetrics, setIsFetchingMetrics] = useState(false);

  const fetchMetrics = useCallback(async () => {
    setIsFetchingMetrics(true);
    try {
      const data = await jarvisAPI.getMetrics();
      setMetrics(data);
      setLastRefreshed(new Date());
    } catch (error: any) {
      toast.error(`Failed to load system metrics: ${error.message}`);
    } finally {
      setIsFetchingMetrics(false);
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchMetrics]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">System Dashboard</h1>
        <p className="text-muted-foreground mt-1">
          Monitor and control your system from one place.
        </p>
      </div>

      {/* Status Cards */}
      <SystemStatusCards
        metrics={metrics}
        lastRefreshed={lastRefreshed}
        onRefresh={fetchMetrics}
      />

      {/* Tabs */}
      <Tabs defaultValue="processes" className="w-full">
        <TabsList className="grid w-full grid-cols-4 max-w-lg">
          <TabsTrigger value="processes" className="text-xs sm:text-sm">
            <Cpu className="h-3.5 w-3.5 mr-1.5 hidden sm:inline" />
            Processes
          </TabsTrigger>
          <TabsTrigger value="apps" className="text-xs sm:text-sm">
            <Grid3X3 className="h-3.5 w-3.5 mr-1.5 hidden sm:inline" />
            Apps
          </TabsTrigger>
          <TabsTrigger value="clipboard" className="text-xs sm:text-sm">
            <Clipboard className="h-3.5 w-3.5 mr-1.5 hidden sm:inline" />
            Clipboard
          </TabsTrigger>
          <TabsTrigger value="screenshots" className="text-xs sm:text-sm">
            <Camera className="h-3.5 w-3.5 mr-1.5 hidden sm:inline" />
            Screenshots
          </TabsTrigger>
        </TabsList>

        <TabsContent value="processes" className="mt-6">
          <ProcessManager />
        </TabsContent>

        <TabsContent value="apps" className="mt-6">
          <AppLauncher />
        </TabsContent>

        <TabsContent value="clipboard" className="mt-6">
          <ClipboardManager />
        </TabsContent>

        <TabsContent value="screenshots" className="mt-6">
          <ScreenshotViewer />
        </TabsContent>
      </Tabs>
    </div>
  );
}
