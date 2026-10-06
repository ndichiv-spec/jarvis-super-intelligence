"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  ArrowUpCircle, CheckCircle, XCircle, AlertTriangle, RefreshCw,
  Download, Shield, Zap, Package, Cpu, Brain, Globe,
  Activity, Clock, AlertCircle, TrendingUp, Info, Play,
  Pause, RotateCcw, HardDrive, MemoryStick, Server
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import { format } from "date-fns";

interface UpgradeCandidate {
  name: string;
  current_version: string;
  latest_version: string;
  severity: "critical" | "major" | "minor" | "patch";
  description?: string;
  released_at?: string;
  breaking_changes?: boolean;
  changelog?: string[];
}

interface ModelBenchmark {
  model_name: string;
  avg_latency_ms: number;
  tokens_per_second: number;
  accuracy_score: number;
  memory_usage_mb: number;
}

interface UpgradeHistory {
  id: string;
  package_name: string;
  old_version: string;
  new_version: string;
  status: "success" | "failed" | "rolled_back";
  started_at: string;
  completed_at?: string;
  duration_ms?: number;
  error?: string;
}

interface SystemStatus {
  jarvis_version: string;
  python_version: string;
  ollama_models: number;
  total_packages: number;
  outdated_packages: number;
  last_upgrade_check: string;
  disk_usage: {
    total_gb: number;
    used_gb: number;
    percent: number;
  };
  memory_usage: {
    total_mb: number;
    used_mb: number;
    percent: number;
  };
}

const SEVERITY_CONFIG = {
  critical: {
    color: "bg-red-500/20 text-red-400 border-red-500/30",
    icon: AlertTriangle,
    label: "Critical",
  },
  major: {
    color: "bg-orange-500/20 text-orange-400 border-orange-500/30",
    icon: AlertCircle,
    label: "Major",
  },
  minor: {
    color: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    icon: ArrowUpCircle,
    label: "Minor",
  },
  patch: {
    color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    icon: CheckCircle,
    label: "Patch",
  },
};

