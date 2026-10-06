"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain, Zap, Activity, Cpu, Database, Globe, Shield,
  ArrowUpRight, ArrowDownRight, Pause, Play, Square, RotateCcw,
  TrendingUp, Search, Bell, BookOpen, HardDrive, Network,
  CheckCircle, AlertTriangle, XCircle, Clock, RefreshCw,
  Terminal, Code2, FileText, Settings, Sparkles, Eye,
  ChevronRight, ChevronDown, Layers, BarChart3, PieChart,
  Power, Download, Upload, Wifi, WifiOff, Server,
  GitBranch, Target, Timer, Gauge, AlertCircle, Info,
  PlayCircle, StopCircle, Plus, X
} from "lucide-react";
import {
  RadialBarChart, RadialBar, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area,
  BarChart, Bar, Cell
} from "recharts";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
  DialogDescription, DialogFooter, DialogTrigger
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Tabs, TabsContent, TabsList, TabsTrigger
} from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { jarvisAPI } from "@/lib/api";
import { toast } from "sonner";

// ============================================================
// DATA & TYPES
// ============================================================

interface AIModel {
  id: string;
  name: string;
  provider: string;
  status: "online" | "offline" | "loading";
  benchmark: number;
  speed: number; // tokens/sec
  latency: number; // ms
  active: boolean;
  icon: React.ElementType;
  color: string;
  specialty: string;
}

interface AutonomousGoal {
  id: string;
  name: string;
  progress: number;
  step: string;
  totalSteps: number;
  eta: string;
  status: "running" | "paused" | "completed" | "error";
  model: string;
  startedAt: string;
}

interface UpgradeInfo {
  currentVersion: string;
  latestVersion: string;
  hasUpdate: boolean;
  packages: Array<{ name: string; current: string; latest: string; critical: boolean }>;
  lastUpgrade: string;
  history: Array<{ version: string; date: string; changes: string[] }>;
}

interface KnowledgeFeed {
  trending: Array<{ topic: string; score: number; category: string }>;
  recentSearches: Array<{ query: string; time: string; results: number }>;
  breakingNews: Array<{ title: string; source: string; time: string; urgency: "high" | "medium" | "low" }>;
  stats: { entries: number; sources: number; freshness: number; lastIndexed: string };
}

interface SystemHealth {
  cpu: number;
  memory: number;
  disk: number;
  network: { up: number; down: number };
  processes: number;
  uptime: number;
  selfHealingActions: number;
  recoveryRate: number;
  history: Array<{ time: string; cpu: number; memory: number }>;
}

const MODEL_COLORS: Record<string, string> = {
  ollama: "#3b82f6",
  openai: "#10a37f",
  gemini: "#8b5cf6",
  claude: "#f59e0b",
  mistral: "#ef4444",
  llama: "#06b6d4",
};

const INITIAL_MODELS: AIModel[] = [
  { id: "ollama-local", name: "Ollama Local", provider: "Ollama", status: "online", benchmark: 78.5, speed: 42, latency: 120, active: true, icon: Cpu, color: MODEL_COLORS.ollama, specialty: "Local inference, privacy" },
  { id: "gpt4", name: "GPT-4 Turbo", provider: "OpenAI", status: "online", benchmark: 92.3, speed: 35, latency: 350, active: false, icon: Zap, color: MODEL_COLORS.openai, specialty: "Complex reasoning, code" },
  { id: "gemini-pro", name: "Gemini 1.5 Pro", provider: "Google", status: "online", benchmark: 90.1, speed: 40, latency: 280, active: false, icon: Sparkles, color: MODEL_COLORS.gemini, specialty: "Multimodal, long context" },
  { id: "claude-3", name: "Claude 3.5 Sonnet", provider: "Anthropic", status: "online", benchmark: 91.7, speed: 38, latency: 310, active: false, icon: Brain, color: MODEL_COLORS.claude, specialty: "Writing, analysis" },
  { id: "mistral", name: "Mistral Large", provider: "Mistral AI", status: "offline", benchmark: 85.2, speed: 45, latency: 200, active: false, icon: Terminal, color: MODEL_COLORS.mistral, specialty: "European compliance" },
  { id: "llama3", name: "Llama 3 70B", provider: "Meta", status: "online", benchmark: 82.4, speed: 30, latency: 180, active: false, icon: Network, color: MODEL_COLORS.llama, specialty: "Open-source, fine-tuning" },
];

const INITIAL_GOALS: AutonomousGoal[] = [
  { id: "g1", name: "Knowledge Base Expansion", progress: 73, step: "Indexing new sources", totalSteps: 24, eta: "12 min", status: "running", model: "Ollama Local", startedAt: "2h ago" },
  { id: "g2", name: "System Health Optimization", progress: 45, step: "Analyzing metrics", totalSteps: 10, eta: "5 min", status: "running", model: "GPT-4 Turbo", startedAt: "15 min ago" },
  { id: "g3", name: "Code Review Pipeline", progress: 100, step: "Complete", totalSteps: 8, eta: "Done", status: "completed", model: "Claude 3.5", startedAt: "1h ago" },
  { id: "g4", name: "Security Audit Scan", progress: 12, step: "Scanning endpoints", totalSteps: 32, eta: "45 min", status: "running", model: "Gemini Pro", startedAt: "3 min ago" },
];

const INITIAL_UPGRADE: UpgradeInfo = {
  currentVersion: "3.2.1",
  latestVersion: "3.3.0",
  hasUpdate: true,
  packages: [
    { name: "fastapi", current: "0.109.0", latest: "0.115.0", critical: true },
    { name: "langchain", current: "0.1.5", latest: "0.3.0", critical: true },
    { name: "ollama", current: "0.1.26", latest: "0.4.0", critical: false },
    { name: "transformers", current: "4.37.0", latest: "4.44.0", critical: false },
    { name: "pydantic", current: "2.6.0", latest: "2.9.0", critical: true },
  ],
  lastUpgrade: "2026-04-10T14:30:00Z",
  history: [
    { version: "3.2.1", date: "2026-04-10", changes: ["Fixed memory leak", "Improved response time"] },
    { version: "3.2.0", date: "2026-04-05", changes: ["Added multi-model routing", "New knowledge ingestion"] },
    { version: "3.1.0", date: "2026-03-28", changes: ["Self-healing v2", "Enhanced security"] },
  ],
};

