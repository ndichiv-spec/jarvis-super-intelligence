"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Users, Bot, Code, Rocket, FileCode, CheckCircle,
  AlertCircle, Play, Plus, RefreshCw, Settings,
  GitBranch, Layers, Zap, Package, Eye, Terminal,
  Cloud, Container, Database, Shield, Globe
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { jarvisAPI } from "@/lib/api";
import { toast } from "sonner";

interface Agent {
  agent_id: string;
  agent_type: string;
  name: string;
  status: string;
  current_task?: string;
  capabilities: string[];
  tasks_completed: number;
  success_rate: number;
}

interface CollaborationTask {
  id: string;
  status: string;
  description: string;
  collaboration_pattern: string;
  agents_needed: string[];
  created_at: string;
}

interface GeneratedProject {
  project_id: string;
  name: string;
  status: string;
  code: string;
  files: Array<{ path: string; type?: string; size?: number }>;
}

const AGENT_TYPES = [
  { id: "researcher", name: "Researcher", icon: Globe, color: "text-blue-400", desc: "Web search & information gathering" },
  { id: "coder", name: "Coder", icon: Code, color: "text-purple-400", desc: "Code generation & debugging" },
  { id: "analyst", name: "Analyst", icon: Layers, color: "text-emerald-400", desc: "Data analysis & pattern recognition" },
  { id: "planner", name: "Planner", icon: GitBranch, color: "text-amber-400", desc: "Strategy & workflow planning" },
  { id: "reviewer", name: "Reviewer", icon: Eye, color: "text-pink-400", desc: "Code review & quality checks" },
  { id: "executor", name: "Executor", icon: Zap, color: "text-red-400", desc: "Task execution & automation" },
];

const COLLAB_PATTERNS = [
  { id: "sequential", name: "Sequential Pipeline", desc: "Agents work in sequence" },
  { id: "parallel", name: "Parallel Execution", desc: "Multiple agents simultaneously" },
  { id: "hierarchical", name: "Hierarchical Delegation", desc: "Manager delegates to workers" },
  { id: "democratic", name: "Democratic Consensus", desc: "Decision by voting" },
  { id: "debate", name: "Debate & Synthesis", desc: "Argue viewpoints, then synthesize" },
];

const PROJECT_TYPES = [
  { id: "web_frontend", name: "Web Frontend", icon: Globe },
  { id: "web_backend", name: "Web Backend", icon: Database },
  { id: "full_stack", name: "Full Stack", icon: Layers },
  { id: "api_service", name: "API Service", icon: Zap },
];

const FRAMEWORKS = [
  { id: "react", name: "React", type: "web_frontend" },
  { id: "next_js", name: "Next.js", type: "web_frontend" },
  { id: "fastapi", name: "FastAPI", type: "web_backend" },
  { id: "flask", name: "Flask", type: "web_backend" },
];

const DEPLOY_TARGETS = [
  { id: "vercel", name: "Vercel", icon: Cloud, color: "text-white" },
  { id: "docker", name: "Docker", icon: Container, color: "text-blue-400" },
  { id: "railway", name: "Railway", icon: Rocket, color: "text-pink-400" },
  { id: "aws", name: "AWS", icon: Cloud, color: "text-amber-400" },
];

interface ProjectSpec {
  name: string;
  project_type: string;
  framework: string;
  description: string;
  features: string[];
  database: string;
  authentication: boolean;
  testing: boolean;
  docker: boolean;
  deployment: string;
}