export default function UpgradePage() {
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("packages");
  const [upgrades, setUpgrades] = useState<UpgradeCandidate[]>([]);
  const [history, setHistory] = useState<UpgradeHistory[]>([]);
  const [benchmarks, setBenchmarks] = useState<ModelBenchmark[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [isUpgrading, setIsUpgrading] = useState(false);
  const [upgradeProgress, setUpgradeProgress] = useState(0);

  useEffect(() => {
    loadData();
    // Poll for updates every 30 seconds
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      setIsLoading(true);
      // In a real implementation, these would call the actual API endpoints
      // const status = await jarvisAPI.getUpgradeStatus();
      // const candidates = await jarvisAPI.checkUpgrades();
      
      // Mock data for now - replace with actual API calls
      setSystemStatus({
        jarvis_version: "3.0.0",
        python_version: "3.11.4",
        ollama_models: 3,
        total_packages: 127,
        outdated_packages: 8,
        last_upgrade_check: new Date().toISOString(),
        disk_usage: {
          total_gb: 512,
          used_gb: 287,
          percent: 56,
        },
        memory_usage: {
          total_mb: 16384,
          used_mb: 8942,
          percent: 54,
        },
      });

      setUpgrades([
        {
          name: "transformers",
          current_version: "4.35.2",
          latest_version: "4.38.1",
          severity: "minor",
          description: "Hugging Face Transformers library",
          changelog: ["New model support", "Performance improvements", "Bug fixes"],
        },
        {
          name: "ollama",
          current_version: "0.1.25",
          latest_version: "0.1.29",
          severity: "major",
          description: "Ollama Python client",
          changelog: ["API improvements", "New features", "Breaking changes in auth"],
          breaking_changes: true,
        },
        {
          name: "langchain",
          current_version: "0.0.345",
          latest_version: "0.1.5",
          severity: "critical",
          description: "LangChain framework",
          changelog: ["Major refactoring", "New architecture", "Performance boost"],
          breaking_changes: true,
        },
      ]);

      setHistory([
        {
          id: "1",
          package_name: "pydantic",
          old_version: "2.4.2",
          new_version: "2.5.3",
          status: "success",
          started_at: new Date(Date.now() - 86400000 * 2).toISOString(),
          completed_at: new Date(Date.now() - 86400000 * 2 + 120000).toISOString(),
          duration_ms: 120000,
        },
        {
          id: "2",
          package_name: "fastapi",
          old_version: "0.104.1",
          new_version: "0.109.0",
          status: "success",
          started_at: new Date(Date.now() - 86400000 * 5).toISOString(),
          completed_at: new Date(Date.now() - 86400000 * 5 + 180000).toISOString(),
          duration_ms: 180000,
        },
        {
          id: "3",
          package_name: "sqlalchemy",
          old_version: "2.0.22",
          new_version: "2.0.25",
          status: "rolled_back",
          started_at: new Date(Date.now() - 86400000 * 7).toISOString(),
          completed_at: new Date(Date.now() - 86400000 * 7 + 60000).toISOString(),
          duration_ms: 60000,
          error: "Compatibility issue detected, automatic rollback triggered",
        },
      ]);

      setBenchmarks([
        {
          model_name: "llama3:8b",
          avg_latency_ms: 245,
          tokens_per_second: 32,
          accuracy_score: 87.5,
          memory_usage_mb: 4096,
        },
        {
          model_name: "mistral:7b",
          avg_latency_ms: 198,
          tokens_per_second: 41,
          accuracy_score: 85.2,
          memory_usage_mb: 3584,
        },
        {
          model_name: "phi3:3.8b",
          avg_latency_ms: 142,
          tokens_per_second: 58,
          accuracy_score: 82.1,
          memory_usage_mb: 2048,
        },
      ]);
    } catch (error) {
      console.error("Failed to load upgrade data:", error);
      toast.error("Failed to load upgrade information");
    } finally {
      setIsLoading(false);
    }
  };

  const handleUpgrade = async (packageName: string) => {
    try {
      setIsUpgrading(true);
      setUpgradeProgress(0);
      toast.info(`Starting upgrade of ${packageName}...`);

      // Simulate upgrade progress
      const interval = setInterval(() => {
        setUpgradeProgress((prev) => {
          if (prev >= 100) {
            clearInterval(interval);
            return 100;
          }
          return prev + 10;
        });
      }, 500);

      // In real implementation:
      // await jarvisAPI.upgradePackage(packageName);

      setTimeout(() => {
        clearInterval(interval);
        setUpgradeProgress(100);
        toast.success(`${packageName} upgraded successfully`);
        setIsUpgrading(false);
        loadData();
      }, 5000);
    } catch (error: any) {
      toast.error(`Upgrade failed: ${error.message}`);
      setIsUpgrading(false);
      setUpgradeProgress(0);
    }
  };

  const handleUpgradeAll = async () => {
    try {
      setIsUpgrading(true);
      setUpgradeProgress(0);
      toast.info("Starting batch upgrade...");

      // In real implementation:
      // await jarvisAPI.upgradeBatch(upgrades.map(u => u.name));

      setTimeout(() => {
        toast.success("All packages upgraded successfully");
        setIsUpgrading(false);
        setUpgradeProgress(0);
        loadData();
      }, 10000);
    } catch (error: any) {
      toast.error(`Batch upgrade failed: ${error.message}`);
      setIsUpgrading(false);
    }
  };

  const getSeverityBadge = (severity: string) => {
    const config = SEVERITY_CONFIG[severity as keyof typeof SEVERITY_CONFIG];
    const Icon = config.icon;
    return (
      <Badge className={`${config.color} border`}>
        <Icon className="mr-1 h-3 w-3" />
        {config.label}
      </Badge>
    );
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "success":
        return <CheckCircle className="h-4 w-4 text-emerald-400" />;
      case "failed":
        return <XCircle className="h-4 w-4 text-red-400" />;
      case "rolled_back":
        return <RotateCcw className="h-4 w-4 text-amber-400" />;
      default:
        return <Clock className="h-4 w-4 text-gray-400" />;
    }
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
          <h1 className="text-3xl font-bold bg-gradient-to-r from-emerald-400 via-blue-400 to-purple-400 bg-clip-text text-transparent">
            Self-Upgrade Center
          </h1>
          <p className="text-muted-foreground/60 mt-1">
            Manage package updates, model upgrades, and system optimization
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={loadData}
            disabled={isLoading}
          >
            <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          {upgrades.length > 0 && (
            <Button
              onClick={handleUpgradeAll}
              disabled={isUpgrading}
              className="bg-gradient-to-r from-emerald-500 to-blue-500 hover:from-emerald-600 hover:to-blue-600"
            >
              <ArrowUpCircle className="mr-2 h-4 w-4" />
              Upgrade All ({upgrades.length})
            </Button>
          )}
        </div>
      </motion.div>

      {/* Upgrade Progress */}
      {isUpgrading && upgradeProgress > 0 && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <Card className="bg-blue-500/10 border-blue-500/20">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <RefreshCw className="h-5 w-5 text-blue-400 animate-spin" />
                <div className="flex-1">
                  <p className="text-sm font-medium">Upgrading packages...</p>
                  <Progress value={upgradeProgress} className="mt-2" />
                  <p className="text-xs text-muted-foreground/60 mt-1">{upgradeProgress}% complete</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* System Overview */}
      {systemStatus && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <Card className="bg-white/[0.02] border-white/5">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-2xl font-bold">{systemStatus.jarvis_version}</p>
                    <p className="text-xs text-muted-foreground/60">JARVIS Version</p>
                  </div>
                  <Shield className="h-8 w-8 text-emerald-400 opacity-50" />
                </div>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <Card className="bg-white/[0.02] border-white/5">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-2xl font-bold">{systemStatus.outdated_packages}</p>
                    <p className="text-xs text-muted-foreground/60">Updates Available</p>
                  </div>
                  <Package className="h-8 w-8 text-amber-400 opacity-50" />
                </div>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <Card className="bg-white/[0.02] border-white/5">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-2xl font-bold">{systemStatus.ollama_models}</p>
                    <p className="text-xs text-muted-foreground/60">AI Models</p>
                  </div>
                  <Brain className="h-8 w-8 text-purple-400 opacity-50" />
                </div>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
          >
            <Card className="bg-white/[0.02] border-white/5">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-2xl font-bold">{systemStatus.disk_usage.percent}%</p>
                    <p className="text-xs text-muted-foreground/60">Disk Usage</p>
                  </div>
                  <HardDrive className="h-8 w-8 text-blue-400 opacity-50" />
                </div>
              </CardContent>
            </Card>
          </motion.div>
        </div>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-white/[0.02] border-white/5">
          <TabsTrigger value="packages" className="text-sm">
            <Package className="mr-2 h-4 w-4" />
            Packages
          </TabsTrigger>
          <TabsTrigger value="models" className="text-sm">
            <Brain className="mr-2 h-4 w-4" />
            AI Models
          </TabsTrigger>
          <TabsTrigger value="history" className="text-sm">
            <Clock className="mr-2 h-4 w-4" />
            History
          </TabsTrigger>
          <TabsTrigger value="system" className="text-sm">
            <Server className="mr-2 h-4 w-4" />
            System
          </TabsTrigger>
        </TabsList>

        {/* Packages Tab */}
        <TabsContent value="packages" className="mt-4">
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader>
              <CardTitle>Available Updates</CardTitle>
              <CardDescription>
                {upgrades.length} packages have updates available
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex items-center justify-center py-12">
                  <RefreshCw className="h-8 w-8 animate-spin text-blue-400" />
                </div>
              ) : upgrades.length === 0 ? (
                <div className="text-center py-12">
                  <CheckCircle className="h-16 w-16 text-emerald-400 mx-auto mb-4" />
                  <h3 className="text-xl font-semibold mb-2">All packages up to date</h3>
                  <p className="text-sm text-muted-foreground/60">
                    Your system is running the latest versions of all packages
                  </p>
                </div>
              ) : (
                <ScrollArea className="h-[400px]">
                  <div className="space-y-3">
                    {upgrades.map((upgrade, i) => (
                      <motion.div
                        key={upgrade.name}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.05 }}
                      >
                        <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5 hover:border-blue-500/20 transition-all">
                          <div className="flex items-start justify-between mb-3">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <h4 className="font-semibold">{upgrade.name}</h4>
                                {getSeverityBadge(upgrade.severity)}
                                {upgrade.breaking_changes && (
                                  <Badge className="bg-red-500/20 text-red-400 border-red-500/30">
                                    <AlertTriangle className="mr-1 h-3 w-3" />
                                    Breaking Changes
                                  </Badge>
                                )}
                              </div>
                              <p className="text-sm text-muted-foreground/60">
                                {upgrade.description}
                              </p>
                            </div>
                            <Button
                              size="sm"
                              onClick={() => handleUpgrade(upgrade.name)}
                              disabled={isUpgrading}
                              className="ml-2"
                            >
                              <Download className="mr-1 h-4 w-4" />
                              Update
                            </Button>
                          </div>

                          <div className="flex items-center gap-4 text-xs text-muted-foreground/60 mb-2">
                            <div className="flex items-center gap-1">
                              <span>Current:</span>
                              <code className="px-1 py-0.5 bg-white/5 rounded">
                                {upgrade.current_version}
                              </code>
                            </div>
                            <span>→</span>
                            <div className="flex items-center gap-1">
                              <span>Latest:</span>
                              <code className="px-1 py-0.5 bg-blue-500/10 text-blue-400 rounded">
                                {upgrade.latest_version}
                              </code>
                            </div>
                          </div>

                          {upgrade.changelog && upgrade.changelog.length > 0 && (
                            <div className="mt-2">
                              <p className="text-xs font-semibold text-muted-foreground/60 mb-1">
                                Changelog:
                              </p>
                              <ul className="space-y-1">
                                {upgrade.changelog.map((change, idx) => (
                                  <li key={idx} className="text-xs text-muted-foreground/50 flex items-start gap-2">
                                    <span className="text-blue-400 mt-0.5">•</span>
                                    {change}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Models Tab */}
        <TabsContent value="models" className="mt-4">
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader>
              <CardTitle>AI Model Benchmarks</CardTitle>
              <CardDescription>
                Performance metrics for installed Ollama models
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[400px]">
                <div className="space-y-3">
                  {benchmarks.map((benchmark, i) => (
                    <motion.div
                      key={benchmark.model_name}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.05 }}
                    >
                      <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
                        <div className="flex items-start justify-between mb-3">
                          <div className="flex-1">
                            <h4 className="font-semibold mb-1">{benchmark.model_name}</h4>
                            <p className="text-sm text-muted-foreground/60">
                              Local LLM Model
                            </p>
                          </div>
                          <Badge className="bg-purple-500/20 text-purple-400 border-purple-500/30">
                            <Brain className="mr-1 h-3 w-3" />
                            Active
                          </Badge>
                        </div>

                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                          <div className="p-2 bg-white/[0.02] rounded">
                            <p className="text-xs text-muted-foreground/60">Latency</p>
                            <p className="text-lg font-bold">{benchmark.avg_latency_ms}ms</p>
                          </div>
                          <div className="p-2 bg-white/[0.02] rounded">
                            <p className="text-xs text-muted-foreground/60">Speed</p>
                            <p className="text-lg font-bold">{benchmark.tokens_per_second} t/s</p>
                          </div>
                          <div className="p-2 bg-white/[0.02] rounded">
                            <p className="text-xs text-muted-foreground/60">Accuracy</p>
                            <p className="text-lg font-bold">{benchmark.accuracy_score}%</p>
                          </div>
                          <div className="p-2 bg-white/[0.02] rounded">
                            <p className="text-xs text-muted-foreground/60">Memory</p>
                            <p className="text-lg font-bold">{(benchmark.memory_usage_mb / 1024).toFixed(1)} GB</p>
                          </div>
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        {/* History Tab */}
        <TabsContent value="history" className="mt-4">
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader>
              <CardTitle>Upgrade History</CardTitle>
              <CardDescription>
                Recent package upgrade history and outcomes
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[400px]">
                <div className="space-y-3">
                  {history.map((entry, i) => (
                    <motion.div
                      key={entry.id}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.05 }}
                    >
                      <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            {getStatusIcon(entry.status)}
                            <h4 className="font-semibold">{entry.package_name}</h4>
                          </div>
                          <Badge
                            className={
                              entry.status === "success"
                                ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                                : entry.status === "failed"
                                ? "bg-red-500/20 text-red-400 border-red-500/30"
                                : "bg-amber-500/20 text-amber-400 border-amber-500/30"
                            }
                          >
                            {entry.status}
                          </Badge>
                        </div>

                        <div className="flex items-center gap-4 text-xs text-muted-foreground/60 mb-2">
                          <div className="flex items-center gap-1">
                            <code className="px-1 py-0.5 bg-white/5 rounded">
                              {entry.old_version}
                            </code>
                            <span>→</span>
                            <code className="px-1 py-0.5 bg-white/5 rounded">
                              {entry.new_version}
                            </code>
                          </div>
                          {entry.duration_ms && (
                            <span className="flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {(entry.duration_ms / 1000).toFixed(0)}s
                            </span>
                          )}
                        </div>

                        <p className="text-xs text-muted-foreground/40">
                          {format(new Date(entry.started_at), "MMM d, yyyy HH:mm")}
                        </p>

                        {entry.error && (
                          <div className="mt-2 p-2 bg-red-500/10 border border-red-500/20 rounded text-xs text-red-400">
                            <AlertCircle className="inline mr-1 h-3 w-3" />
                            {entry.error}
                          </div>
                        )}
                      </div>
                    </motion.div>
                  ))}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        {/* System Tab */}
        <TabsContent value="system" className="mt-4">
          {systemStatus && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card className="bg-white/[0.02] border-white/5">
                <CardHeader>
                  <CardTitle>System Information</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground/60">JARVIS Version</span>
                      <span className="text-sm font-mono">{systemStatus.jarvis_version}</span>
                    </div>
                    <Separator />
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground/60">Python Version</span>
                      <span className="text-sm font-mono">{systemStatus.python_version}</span>
                    </div>
                    <Separator />
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground/60">Total Packages</span>
                      <span className="text-sm">{systemStatus.total_packages}</span>
                    </div>
                    <Separator />
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground/60">Outdated Packages</span>
                      <span className="text-sm text-amber-400">{systemStatus.outdated_packages}</span>
                    </div>
                    <Separator />
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground/60">Last Upgrade Check</span>
                      <span className="text-sm">
                        {format(new Date(systemStatus.last_upgrade_check), "MMM d, HH:mm")}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="bg-white/[0.02] border-white/5">
                <CardHeader>
                  <CardTitle>Resource Usage</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div>
                      <div className="flex justify-between mb-2">
                        <span className="text-sm text-muted-foreground/60">Disk Usage</span>
                        <span className="text-sm">
                          {systemStatus.disk_usage.used_gb} / {systemStatus.disk_usage.total_gb} GB
                        </span>
                      </div>
                      <Progress value={systemStatus.disk_usage.percent} />
                      <p className="text-xs text-muted-foreground/40 mt-1">
                        {systemStatus.disk_usage.percent}% used
                      </p>
                    </div>

                    <Separator />

                    <div>
                      <div className="flex justify-between mb-2">
                        <span className="text-sm text-muted-foreground/60">Memory Usage</span>
                        <span className="text-sm">
                          {(systemStatus.memory_usage.used_mb / 1024).toFixed(1)} /{" "}
                          {(systemStatus.memory_usage.total_mb / 1024).toFixed(1)} GB
                        </span>
                      </div>
                      <Progress value={systemStatus.memory_usage.percent} />
                      <p className="text-xs text-muted-foreground/40 mt-1">
                        {systemStatus.memory_usage.percent}% used
                      </p>
                    </div>

                    <Separator />

                    <div>
                      <div className="flex justify-between mb-2">
                        <span className="text-sm text-muted-foreground/60">AI Models Installed</span>
                        <span className="text-sm">{systemStatus.ollama_models}</span>
                      </div>
                      <div className="flex gap-2 mt-2">
                        <Badge className="bg-purple-500/20 text-purple-400 border-purple-500/30">
                          <Brain className="mr-1 h-3 w-3" />
                          Ollama
                        </Badge>
                        <Badge className="bg-blue-500/20 text-blue-400 border-blue-500/30">
                          <Globe className="mr-1 h-3 w-3" />
                          Cloud
                        </Badge>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
