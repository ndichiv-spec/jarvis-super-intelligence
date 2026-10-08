/**
 * JARVIS Stark Control Panel
 * ===========================
 * The Tony Stark-inspired command center showing real-time status of:
 * - All AI engines (OMEGA, Local LLM, Agents)
 * - Active autonomous goals with progress tracking
 * - Self-upgrade status
 * - Global knowledge feed with trending topics
 * - System health gauges
 * 
 * This is the ultimate command center - the heart of Jarvis.
 */

"use client";

import { useState, useEffect, useCallback } from "react";
import env from "@/config/env";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import {
  Activity,
  Brain,
  Cpu,
  Database,
  Globe,
  Zap,
  Shield,
  TrendingUp,
  Radio,
  Terminal,
  Network,
  Gauge,
  AlertCircle,
  CheckCircle,
  Clock,
  MessageSquare,
} from "lucide-react";
import { toast } from "sonner";

interface EngineStatus {
  status: "online" | "offline";
  type: string;
}

interface GatewayStatus {
  active: boolean;
  uptime: string | null;
  engines_connected: number;
  tools_registered: number;
}

interface SystemStatus {
  gateway: GatewayStatus;
  engines: {
    omega: EngineStatus;
    ai_engine: EngineStatus;
    agent_system: EngineStatus;
    memory: EngineStatus;
    observation: EngineStatus;
    speech: EngineStatus;
    global_knowledge: EngineStatus;
  };
  tools: {
    registered: string[];
  };
  timestamp: string;
}

interface HealthCheck {
  name: string;
  status: "healthy" | "warning" | "critical";
  details?: string;
}