export default function AdvancedPage() {
  const [isLoading, setIsLoading] = useState(true);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tasks, setTasks] = useState<CollaborationTask[]>([]);
  const [activeTab, setActiveTab] = useState("agents");
  const [runtimeError, setRuntimeError] = useState<string | null>(null);

  // Code generation state
  const [projectSpec, setProjectSpec] = useState<ProjectSpec>({
    name: "",
    project_type: "web_backend",
    framework: "fastapi",
    description: "",
    features: [],
    database: "postgresql",
    authentication: true,
    testing: true,
    docker: true,
    deployment: "docker",
  });
  const [generatedProject, setGeneratedProject] = useState<GeneratedProject | null>(null);

  useEffect(() => {
    loadAgentData();
  }, []);

  const loadAgentData = async () => {
    setIsLoading(true);
    const [agentResult, taskResult] = await Promise.allSettled([
      jarvisAPI.getCollaborationAgents(),
      jarvisAPI.getCollaborationTasks(),
    ]);
    const failures: string[] = [];
    if (agentResult.status === "fulfilled") {
      setAgents(agentResult.value.agents || []);
    } else {
      setAgents([]);
      failures.push("Agent runtime state could not be loaded.");
    }
    if (taskResult.status === "fulfilled") {
      setTasks(taskResult.value.tasks || []);
    } else {
      setTasks([]);
      failures.push("Persisted collaboration tasks could not be loaded.");
    }
    setRuntimeError(failures.length ? failures.join(" ") : null);
    setIsLoading(false);
  };

  const createCollaborationTask = async () => {
    try {
      const description = prompt("Enter task description:");
      if (!description) return;

      const result = await jarvisAPI.createCollaborationTask(
        description,
        agents.map((agent) => agent.agent_type),
        "sequential",
      );
      if (!result?.id) throw new Error("The runtime did not return a persisted task identifier.");
      toast.success("Collaboration task saved to runtime.");
      await loadAgentData();
    } catch (error: any) {
      toast.error(`Failed to create task: ${error.message}`);
    }
  };

  const generateProject = async () => {
    if (!projectSpec.name.trim()) {
      toast.error("Project name is required");
      return;
    }

    try {
      const result = await jarvisAPI.generateProject({
        spec: projectSpec,
        description: projectSpec.description,
        language: projectSpec.framework,
      });
      if (typeof result.code !== "string" || !result.code.trim()) {
        throw new Error("The model returned no generated code.");
      }
      setGeneratedProject(result);
      toast.success("Model-generated code is ready to inspect; no files have been written.");
    } catch (error: any) {
      toast.error(`Generation failed: ${error.message}`);
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
          <h1 className="text-3xl font-bold bg-gradient-to-r from-cyan-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
            Advanced Systems
          </h1>
          <p className="text-muted-foreground/60 mt-1">
            Agent collaboration & intelligent code generation
          </p>
        </div>
        <Button onClick={loadAgentData} disabled={isLoading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </motion.div>

      {runtimeError && (
        <div role="alert" className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
          {runtimeError}
        </div>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-white/[0.02] border-white/5">
          <TabsTrigger value="agents" className="text-sm">
            <Users className="mr-2 h-4 w-4" />
            Agents
          </TabsTrigger>
          <TabsTrigger value="collaboration" className="text-sm">
            <GitBranch className="mr-2 h-4 w-4" />
            Collaboration
          </TabsTrigger>
          <TabsTrigger value="codegen" className="text-sm">
            <Code className="mr-2 h-4 w-4" />
            Code Generation
          </TabsTrigger>
          <TabsTrigger value="deploy" className="text-sm">
            <Rocket className="mr-2 h-4 w-4" />
            Deployment
          </TabsTrigger>
        </TabsList>

        {/* Agents Tab */}
        <TabsContent value="agents" className="mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {AGENT_TYPES.map((agentType, i) => {
              const Icon = agentType.icon;
              const agent = agents.find(a => a.agent_type === agentType.id);
              
              return (
                <motion.div
                  key={agentType.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.1 }}
                >
                  <Card className="bg-white/[0.02] border-white/5 hover:border-cyan-500/20 transition-all">
                    <CardHeader>
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-3">
                          <div className={`p-2 rounded-lg bg-white/[0.02]`}>
                            <Icon className={`h-6 w-6 ${agentType.color}`} />
                          </div>
                          <div>
                            <CardTitle className="text-lg">{agentType.name}</CardTitle>
                            <CardDescription>{agentType.desc}</CardDescription>
                          </div>
                        </div>
                        {agent && (
                          <Badge className={
                            agent.status === "idle"
                              ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                              : "bg-blue-500/20 text-blue-400 border-blue-500/30"
                          }>
                            {agent.status}
                          </Badge>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent>
                      {agent ? (
                        <div className="space-y-2">
                          <div className="flex justify-between text-sm">
                            <span className="text-muted-foreground/60">Tasks Completed</span>
                            <span className="font-medium">{agent.tasks_completed}</span>
                          </div>
                          <div className="flex justify-between text-sm">
                            <span className="text-muted-foreground/60">Success Rate</span>
                            <span className="font-medium">{(agent.success_rate * 100).toFixed(0)}%</span>
                          </div>
                          <Progress value={agent.success_rate * 100} className="h-1" />
                          <div className="flex gap-1 flex-wrap mt-2">
                            {agent.capabilities.map((cap, idx) => (
                              <Badge key={idx} variant="outline" className="text-xs bg-white/[0.02]">
                                {cap}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      ) : <div className="text-center py-4 text-muted-foreground/40 text-sm">
                        {isLoading ? "Loading runtime state…" : runtimeError ? "Agent state unavailable" : "No agent registered"}
                      </div>}
                    </CardContent>
                  </Card>
                </motion.div>
              );
            })}
          </div>
        </TabsContent>

        {/* Collaboration Tab */}
        <TabsContent value="collaboration" className="mt-4">
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Agent Collaboration Patterns</CardTitle>
                  <CardDescription>
                    5 different collaboration strategies for multi-agent tasks
                  </CardDescription>
                </div>
                <Button onClick={createCollaborationTask}>
                  <Plus className="mr-2 h-4 w-4" />
                  New Task
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {COLLAB_PATTERNS.map((pattern, i) => (
                  <motion.div
                    key={pattern.id}
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: i * 0.05 }}
                  >
                    <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5 hover:border-purple-500/20 transition-all">
                      <h4 className="font-semibold mb-1">{pattern.name}</h4>
                      <p className="text-sm text-muted-foreground/60 mb-3">{pattern.desc}</p>
                      <Badge className="bg-purple-500/20 text-purple-400 border-purple-500/30">
                        {pattern.id}
                      </Badge>
                    </div>
                  </motion.div>
                ))}
              </div>
              <Separator className="my-6" />
              <h3 className="mb-3 text-sm font-semibold">Persisted tasks</h3>
              {tasks.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  {isLoading ? "Loading tasks…" : "No collaboration tasks were returned by the runtime."}
                </p>
              ) : (
                <div className="space-y-2">
                  {tasks.map((task) => (
                    <div key={task.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/5 p-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{task.description}</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {task.collaboration_pattern} · {task.agents_needed.join(", ") || "No agents assigned"} · {task.created_at}
                        </p>
                      </div>
                      <Badge variant="outline">{task.status}</Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Code Generation Tab */}
        <TabsContent value="codegen" className="mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Project Spec Form */}
            <Card className="bg-white/[0.02] border-white/5">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileCode className="h-5 w-5 text-cyan-400" />
                  Project Specification
                </CardTitle>
                <CardDescription>
                  Define your project requirements for intelligent scaffolding
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <Label>Project Name</Label>
                    <Input
                      value={projectSpec.name}
                      onChange={(e) => setProjectSpec({...projectSpec, name: e.target.value})}
                      placeholder="my-awesome-project"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label>Project Type</Label>
                      <Select
                        value={projectSpec.project_type}
                        onValueChange={(val) => setProjectSpec({...projectSpec, project_type: val})}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {PROJECT_TYPES.map(pt => (
                            <SelectItem key={pt.id} value={pt.id}>{pt.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div>
                      <Label>Framework</Label>
                      <Select
                        value={projectSpec.framework}
                        onValueChange={(val) => setProjectSpec({...projectSpec, framework: val})}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {FRAMEWORKS.filter(f => f.type === projectSpec.project_type || projectSpec.project_type === "full_stack")
                            .map(fw => (
                              <SelectItem key={fw.id} value={fw.id}>{fw.name}</SelectItem>
                            ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div>
                    <Label>Description</Label>
                    <Textarea
                      value={projectSpec.description}
                      onChange={(e) => setProjectSpec({...projectSpec, description: e.target.value})}
                      placeholder="What does this project do?"
                      rows={3}
                    />
                  </div>

                  <Separator />

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label>Database</Label>
                      <Select
                        value={projectSpec.database}
                        onValueChange={(val) => setProjectSpec({...projectSpec, database: val})}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="postgresql">PostgreSQL</SelectItem>
                          <SelectItem value="mysql">MySQL</SelectItem>
                          <SelectItem value="sqlite">SQLite</SelectItem>
                          <SelectItem value="none">None</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div>
                      <Label>Deployment</Label>
                      <Select
                        value={projectSpec.deployment}
                        onValueChange={(val) => setProjectSpec({...projectSpec, deployment: val})}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {DEPLOY_TARGETS.map(dt => (
                            <SelectItem key={dt.id} value={dt.id}>{dt.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <Separator />

                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Label>Authentication</Label>
                      <Switch
                        checked={projectSpec.authentication}
                        onCheckedChange={(val) => setProjectSpec({...projectSpec, authentication: val})}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <Label>Testing Setup</Label>
                      <Switch
                        checked={projectSpec.testing}
                        onCheckedChange={(val) => setProjectSpec({...projectSpec, testing: val})}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <Label>Docker Support</Label>
                      <Switch
                        checked={projectSpec.docker}
                        onCheckedChange={(val) => setProjectSpec({...projectSpec, docker: val})}
                      />
                    </div>
                  </div>

                  <Button onClick={generateProject} className="w-full">
                    <Code className="mr-2 h-4 w-4" />
                    Generate Project
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Generated Project */}
            <Card className="bg-white/[0.02] border-white/5">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Package className="h-5 w-5 text-emerald-400" />
                  Generated Project
                </CardTitle>
                <CardDescription>
                  Your project structure and files
                </CardDescription>
              </CardHeader>
              <CardContent>
                {generatedProject ? (
                  <div className="space-y-4">
                    <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                      <div className="flex items-center gap-2 mb-2">
                        <CheckCircle className="h-4 w-4 text-emerald-400" />
                        <span className="text-sm font-medium">Model output received</span>
                      </div>
                      <p className="text-xs text-muted-foreground/60">
                        {generatedProject.name} · {generatedProject.status} · no files have been written
                      </p>
                    </div>

                    <div>
                      <p className="text-sm font-medium mb-2">Generated response</p>
                      <ScrollArea className="h-[300px]">
                        <pre className="whitespace-pre-wrap break-words rounded bg-black/30 p-3 font-mono text-xs">
                          {generatedProject.code}
                        </pre>
                      </ScrollArea>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-12 text-muted-foreground/40">
                    <Code className="h-16 w-16 mx-auto mb-4 opacity-50" />
                    <h3 className="text-lg font-semibold mb-2">No Project Generated Yet</h3>
                    <p className="text-sm">
                      Define your project specifications and click "Generate Project"
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Deployment Tab */}
        <TabsContent value="deploy" className="mt-4">
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Rocket className="h-5 w-5 text-pink-400" />
                Deployment Targets
              </CardTitle>
              <CardDescription>
                Deploy to multiple cloud platforms with automated CI/CD
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {DEPLOY_TARGETS.map((target, i) => {
                  const Icon = target.icon;
                  return (
                    <motion.div
                      key={target.id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.1 }}
                    >
                      <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5 hover:border-pink-500/20 transition-all cursor-pointer group">
                        <Icon className={`h-10 w-10 mb-3 ${target.color} group-hover:scale-110 transition-transform`} />
                        <h4 className="font-semibold mb-1">{target.name}</h4>
                        <p className="text-xs text-muted-foreground/60 mb-3">
                          One-click deployment
                        </p>
                        <Button size="sm" variant="outline" className="w-full text-xs">
                          <Cloud className="mr-2 h-3 w-3" />
                          Deploy
                        </Button>
                      </div>
                    </motion.div>
                  );
                })}
              </div>

              <Separator className="my-6" />

              <div>
                <h3 className="text-lg font-semibold mb-4">Deployment Pipeline</h3>
                <div className="space-y-3">
                  {["Build & Test", "Code Review", "Security Scan", "Deploy to Staging", "Deploy to Production"].map((step, i) => (
                    <div key={i} className="flex items-center gap-3 p-3 rounded bg-white/[0.02]">
                      <div className="flex items-center justify-center h-6 w-6 rounded-full bg-blue-500/20 text-blue-400 text-xs font-bold">
                        {i + 1}
                      </div>
                      <span className="text-sm flex-1">{step}</span>
                      <Badge className="bg-gray-500/20 text-gray-400 border-gray-500/30">
                        Pending
                      </Badge>
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