const INITIAL_KNOWLEDGE: KnowledgeFeed = {
  trending: [
    { topic: "AI Agent Frameworks", score: 95, category: "AI" },
    { topic: "Rust for Systems Programming", score: 88, category: "Dev" },
    { topic: "Quantum Computing Breakthroughs", score: 82, category: "Science" },
    { topic: "Edge AI Deployment", score: 79, category: "AI" },
    { topic: "WebAssembly Runtime", score: 74, category: "Dev" },
    { topic: "Neural Architecture Search", score: 71, category: "Research" },
  ],
  recentSearches: [
    { query: "best practices for RAG pipelines", time: "2m ago", results: 342 },
    { query: "autonomous agent memory patterns", time: "15m ago", results: 189 },
    { query: "fastapi middleware optimization", time: "1h ago", results: 567 },
    { query: "ollama model comparison 2026", time: "2h ago", results: 234 },
  ],
  breakingNews: [
    { title: "OpenAI releases GPT-5 preview", source: "TechCrunch", time: "5m ago", urgency: "high" },
    { title: "Meta open-sources Llama 4", source: "The Verge", time: "22m ago", urgency: "high" },
    { title: "New Python 3.13 performance gains", source: "PyPA", time: "1h ago", urgency: "medium" },
  ],
  stats: { entries: 15847, sources: 234, freshness: 94, lastIndexed: "30s ago" },
};

const INITIAL_HEALTH: SystemHealth = {
  cpu: 34,
  memory: 62,
  disk: 45,
  network: { up: 2.4, down: 18.7 },
  processes: 47,
  uptime: 172800,
  selfHealingActions: 23,
  recoveryRate: 99.2,
  history: [
    { time: "00:00", cpu: 28, memory: 55 },
    { time: "04:00", cpu: 22, memory: 52 },
    { time: "08:00", cpu: 45, memory: 61 },
    { time: "12:00", cpu: 52, memory: 68 },
    { time: "16:00", cpu: 38, memory: 59 },
    { time: "20:00", cpu: 31, memory: 56 },
    { time: "Now", cpu: 34, memory: 62 },
  ],
};