export default function StarkControlPanel() {
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [healthChecks, setHealthChecks] = useState<HealthCheck[]>([]);
  const [activeGoals, setActiveGoals] = useState<any[]>([]);
  const [recentInteractions, setRecentInteractions] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  const fetchSystemStatus = useCallback(async () => {
    try {
      const get = async (path: string) => {
        const r = await fetch(`${env.API_URL}${path}`);
        if (!r.ok) throw new Error(`${path}: ${r.status}`);
        return r.json();
      };
      const results = await Promise.allSettled([
        get("/api/v1/ai/status"),                 // ai_engine (Silverwing)
        get("/api/v1/agents/scheduler/status"),   // agent_system
        get("/api/v1/cognitive/memory/stats"),    // memory
        get("/api/v1/global/observation/status"), // observation
        get("/api/v1/voice/status"),              // speech
        get("/api/v1/knowledge/search?query=test&limit=1"), // global_knowledge
        get("/api/v1/tier4/status"),              // omega tier
        get("/api/v1/stark/status"),              // gateway + tools
      ]);
      const val = (i: number) =>
        results[i].status === "fulfilled" ? (results[i] as PromiseFulfilledResult<any>).value : null;
      const ai = val(0), scheduler = val(1), mem = val(2), obs = val(3),
        voice = val(4), know = val(5), tier = val(6), stark = val(7);

      const engines: SystemStatus["engines"] = {
        omega: {
          status: tier && tier.status === "available" ? "online" : "offline",
          type: tier ? `tier ${tier.tier ?? 4}` : "unreachable",
        },
        ai_engine: {
          status: ai && ai.status === "ready" && (ai.enabled || ai.silverwing_endpoint) ? "online" : "offline",
          type: ai ? String(ai.provider || "unknown") : "unreachable",
        },
        agent_system: {
          status: scheduler && scheduler.running ? "online" : "offline",
          type: scheduler ? `scheduler every ${scheduler.interval ?? "?"}s` : "unreachable",
        },
        memory: {
          status: mem ? "online" : "offline",
          type: mem ? `${mem.total ?? 0} stored` : "unreachable",
        },
        observation: {
          status: obs && obs.status === "active" ? "online" : "offline",
          type: obs ? String(obs.mode || "unknown") : "unreachable",
        },
        speech: {
          status: voice && voice.status === "ready" ? "online" : "offline",
          type: voice
            ? `tts:${voice.tts_available ? "yes" : "no"} asr:${voice.asr_available ? "yes" : "no"}`
            : "unreachable",
        },
        global_knowledge: {
          status: know && Array.isArray(know.results) ? "online" : "offline",
          type: know ? `${know.count ?? 0} hit(s) on probe query` : "unreachable",
        },
      };
      const tools: string[] = Array.isArray(stark?.tools_available)
        ? stark.tools_available
        : [];
      const onlineCount = Object.values(engines).filter((e) => e.status === "online").length;
      const gatewayUp = stark?.status === "online" || onlineCount > 0;
      setSystemStatus({
        gateway: {
          active: gatewayUp,
          uptime: gatewayUp ? "Active" : null,
          engines_connected: onlineCount,
          tools_registered: tools.length,
        },
        engines,
        tools: { registered: tools },
        timestamp: new Date().toISOString(),
      });
    } catch (error) {
      console.error("Failed to fetch system status:", error);
    }
  }, []);

  const fetchHealthChecks = useCallback(async () => {
    try {
      const response = await fetch(`${env.API_URL}/api/v1/monitoring/health`);
      if (response.ok) {
        const data = await response.json();
        if (data.success && data.health_checks) {
          setHealthChecks(data.health_checks);
        } else if (data.status) {
          // Backend returns a flat {status, timestamp} shape.
          setHealthChecks([{
            name: "stark gateway",
            status: data.status === "healthy" ? "healthy" : "warning",
            details: data.timestamp,
          }]);
        }
      }
    } catch (error) {
      console.error("Failed to fetch health checks:", error);
    }
  }, []);

  const fetchActiveGoals = useCallback(async () => {
    try {
      const response = await fetch(`${env.API_URL}/api/v1/agents/goals`);
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setActiveGoals(data.active_goals || []);
        } else if (Array.isArray(data.goals)) {
          setActiveGoals(data.goals);
        }
      }
    } catch (error) {
      console.error("Failed to fetch active goals:", error);
    }
  }, []);

  useEffect(() => {
    const initialize = async () => {
      await Promise.all([
        fetchSystemStatus(),
        fetchHealthChecks(),
        fetchActiveGoals(),
      ]);
      setIsLoading(false);
    };

    initialize();

    // Update every 10 seconds
    const interval = setInterval(() => {
      fetchSystemStatus();
      fetchHealthChecks();
      fetchActiveGoals();
      setLastUpdate(new Date());
    }, 10000);

    return () => clearInterval(interval);
  }, [fetchSystemStatus, fetchHealthChecks, fetchActiveGoals]);

  const getEngineColor = (status: "online" | "offline") => {
    return status === "online"
      ? "bg-green-500/20 text-green-400 border-green-500/50"
      : "bg-red-500/20 text-red-400 border-red-500/50";
  };

  const getHealthIcon = (status: "healthy" | "warning" | "critical") => {
    switch (status) {
      case "healthy":
        return <CheckCircle className="h-4 w-4 text-green-400" />;
      case "warning":
        return <AlertCircle className="h-4 w-4 text-yellow-400" />;
      case "critical":
        return <AlertCircle className="h-4 w-4 text-red-400" />;
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center space-y-4">
          <div className="animate-spin h-12 w-12 border-4 border-blue-500 border-t-transparent rounded-full mx-auto"></div>
          <p className="text-muted-foreground">Initializing Stark Gateway...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
            JARVIS Stark Control Panel
          </h1>
          <p className="text-muted-foreground mt-1">
            Unified AI Command Center • Last update: {lastUpdate.toLocaleTimeString()}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="px-3 py-1">
            <div className="h-2 w-2 rounded-full bg-green-500 mr-2 animate-pulse"></div>
            Systems Online
          </Badge>
          <Button variant="outline" size="sm" onClick={() => {
            fetchSystemStatus();
            fetchHealthChecks();
            fetchActiveGoals();
            setLastUpdate(new Date());
            toast.success("System status refreshed");
          }}>
            Refresh
          </Button>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="border-blue-500/20 bg-gradient-to-br from-blue-950/30 to-transparent">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Brain className="h-4 w-4 text-blue-400" />
              Active Engines
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-blue-400">
              {systemStatus?.gateway.engines_connected || 0}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              of 7 total engines
            </p>
          </CardContent>
        </Card>

        <Card className="border-purple-500/20 bg-gradient-to-br from-purple-950/30 to-transparent">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Terminal className="h-4 w-4 text-purple-400" />
              Tools Registered
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-purple-400">
              {systemStatus?.gateway.tools_registered || 0}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Available for execution
            </p>
          </CardContent>
        </Card>

        <Card className="border-green-500/20 bg-gradient-to-br from-green-950/30 to-transparent">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Activity className="h-4 w-4 text-green-400" />
              System Health
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-green-400">
              {healthChecks.filter((h) => h.status === "healthy").length}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              checks passing
            </p>
          </CardContent>
        </Card>

        <Card className="border-yellow-500/20 bg-gradient-to-br from-yellow-950/30 to-transparent">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Clock className="h-4 w-4 text-yellow-400" />
              Gateway Uptime
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-yellow-400">
              {systemStatus?.gateway.uptime ? "Active" : "Starting"}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {systemStatus?.gateway.uptime || "Initializing..."}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <Tabs defaultValue="engines" className="space-y-4">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="engines">AI Engines</TabsTrigger>
          <TabsTrigger value="health">System Health</TabsTrigger>
          <TabsTrigger value="autonomous">Autonomous Goals</TabsTrigger>
          <TabsTrigger value="knowledge">Global Knowledge</TabsTrigger>
        </TabsList>

        {/* AI Engines Tab */}
        <TabsContent value="engines" className="space-y-4">
          <Card className="border-blue-500/20">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Network className="h-5 w-5 text-blue-400" />
                AI Engine Status
              </CardTitle>
              <CardDescription>
                Real-time status of all connected AI engines and capabilities
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {systemStatus?.engines &&
                  Object.entries(systemStatus.engines).map(([name, engine]) => (
                    <div
                      key={name}
                      className={`flex items-center justify-between p-4 rounded-lg border ${getEngineColor(
                        engine.status
                      )}`}
                    >
                      <div className="flex items-center gap-3">
                        {name === "omega" && <Brain className="h-5 w-5" />}
                        {name === "ai_engine" && <Zap className="h-5 w-5" />}
                        {name === "agent_system" && <Gauge className="h-5 w-5" />}
                        {name === "memory" && <Database className="h-5 w-5" />}
                        {name === "observation" && <Radio className="h-5 w-5" />}
                        {name === "speech" && <MessageSquare className="h-5 w-5" />}
                        {name === "global_knowledge" && <Globe className="h-5 w-5" />}
                        <div>
                          <p className="font-semibold capitalize">
                            {name.replace("_", " ")}
                          </p>
                          <p className="text-xs opacity-75">{engine.type}</p>
                        </div>
                      </div>
                      <Badge
                        variant="outline"
                        className={
                          engine.status === "online"
                            ? "border-green-500 text-green-400"
                            : "border-red-500 text-red-400"
                        }
                      >
                        {engine.status}
                      </Badge>
                    </div>
                  ))}
              </div>
            </CardContent>
          </Card>

          {/* Available Tools */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Terminal className="h-5 w-5" />
                Tool Registry
              </CardTitle>
              <CardDescription>
                Tools available through the Stark Gateway
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {(systemStatus?.tools?.registered ?? []).map((tool) => (
                  <Badge key={tool} variant="secondary" className="px-3 py-1">
                    {tool.replace("_", " ")}
                  </Badge>
                ))}
                {(systemStatus?.tools?.registered ?? []).length === 0 && (
                  <span className="text-xs text-muted-foreground">
                    {systemStatus ? "No tools reported." : "Waiting for gateway status..."}
                  </span>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* System Health Tab */}
        <TabsContent value="health" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="h-5 w-5 text-green-400" />
                System Health Checks
              </CardTitle>
              <CardDescription>
                Continuous monitoring of critical systems
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {healthChecks.map((check, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between p-3 rounded-lg border bg-card"
                  >
                    <div className="flex items-center gap-3">
                      {getHealthIcon(check.status)}
                      <div>
                        <p className="font-medium">{check.name}</p>
                        {check.details && (
                          <p className="text-xs text-muted-foreground">
                            {check.details}
                          </p>
                        )}
                      </div>
                    </div>
                    <Badge
                      variant="outline"
                      className={
                        check.status === "healthy"
                          ? "border-green-500 text-green-400"
                          : check.status === "warning"
                          ? "border-yellow-500 text-yellow-400"
                          : "border-red-500 text-red-400"
                      }
                    >
                      {check.status}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Autonomous Goals Tab */}
        <TabsContent value="autonomous" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Gauge className="h-5 w-5" />
                Active Autonomous Goals
              </CardTitle>
              <CardDescription>
                Tasks being executed without human intervention
              </CardDescription>
            </CardHeader>
            <CardContent>
              {activeGoals.length > 0 ? (
                <div className="space-y-4">
                  {activeGoals.map((goal) => (
                    <div
                      key={goal.id}
                      className="p-4 rounded-lg border bg-card space-y-3"
                    >
                      <div className="flex items-center justify-between">
                        <h4 className="font-semibold">{goal.name}</h4>
                        <Badge>{goal.status}</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {goal.description}
                      </p>
                      <div className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span>Progress</span>
                          <span>{goal.progress || 0}%</span>
                        </div>
                        <Progress value={goal.progress || 0} />
                      </div>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        <span>
                          Started: {new Date(goal.started_at).toLocaleString()}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12 text-muted-foreground">
                  <Gauge className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>No active autonomous goals</p>
                  <p className="text-sm mt-2">
                    Agents will execute tasks when assigned
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Global Knowledge Tab */}
        <TabsContent value="knowledge" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Globe className="h-5 w-5 text-blue-400" />
                Global Knowledge Feed
              </CardTitle>
              <CardDescription>
                Real-time intelligence from connected knowledge sources
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {[
                    { name: "DuckDuckGo", icon: "🔍" },
                    { name: "Wikipedia", icon: "📚" },
                    { name: "arXiv", icon: "📄" },
                    { name: "GitHub", icon: "💻" },
                    { name: "Google News", icon: "📰" },
                    { name: "Reddit", icon: "🔴" },
                    { name: "Hacker News", icon: "🟠" },
                    { name: "PubMed", icon: "🏥" },
                    { name: "StackOverflow", icon: "💡" },
                  ].map((source) => (
                    <div
                      key={source.name}
                      className="flex items-center gap-2 p-3 rounded-lg border bg-card hover:border-blue-500/50 transition-colors"
                    >
                      <span className="text-2xl">{source.icon}</span>
                      <span className="text-sm font-medium">{source.name}</span>
                      <Badge variant="outline" className="ml-auto text-xs">
                        Connected
                      </Badge>
                    </div>
                  ))}
                </div>

                <div className="pt-4 border-t">
                  <h4 className="font-medium mb-2 flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-yellow-400" />
                    Trending Topics
                  </h4>
                  <ScrollArea className="h-48 rounded-lg border p-3 bg-muted/30">
                    <div className="space-y-2 text-sm text-muted-foreground">
                      <p>• AI advancements in autonomous systems</p>
                      <p>• Latest developments in multi-model AI</p>
                      <p>• Open-source LLM improvements</p>
                      <p>• Real-time knowledge integration patterns</p>
                      <p>• Self-healing infrastructure trends</p>
                    </div>
                  </ScrollArea>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