// ============================================================
// UTILITY HELPERS
// ============================================================

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${d}d ${h}h ${m}m`;
}

function formatTimeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours > 24) return `${Math.floor(hours / 24)}d ago`;
  if (hours > 0) return `${hours}h ago`;
  return `${Math.floor(diff / 60000)}m ago`;
}

// ============================================================
// REUSABLE SUB-COMPONENTS
// ============================================================

function RadialGauge({ value, size = 120, label, color, sublabel }: { value: number; size?: number; label: string; color: string; sublabel?: string }) {
  const data = [{ name: label, value, fill: color }];
  return (
    <div className="flex flex-col items-center gap-1">
      <ResponsiveContainer width={size} height={size}>
        <RadialBarChart cx="50%" cy="50%" innerRadius="70%" outerRadius="100%" data={data} startAngle={180} endAngle={-180}>
          <RadialBar dataKey="value" cornerRadius={12} background={{ fill: "rgba(255,255,255,0.05)" }} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="-mt-12 text-center">
        <div className="text-xl font-bold" style={{ color }}>{value}%</div>
        <div className="text-[10px] text-muted-foreground/60 uppercase tracking-wider">{label}</div>
        {sublabel && <div className="text-[9px] text-muted-foreground/40">{sublabel}</div>}
      </div>
    </div>
  );
}

function StatusDot({ status, pulse }: { status: "online" | "offline" | "loading"; pulse?: boolean }) {
  const colors = { online: "bg-emerald-400", offline: "bg-red-400", loading: "bg-amber-400" };
  return (
    <span className={`relative flex h-2.5 w-2.5 rounded-full ${colors[status]}`}>
      {pulse && status === "online" && (
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
      )}
    </span>
  );
}

function SectionHeader({ icon: Icon, title, badge, right }: { icon: React.ElementType; title: string; badge?: string; right?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-4">
      <div className="flex items-center gap-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500/20 to-cyan-500/20 border border-blue-500/10">
          <Icon className="h-4 w-4 text-blue-400" />
        </div>
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        {badge && (
          <Badge className="h-4 px-1.5 text-[9px] bg-blue-500/20 text-blue-400 border-blue-500/30">{badge}</Badge>
        )}
      </div>
      {right}
    </div>
  );
}

// ============================================================
// MAIN OMEGA PAGE
// ============================================================

export default function OmegaPage() {
  // State
  const [models, setModels] = useState<AIModel[]>(INITIAL_MODELS);
  const [goals, setGoals] = useState<AutonomousGoal[]>(INITIAL_GOALS);
  const [upgrade, setUpgrade] = useState<UpgradeInfo>(INITIAL_UPGRADE);
  const [knowledge, setKnowledge] = useState<KnowledgeFeed>(INITIAL_KNOWLEDGE);
  const [health, setHealth] = useState<SystemHealth>(INITIAL_HEALTH);
  const [autonomousMode, setAutonomousMode] = useState(true);
  const [autoUpgrade, setAutoUpgrade] = useState(false);
  const [showComparison, setShowComparison] = useState(false);
  const [comparisonModels, setComparisonModels] = useState<string[]>([]);
  const [comparisonResults, setComparisonResults] = useState<Record<string, string>>({});
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [comparisonPrompt, setComparisonPrompt] = useState("Explain quantum computing in simple terms");
  const [showCustomGoal, setShowCustomGoal] = useState(false);
  const [customGoalName, setCustomGoalName] = useState("");
  const [customGoalDesc, setCustomGoalDesc] = useState("");
  const [showUpgradeHistory, setShowUpgradeHistory] = useState(false);
  const [isUpgrading, setIsUpgrading] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");

  // Fetch real metrics periodically
  const fetchMetrics = useCallback(async () => {
    try {
      const metrics = await jarvisAPI.getMetrics();
      setHealth((prev) => ({
        ...prev,
        cpu: metrics.system?.cpu_percent ?? prev.cpu,
        memory: metrics.system?.memory_percent ?? prev.memory,
        disk: metrics.system?.disk_percent ?? prev.disk,
        processes: metrics.system?.process_count ?? prev.processes,
        uptime: metrics.uptime_seconds ?? prev.uptime,
      }));
    } catch {
      // Silently fail - use mock data
    }
  }, []);

  const fetchHealth = useCallback(async () => {
    try {
      const report = await jarvisAPI.getHealthReport();
      setHealth((prev) => ({
        ...prev,
        recoveryRate: report.health_rate_percent ?? prev.recoveryRate,
        selfHealingActions: report.recent_recoveries ?? prev.selfHealingActions,
      }));
    } catch {
      // Silently fail
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
    fetchHealth();
    const interval = setInterval(() => {
      fetchMetrics();
      fetchHealth();
      // Simulate live data fluctuations
      setHealth((prev) => ({
        ...prev,
        cpu: Math.max(10, Math.min(90, prev.cpu + (Math.random() - 0.5) * 6)),
        memory: Math.max(30, Math.min(90, prev.memory + (Math.random() - 0.5) * 3)),
        network: {
          up: Math.max(0.5, prev.network.up + (Math.random() - 0.5) * 0.5),
          down: Math.max(5, prev.network.down + (Math.random() - 0.5) * 2),
        },
      }));
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchMetrics, fetchHealth]);

  // Simulate goal progress
  useEffect(() => {
    const interval = setInterval(() => {
      setGoals((prev) =>
        prev.map((g) => {
          if (g.status !== "running") return g;
          const newProgress = Math.min(100, g.progress + Math.random() * 1.5);
          return {
            ...g,
            progress: Math.round(newProgress * 10) / 10,
            status: newProgress >= 100 ? "completed" : "running",
          };
        })
      );
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleModelSwitch = (modelId: string) => {
    setModels((prev) =>
      prev.map((m) => ({
        ...m,
        active: m.id === modelId,
        status: m.id === modelId ? "loading" : m.status,
      }))
    );
    setTimeout(() => {
      setModels((prev) =>
        prev.map((m) => ({
          ...m,
          status: m.id === modelId ? "online" : m.status,
        }))
      );
      toast.success(`Switched to ${models.find((m) => m.id === modelId)?.name}`);
    }, 1200);
  };

  const handleToggleGoal = (goalId: string) => {
    setGoals((prev) =>
      prev.map((g) => {
        if (g.id !== goalId) return g;
        const newStatus = g.status === "running" ? "paused" : g.status === "paused" ? "running" : g.status;
        return { ...g, status: newStatus };
      })
    );
  };

  const handleAbortGoal = (goalId: string) => {
    setGoals((prev) => prev.filter((g) => g.id !== goalId));
    toast.info("Goal aborted");
  };

  const handleUpgrade = () => {
    setIsUpgrading(true);
    toast.info("Starting system upgrade...");
    setTimeout(() => {
      setUpgrade((prev) => ({
        ...prev,
        currentVersion: prev.latestVersion,
        latestVersion: prev.latestVersion,
        hasUpdate: false,
        packages: prev.packages.map((p) => ({ ...p, current: p.latest })),
        lastUpgrade: new Date().toISOString(),
        history: [{ version: prev.latestVersion, date: new Date().toISOString().split("T")[0], changes: ["System upgrade", "Security patches"] }, ...prev.history],
      }));
      setIsUpgrading(false);
      toast.success("Upgrade completed successfully!");
    }, 5000);
  };

  const handleRunComparison = async () => {
    if (comparisonModels.length < 2) {
      toast.error("Select at least 2 models for comparison");
      return;
    }
    setComparisonLoading(true);
    setComparisonResults({});
    // Simulate API responses from different models
    await new Promise((r) => setTimeout(r, 2000));
    const results: Record<string, string> = {};
    for (const mId of comparisonModels) {
      const model = models.find((m) => m.id === mId);
      if (!model) continue;
      results[mId] = `[${model.name} Response]\nQuantum computing uses quantum bits (qubits) that can exist in multiple states simultaneously through superposition. This allows quantum computers to process vast amounts of information in parallel, solving certain problems exponentially faster than classical computers. Key principles include superposition, entanglement, and quantum interference.`;
    }
    setComparisonResults(results);
    setComparisonLoading(false);
  };

  const handleAddCustomGoal = () => {
    if (!customGoalName.trim()) return;
    const newGoal: AutonomousGoal = {
      id: `g-${Date.now()}`,
      name: customGoalName,
      progress: 0,
      step: "Initializing",
      totalSteps: 10,
      eta: "Calculating...",
      status: "running",
      model: models.find((m) => m.active)?.name || "Ollama Local",
      startedAt: "Just now",
    };
    setGoals((prev) => [newGoal, ...prev]);
    setCustomGoalName("");
    setCustomGoalDesc("");
    setShowCustomGoal(false);
    toast.success(`Goal "${newGoal.name}" started`);
  };

  const handleQuickAction = (action: string) => {
    toast.info(`${action} initiated...`);
    // Simulate action
    setTimeout(() => toast.success(`${action} completed`), 3000);
  };

  // Computed values
  const activeModel = useMemo(() => models.find((m) => m.active), [models]);
  const avgBenchmark = useMemo(() => Math.round(models.reduce((s, m) => s + m.benchmark, 0) / models.length * 10) / 10, [models]);
  const runningGoals = useMemo(() => goals.filter((g) => g.status === "running").length, [goals]);
  const criticalPackages = useMemo(() => upgrade.packages.filter((p) => p.critical).length, [upgrade.packages]);

  const chartColors = ["#3b82f6", "#8b5cf6", "#10a37f", "#f59e0b", "#ef4444", "#06b6d4"];

  // ============================================================
  // RENDER
  // ============================================================

  return (
    <div className="min-h-screen bg-[hsl(222,47%,6%)] bg-grid">
      {/* Ambient glow effects */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-40 -left-40 h-96 w-96 rounded-full bg-blue-500/5 blur-3xl" />
        <div className="absolute top-1/3 -right-40 h-80 w-80 rounded-full bg-cyan-500/5 blur-3xl" />
        <div className="absolute -bottom-40 left-1/3 h-96 w-96 rounded-full bg-purple-500/5 blur-3xl" />
      </div>

      <div className="relative mx-auto max-w-[1800px] px-4 py-6 space-y-6">

        {/* ============================================================
            HEADER
            ============================================================ */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col md:flex-row md:items-center justify-between gap-4"
        >
          <div className="flex items-center gap-4">
            <div className="relative">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 via-cyan-400 to-blue-500 shadow-2xl shadow-blue-500/30">
                <Brain className="h-7 w-7 text-white" />
              </div>
              <div className="absolute -inset-2 rounded-2xl bg-gradient-to-r from-blue-500/20 via-cyan-500/20 to-blue-500/20 blur-xl animate-pulse" />
            </div>
            <div>
              <h1 className="text-3xl font-extrabold bg-gradient-to-r from-blue-400 via-cyan-300 to-blue-400 bg-clip-text text-transparent text-glow">
                OMEGA CONTROL PANEL
              </h1>
              <p className="text-sm text-muted-foreground/60">
                Ultimate AI Command Center v3.3.0 — Autonomous Intelligence Platform
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
              <StatusDot status="online" pulse />
              <span className="text-sm font-medium text-emerald-400">All Systems Operational</span>
            </div>
            <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-white/[0.03] border border-white/5">
              <Clock className="h-4 w-4 text-muted-foreground/40" />
              <span className="text-xs text-muted-foreground/60">Uptime: {formatUptime(health.uptime)}</span>
            </div>
          </div>
        </motion.div>

        {/* ============================================================
            SECTION 1: AI MODEL CONTROLLER
            ============================================================ */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-glow rounded-2xl p-5"
        >
          <SectionHeader
            icon={Brain}
            title="AI Model Controller"
            badge={`${models.filter((m) => m.status === "online").length} Online`}
            right={
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground/50">Avg Benchmark:</span>
                <span className="text-sm font-bold text-blue-400">{avgBenchmark}</span>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs bg-white/[0.03] border-white/10 hover:bg-white/5"
                  onClick={() => setShowComparison(!showComparison)}
                >
                  <BarChart3 className="h-3.5 w-3.5 mr-1" />
                  Compare
                </Button>
              </div>
            }
          />

          {/* Active model routing indicator */}
          <div className="mb-4 flex items-center gap-3 px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-500/10 to-cyan-500/5 border border-blue-500/10">
            <GitBranch className="h-4 w-4 text-blue-400" />
            <span className="text-xs text-muted-foreground/60">Auto-Routing:</span>
            <span className="text-sm font-semibold text-blue-400">{activeModel?.name || "None"}</span>
            <span className="text-xs text-muted-foreground/40">— Selected for:</span>
            <span className="text-xs text-muted-foreground/50">{activeModel?.specialty || "—"}</span>
            <div className="ml-auto flex items-center gap-1">
              <span className="text-[10px] text-muted-foreground/40">Confidence:</span>
              <span className="text-xs font-bold text-emerald-400">{activeModel ? Math.round(activeModel.benchmark / 100 * 100) : 0}%</span>
            </div>
          </div>

          {/* Model cards grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
            {models.map((model) => {
              const Icon = model.icon;
              const isActive = model.active;
              return (
                <motion.button
                  key={model.id}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => handleModelSwitch(model.id)}
                  className={`relative rounded-xl p-4 border transition-all text-left cursor-pointer ${
                    isActive
                      ? "bg-gradient-to-br from-blue-500/15 to-cyan-500/10 border-blue-500/30 shadow-lg shadow-blue-500/10"
                      : "bg-white/[0.02] border-white/5 hover:bg-white/[0.04] hover:border-white/10"
                  }`}
                >
                  {isActive && (
                    <div className="absolute top-2 right-2">
                      <Badge className="h-4 px-1.5 text-[8px] bg-blue-500/20 text-blue-400 border-blue-500/30">ACTIVE</Badge>
                    </div>
                  )}
                  <div className="flex items-center gap-2 mb-3">
                    <StatusDot status={model.status} pulse />
                    <Icon className="h-4 w-4" style={{ color: model.color }} />
                    <span className="text-xs font-semibold text-foreground truncate">{model.name}</span>
                  </div>
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="text-muted-foreground/40">Benchmark</span>
                      <span className="font-bold" style={{ color: model.color }}>{model.benchmark}</span>
                    </div>
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="text-muted-foreground/40">Speed</span>
                      <span className="text-muted-foreground/60">{model.speed} t/s</span>
                    </div>
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="text-muted-foreground/40">Latency</span>
                      <span className="text-muted-foreground/60">{model.latency}ms</span>
                    </div>
                  </div>
                  <Progress value={model.benchmark} className="h-1 mt-3 bg-white/5" />
                </motion.button>
              );
            })}
          </div>

          {/* Multi-model comparison panel */}
          <AnimatePresence>
            {showComparison && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="mt-4 overflow-hidden"
              >
                <div className="rounded-xl bg-white/[0.02] border border-white/5 p-4">
                  <h4 className="text-sm font-semibold text-foreground mb-3">Multi-Model Comparison</h4>
                  <div className="flex flex-wrap gap-2 mb-3">
                    {models.filter((m) => m.status === "online").map((m) => {
                      const selected = comparisonModels.includes(m.id);
                      return (
                        <button
                          key={m.id}
                          onClick={() =>
                            setComparisonModels((prev) =>
                              selected ? prev.filter((x) => x !== m.id) : [...prev, m.id]
                            )
                          }
                          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                            selected
                              ? "bg-blue-500/20 text-blue-400 border border-blue-500/30"
                              : "bg-white/5 text-muted-foreground/60 border border-white/5 hover:bg-white/10"
                          }`}
                        >
                          {m.name}
                        </button>
                      );
                    })}
                  </div>
                  <Textarea
                    value={comparisonPrompt}
                    onChange={(e) => setComparisonPrompt(e.target.value)}
                    placeholder="Enter prompt to compare models..."
                    className="mb-3 bg-white/[0.02] border-white/10 text-sm min-h-[60px]"
                  />
                  <Button
                    size="sm"
                    className="bg-gradient-to-r from-blue-500 to-cyan-400 hover:from-blue-600 hover:to-cyan-500"
                    onClick={handleRunComparison}
                    disabled={comparisonLoading || comparisonModels.length < 2}
                  >
                    {comparisonLoading ? (
                      <RefreshCw className="h-4 w-4 mr-1 animate-spin" />
                    ) : (
                      <BarChart3 className="h-4 w-4 mr-1" />
                    )}
                    Run Comparison
                  </Button>

                  {comparisonLoading && (
                    <div className="mt-4 grid gap-3">
                      {comparisonModels.map((mId) => {
                        const model = models.find((m) => m.id === mId);
                        return (
                          <div key={mId} className="rounded-lg bg-white/[0.03] border border-white/5 p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <StatusDot status="loading" />
                              <span className="text-xs font-medium text-muted-foreground/60">{model?.name} is responding...</span>
                            </div>
                            <div className="flex gap-1">
                              {[0, 1, 2, 3, 4].map((i) => (
                                <div
                                  key={i}
                                  className="w-1 bg-blue-500/40 rounded-full animate-pulse"
                                  style={{
                                    height: `${8 + Math.random() * 16}px`,
                                    animationDelay: `${i * 0.1}s`,
                                  }}
                                />
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {Object.keys(comparisonResults).length > 0 && (
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      {Object.entries(comparisonResults).map(([mId, result]) => {
                        const model = models.find((m) => m.id === mId);
                        return (
                          <div key={mId} className="rounded-lg bg-white/[0.03] border border-white/5 p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <div className="h-2 w-2 rounded-full" style={{ backgroundColor: model?.color }} />
                              <span className="text-xs font-semibold text-foreground">{model?.name}</span>
                              <Badge className="h-4 px-1.5 text-[9px] bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                                {model?.benchmark}
                              </Badge>
                            </div>
                            <p className="text-xs text-muted-foreground/70 whitespace-pre-wrap">{result}</p>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>

        {/* ============================================================
            MIDDLE ROW: Autonomous Ops + Self-Upgrade
            ============================================================ */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* SECTION 2: AUTONOMOUS OPERATIONS */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 }}
            className="glass-glow rounded-2xl p-5"
          >
            <SectionHeader
              icon={Target}
              title="Autonomous Operations"
              badge={`${runningGoals} Active`}
              right={
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground/50">Autonomous</span>
                  <Switch
                    checked={autonomousMode}
                    onCheckedChange={setAutonomousMode}
                  />
                  <span className={`text-xs font-semibold ${autonomousMode ? "text-emerald-400" : "text-muted-foreground/40"}`}>
                    {autonomousMode ? "ON" : "OFF"}
                  </span>
                </div>
              }
            />

            <ScrollArea className="max-h-[360px] pr-2 custom-scrollbar">
              <div className="space-y-3">
                {goals.map((goal, idx) => (
                  <motion.div
                    key={goal.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.05 * idx }}
                    className="rounded-xl bg-white/[0.02] border border-white/5 p-4"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <StatusDot
                            status={goal.status === "running" ? "online" : goal.status === "completed" ? "loading" : "offline"}
                          />
                          <span className="text-sm font-semibold text-foreground">{goal.name}</span>
                        </div>
                        <div className="mt-1 flex items-center gap-3 text-[10px] text-muted-foreground/40">
                          <span>Step {Math.ceil((goal.progress / 100) * goal.totalSteps)}/{goal.totalSteps}</span>
                          <span>ETA: {goal.eta}</span>
                          <span>{goal.model}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        {goal.status === "running" && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-muted-foreground/40 hover:text-amber-400"
                            onClick={() => handleToggleGoal(goal.id)}
                          >
                            <Pause className="h-3.5 w-3.5" />
                          </Button>
                        )}
                        {goal.status === "paused" && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-muted-foreground/40 hover:text-emerald-400"
                            onClick={() => handleToggleGoal(goal.id)}
                          >
                            <Play className="h-3.5 w-3.5" />
                          </Button>
                        )}
                        {goal.status === "running" && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-muted-foreground/40 hover:text-red-400"
                            onClick={() => handleAbortGoal(goal.id)}
                          >
                            <Square className="h-3.5 w-3.5" />
                          </Button>
                        )}
                        {goal.status === "completed" && (
                          <CheckCircle className="h-4 w-4 text-emerald-400" />
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <Progress value={goal.progress} className="flex-1 h-1.5 bg-white/5" />
                      <span className="text-xs font-bold w-10 text-right" style={{
                        color: goal.progress >= 100 ? "#10b981" : goal.progress > 50 ? "#3b82f6" : "#f59e0b"
                      }}>
                        {goal.progress}%
                      </span>
                    </div>
                    <div className="mt-1 text-[10px] text-muted-foreground/30">{goal.step}</div>
                  </motion.div>
                ))}
              </div>
            </ScrollArea>

            {/* Execution timeline */}
            <div className="mt-4 pt-4 border-t border-white/5">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-muted-foreground/40">Execution Timeline</span>
                <span className="text-xs text-muted-foreground/30">Last 24h</span>
              </div>
              <div className="flex items-end gap-1 h-12">
                {[35, 42, 28, 55, 67, 45, 38, 72, 85, 62, 48, 33, 58, 75, 90, 68, 52, 40, 30, 55, 70, 82, 65, 48].map((h, i) => (
                  <div
                    key={i}
                    className="flex-1 rounded-sm bg-gradient-to-t from-blue-500/30 to-blue-500/10 hover:from-blue-500/50 hover:to-blue-500/20 transition-all cursor-pointer"
                    style={{ height: `${h}%` }}
                    title={`${h}% load`}
                  />
                ))}
              </div>
            </div>
          </motion.div>

          {/* SECTION 3: SELF-UPGRADE STATUS */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.3 }}
            className="glass-glow rounded-2xl p-5"
          >
            <SectionHeader
              icon={RefreshCw}
              title="Self-Upgrade Status"
              right={
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground/50">Auto-Upgrade</span>
                  <Switch checked={autoUpgrade} onCheckedChange={setAutoUpgrade} />
                </div>
              }
            />

            {/* Version display */}
            <div className="flex items-center justify-between mb-4 px-4 py-3 rounded-xl bg-gradient-to-r from-blue-500/10 to-cyan-500/5 border border-blue-500/10">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500/20 to-cyan-500/20 border border-blue-500/10">
                  <Shield className="h-5 w-5 text-blue-400" />
                </div>
                <div>
                  <div className="text-xs text-muted-foreground/40">Current Version</div>
                  <div className="text-lg font-bold text-foreground">{upgrade.currentVersion}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {upgrade.hasUpdate && (
                  <>
                    <ArrowUpRight className="h-4 w-4 text-amber-400" />
                    <div className="text-right">
                      <div className="text-xs text-muted-foreground/40">Latest Available</div>
                      <div className="text-lg font-bold text-amber-400">{upgrade.latestVersion}</div>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Pending updates */}
            <div className="mb-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-muted-foreground/40">Pending Updates</span>
                <Badge className={`h-4 px-1.5 text-[9px] ${criticalPackages > 0 ? "bg-amber-500/20 text-amber-400 border-amber-500/30" : "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"}`}>
                  {upgrade.packages.length} packages ({criticalPackages} critical)
                </Badge>
              </div>
              <div className="space-y-1.5 max-h-[120px] overflow-y-auto custom-scrollbar">
                {upgrade.packages.map((pkg, i) => (
                  <div key={i} className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-white/[0.02]">
                    <div className="flex items-center gap-2">
                      {pkg.critical && <AlertTriangle className="h-3 w-3 text-amber-400" />}
                      <span className="text-xs text-foreground/80">{pkg.name}</span>
                    </div>
                    <div className="flex items-center gap-2 text-[10px]">
                      <span className="text-muted-foreground/40">{pkg.current}</span>
                      <ArrowUpRight className="h-3 w-3 text-muted-foreground/30" />
                      <span className="text-emerald-400 font-medium">{pkg.latest}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Last upgrade */}
            <div className="flex items-center gap-2 mb-3 text-xs text-muted-foreground/40">
              <Clock className="h-3.5 w-3.5" />
              <span>Last upgrade: {formatTimeAgo(upgrade.lastUpgrade)}</span>
            </div>

            {/* Upgrade button */}
            <div className="flex gap-2">
              <Button
                className="flex-1 bg-gradient-to-r from-blue-500 to-cyan-400 hover:from-blue-600 hover:to-cyan-500 text-sm"
                onClick={handleUpgrade}
                disabled={isUpgrading || !upgrade.hasUpdate}
              >
                {isUpgrading ? (
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Download className="h-4 w-4 mr-2" />
                )}
                {isUpgrading ? "Upgrading..." : upgrade.hasUpdate ? "Upgrade Now" : "Up to Date"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="bg-white/[0.03] border-white/10 hover:bg-white/5"
                onClick={() => setShowUpgradeHistory(true)}
              >
                <Clock className="h-4 w-4" />
              </Button>
            </div>

            {/* Upgrade progress bar if upgrading */}
            {isUpgrading && (
              <div className="mt-3">
                <Progress value={65} className="h-1 bg-white/5" />
                <span className="text-[10px] text-muted-foreground/40 mt-1 block">Downloading and installing packages...</span>
              </div>
            )}
          </motion.div>
        </div>

        {/* ============================================================
            BOTTOM ROW: Knowledge Feed + System Health
            ============================================================ */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* SECTION 4: GLOBAL KNOWLEDGE FEED */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="glass-glow rounded-2xl p-5"
          >
            <SectionHeader
              icon={Globe}
              title="Global Knowledge Feed"
              right={
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs bg-white/[0.03] border-white/10 hover:bg-white/5"
                  onClick={() => handleQuickAction("Knowledge Acquisition")}
                >
                  <Download className="h-3.5 w-3.5 mr-1" />
                  Acquire Knowledge
                </Button>
              }
            />

            <Tabs defaultValue="trending" className="w-full">
              <TabsList className="bg-white/[0.03] border border-white/5">
                <TabsTrigger value="trending" className="text-xs">
                  <TrendingUp className="h-3.5 w-3.5 mr-1" />
                  Trending
                </TabsTrigger>
                <TabsTrigger value="news" className="text-xs">
                  <Bell className="h-3.5 w-3.5 mr-1" />
                  Alerts
                </TabsTrigger>
                <TabsTrigger value="searches" className="text-xs">
                  <Search className="h-3.5 w-3.5 mr-1" />
                  Searches
                </TabsTrigger>
              </TabsList>

              <TabsContent value="trending" className="mt-3">
                <div className="space-y-2">
                  {knowledge.trending.map((item, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between px-3 py-2.5 rounded-lg bg-white/[0.02] border border-white/5 hover:bg-white/[0.04] transition-all cursor-pointer group"
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-bold text-muted-foreground/30 w-5">{i + 1}</span>
                        <div>
                          <div className="text-sm text-foreground/80 group-hover:text-blue-400 transition-colors">{item.topic}</div>
                          <div className="text-[10px] text-muted-foreground/30">{item.category}</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <TrendingUp className="h-3 w-3 text-emerald-400" />
                        <span className="text-xs font-semibold text-emerald-400">{item.score}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </TabsContent>

              <TabsContent value="news" className="mt-3">
                <div className="space-y-2">
                  {knowledge.breakingNews.map((news, i) => (
                    <div
                      key={i}
                      className={`flex items-start gap-3 px-3 py-2.5 rounded-lg border transition-all ${
                        news.urgency === "high"
                          ? "bg-red-500/5 border-red-500/10"
                          : news.urgency === "medium"
                          ? "bg-amber-500/5 border-amber-500/10"
                          : "bg-white/[0.02] border-white/5"
                      }`}
                    >
                      <AlertCircle className={`h-4 w-4 mt-0.5 flex-shrink-0 ${
                        news.urgency === "high" ? "text-red-400" : news.urgency === "medium" ? "text-amber-400" : "text-blue-400"
                      }`} />
                      <div className="flex-1">
                        <div className="text-sm text-foreground/80">{news.title}</div>
                        <div className="flex items-center gap-2 mt-1 text-[10px] text-muted-foreground/40">
                          <span>{news.source}</span>
                          <span>{news.time}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </TabsContent>

              <TabsContent value="searches" className="mt-3">
                <div className="space-y-2">
                  {knowledge.recentSearches.map((search, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between px-3 py-2.5 rounded-lg bg-white/[0.02] border border-white/5 hover:bg-white/[0.04] transition-all cursor-pointer"
                    >
                      <div className="flex items-center gap-2">
                        <Search className="h-3.5 w-3.5 text-muted-foreground/30" />
                        <span className="text-sm text-foreground/70">{search.query}</span>
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-muted-foreground/40">
                        <span>{search.results} results</span>
                        <span>{search.time}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </TabsContent>
            </Tabs>

            {/* Knowledge stats */}
            <div className="mt-4 pt-4 border-t border-white/5 grid grid-cols-4 gap-3">
              {[
                { label: "Entries", value: knowledge.stats.entries.toLocaleString(), icon: Database },
                { label: "Sources", value: knowledge.stats.sources.toString(), icon: Globe },
                { label: "Freshness", value: `${knowledge.stats.freshness}%`, icon: RefreshCw },
                { label: "Indexed", value: knowledge.stats.lastIndexed, icon: Clock },
              ].map((stat, i) => {
                const Icon = stat.icon;
                return (
                  <div key={i} className="text-center">
                    <Icon className="h-4 w-4 mx-auto mb-1 text-muted-foreground/30" />
                    <div className="text-sm font-bold text-foreground">{stat.value}</div>
                    <div className="text-[9px] text-muted-foreground/30 uppercase tracking-wider">{stat.label}</div>
                  </div>
                );
              })}
            </div>
          </motion.div>

          {/* SECTION 5: SYSTEM HEALTH */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
            className="glass-glow rounded-2xl p-5"
          >
            <SectionHeader
              icon={Activity}
              title="System Health"
              badge="LIVE"
            />

            {/* Gauges row */}
            <div className="flex items-center justify-around mb-4">
              <RadialGauge value={Math.round(health.cpu)} label="CPU" color="#3b82f6" sublabel={`${(health.cpu * 0.08).toFixed(1)} GHz`} />
              <RadialGauge value={Math.round(health.memory)} label="Memory" color="#8b5cf6" sublabel={`${Math.round(health.memory * 0.32)} GB`} />
              <RadialGauge value={Math.round(health.disk)} label="Disk" color="#10a37f" sublabel={`${(health.disk * 5.12).toFixed(0)} GB`} />
              <RadialGauge value={Math.round(health.recoveryRate)} label="Recovery" color="#f59e0b" sublabel={`${health.selfHealingActions} actions`} />
            </div>

            {/* Network stats */}
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-white/[0.02] border border-white/5">
                <Upload className="h-4 w-4 text-blue-400" />
                <div>
                  <div className="text-[10px] text-muted-foreground/40">Upload</div>
                  <div className="text-sm font-bold text-foreground">{health.network.up.toFixed(1)} MB/s</div>
                </div>
              </div>
              <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-white/[0.02] border border-white/5">
                <Download className="h-4 w-4 text-emerald-400" />
                <div>
                  <div className="text-[10px] text-muted-foreground/40">Download</div>
                  <div className="text-sm font-bold text-foreground">{health.network.down.toFixed(1)} MB/s</div>
                </div>
              </div>
            </div>

            {/* Resource history chart */}
            <div className="mb-4">
              <div className="text-xs text-muted-foreground/40 mb-2">Resource History (24h)</div>
              <ResponsiveContainer width="100%" height={120}>
                <AreaChart data={health.history}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="time" stroke="rgba(255,255,255,0.2)" tick={{ fontSize: 10 }} />
                  <YAxis stroke="rgba(255,255,255,0.2)" tick={{ fontSize: 10 }} domain={[0, 100]} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "rgba(15, 18, 24, 0.95)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: "8px",
                      fontSize: "11px",
                    }}
                  />
                  <Area type="monotone" dataKey="cpu" stroke="#3b82f6" fill="rgba(59,130,246,0.15)" strokeWidth={2} name="CPU %" />
                  <Area type="monotone" dataKey="memory" stroke="#8b5cf6" fill="rgba(139,92,246,0.15)" strokeWidth={2} name="Memory %" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* System stats */}
            <div className="grid grid-cols-3 gap-3">
              <div className="text-center px-3 py-2.5 rounded-xl bg-white/[0.02] border border-white/5">
                <Server className="h-4 w-4 mx-auto mb-1 text-muted-foreground/30" />
                <div className="text-sm font-bold text-foreground">{health.processes}</div>
                <div className="text-[9px] text-muted-foreground/30 uppercase">Processes</div>
              </div>
              <div className="text-center px-3 py-2.5 rounded-xl bg-white/[0.02] border border-white/5">
                <Timer className="h-4 w-4 mx-auto mb-1 text-muted-foreground/30" />
                <div className="text-sm font-bold text-foreground">{formatUptime(health.uptime)}</div>
                <div className="text-[9px] text-muted-foreground/30 uppercase">Uptime</div>
              </div>
              <div className="text-center px-3 py-2.5 rounded-xl bg-white/[0.02] border border-white/5">
                <Shield className="h-4 w-4 mx-auto mb-1 text-muted-foreground/30" />
                <div className="text-sm font-bold text-emerald-400">{health.recoveryRate}%</div>
                <div className="text-[9px] text-muted-foreground/30 uppercase">Recovery</div>
              </div>
            </div>
          </motion.div>
        </div>

        {/* ============================================================
            SECTION 6: QUICK ACTIONS BAR
            ============================================================ */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
          className="glass-glow rounded-2xl p-5"
        >
          <div className="flex items-center gap-2 mb-4">
            <Zap className="h-4 w-4 text-amber-400" />
            <h3 className="text-sm font-semibold text-foreground">Quick Actions</h3>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {[
              { icon: Brain, label: "Research & Report", color: "from-blue-500 to-cyan-400", shadow: "shadow-blue-500/20" },
              { icon: Activity, label: "Monitor & Fix", color: "from-emerald-500 to-teal-400", shadow: "shadow-emerald-500/20" },
              { icon: RefreshCw, label: "Scan & Upgrade", color: "from-purple-500 to-pink-400", shadow: "shadow-purple-500/20" },
              { icon: BookOpen, label: "Learn & Master", color: "from-amber-500 to-orange-400", shadow: "shadow-amber-500/20" },
              { icon: Settings, label: "Full Maintenance", color: "from-rose-500 to-red-400", shadow: "shadow-rose-500/20" },
              { icon: Plus, label: "Custom Goal", color: "from-indigo-500 to-violet-400", shadow: "shadow-indigo-500/20", action: () => setShowCustomGoal(true) },
            ].map((action, i) => {
              const Icon = action.icon;
              return (
                <motion.button
                  key={i}
                  whileHover={{ scale: 1.03, y: -2 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={action.action || (() => handleQuickAction(action.label))}
                  className={`relative flex flex-col items-center gap-2.5 p-5 rounded-xl bg-gradient-to-br ${action.color} bg-opacity-10
                    border border-white/10 hover:border-white/20 transition-all cursor-pointer group overflow-hidden`}
                >
                  <div className={`absolute inset-0 bg-gradient-to-br ${action.color} opacity-0 group-hover:opacity-10 transition-opacity`} />
                  <div className={`flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br ${action.color} shadow-lg ${action.shadow} group-hover:scale-110 transition-transform`}>
                    <Icon className="h-5 w-5 text-white" />
                  </div>
                  <span className="text-xs font-semibold text-foreground/80 group-hover:text-white transition-colors text-center leading-tight">
                    {action.label}
                  </span>
                </motion.button>
              );
            })}
          </div>
        </motion.div>

        {/* ============================================================
            FOOTER STATUS BAR
            ============================================================ */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.7 }}
          className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 rounded-xl bg-white/[0.02] border border-white/5"
        >
          <div className="flex items-center gap-4 text-[10px] text-muted-foreground/40">
            <div className="flex items-center gap-1.5">
              <StatusDot status="online" pulse />
              <span>AI Engine: Connected</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Wifi className="h-3 w-3 text-emerald-400" />
              <span>Network: {health.network.down.toFixed(1)} MB/s</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Cpu className="h-3 w-3 text-blue-400" />
              <span>CPU: {Math.round(health.cpu)}%</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Database className="h-3 w-3 text-purple-400" />
              <span>Memory: {Math.round(health.memory)}%</span>
            </div>
          </div>
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground/30">
            <span>JARVIS OMEGA v3.3.0</span>
            <span>|</span>
            <span>Phase 4 — Conscious Operations</span>
            <span>|</span>
            <span>{new Date().toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}</span>
          </div>
        </motion.div>
      </div>

      {/* ============================================================
          DIALOGS
          ============================================================ */}

      {/* Custom Goal Dialog */}
      <Dialog open={showCustomGoal} onOpenChange={setShowCustomGoal}>
        <DialogContent className="bg-[hsl(222,47%,12%)] border-white/10 max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Target className="h-5 w-5 text-blue-400" />
              Execute Custom Goal
            </DialogTitle>
            <DialogDescription className="text-muted-foreground/60">
              Define a new autonomous goal for JARVIS to execute.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label htmlFor="goal-name" className="text-sm">Goal Name</Label>
              <Input
                id="goal-name"
                value={customGoalName}
                onChange={(e) => setCustomGoalName(e.target.value)}
                placeholder="e.g., Analyze competitor pricing"
                className="mt-1.5 bg-white/[0.03] border-white/10"
              />
            </div>
            <div>
              <Label htmlFor="goal-desc" className="text-sm">Description</Label>
              <Textarea
                id="goal-desc"
                value={customGoalDesc}
                onChange={(e) => setCustomGoalDesc(e.target.value)}
                placeholder="Describe what JARVIS should accomplish..."
                className="mt-1.5 bg-white/[0.03] border-white/10 min-h-[80px]"
              />
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground/40">
              <Info className="h-3.5 w-3.5" />
              <span>Will be executed by: <span className="text-blue-400 font-medium">{activeModel?.name || "Auto-routed"}</span></span>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCustomGoal(false)} className="bg-white/[0.03] border-white/10">
              Cancel
            </Button>
            <Button
              className="bg-gradient-to-r from-blue-500 to-cyan-400 hover:from-blue-600 hover:to-cyan-500"
              onClick={handleAddCustomGoal}
              disabled={!customGoalName.trim()}
            >
              <PlayCircle className="h-4 w-4 mr-1.5" />
              Start Goal
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Upgrade History Dialog */}
      <Dialog open={showUpgradeHistory} onOpenChange={setShowUpgradeHistory}>
        <DialogContent className="bg-[hsl(222,47%,12%)] border-white/10 max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5 text-blue-400" />
              Upgrade History
            </DialogTitle>
            <DialogDescription className="text-muted-foreground/60">
              View past upgrades and rollback if needed.
            </DialogDescription>
          </DialogHeader>
          <ScrollArea className="max-h-[350px] pr-2 custom-scrollbar">
            <div className="space-y-3">
              {upgrade.history.map((entry, i) => (
                <div key={i} className="rounded-xl bg-white/[0.02] border border-white/5 p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Badge className="h-5 px-2 text-xs bg-blue-500/20 text-blue-400 border-blue-500/30">
                        v{entry.version}
                      </Badge>
                      <span className="text-xs text-muted-foreground/40">{entry.date}</span>
                    </div>
                    {i > 0 && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-6 text-[10px] bg-white/[0.03] border-white/10 hover:bg-white/5"
                        onClick={() => {
                          toast.info(`Rolling back to v${entry.version}...`);
                          setShowUpgradeHistory(false);
                        }}
                      >
                        <RotateCcw className="h-3 w-3 mr-1" />
                        Rollback
                      </Button>
                    )}
                  </div>
                  <ul className="space-y-1">
                    {entry.changes.map((change, j) => (
                      <li key={j} className="flex items-center gap-2 text-xs text-muted-foreground/60">
                        <CheckCircle className="h-3 w-3 text-emerald-400" />
                        {change}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </div>
  );
}
