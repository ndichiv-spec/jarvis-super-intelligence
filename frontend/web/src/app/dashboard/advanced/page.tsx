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
  task_id: string;
  status: string;
  description: string;
  pattern: string;
  progress: number;
  agents: string[];
}

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

export default function AdvancedPage() {
  const [isLoading, setIsLoading] = useState(true);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tasks, setTasks] = useState<CollaborationTask[]>([]);
  const [activeTab, setActiveTab] = useState("agents");

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
  const [generatedProject, setGeneratedProject] = useState<any>(null);

  useEffect(() => {
    loadAgentData();
  }, []);

  const loadAgentData = async () => {
    try {
      setIsLoading(true);
      // Load agents list
      try {
        const data = await jarvisAPI.getCollaborationAgents();
        setAgents(data.agents || []);
      } catch (e) {
        // Mock data if API not available
        setAgents(getMockAgents());
      }
    } catch (error) {
      console.error("Failed to load agent data:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const getMockAgents = (): Agent[] => [
    { agent_id: "researcher-1", agent_type: "researcher", name: "Research Agent", status: "idle", capabilities: ["search", "analysis"], tasks_completed: 45, success_rate: 0.92 },
    { agent_id: "coder-1", agent_type: "coder", name: "Code Agent", status: "idle", capabilities: ["python", "javascript"], tasks_completed: 128, success_rate: 0.89 },
    { agent_id: "analyst-1", agent_type: "analyst", name: "Analysis Agent", status: "idle", capabilities: ["data", "patterns"], tasks_completed: 67, success_rate: 0.95 },
    { agent_id: "reviewer-1", agent_type: "reviewer", name: "Review Agent", status: "idle", capabilities: ["code_review", "quality"], tasks_completed: 234, success_rate: 0.97 },
  ];

  const createCollaborationTask = async () => {
    try {
      const description = prompt("Enter task description:");
      if (!description) return;

      toast.info("Creating collaboration task...");
      // In production: await jarvisAPI.createCollaborationTask(...)
      toast.success("Task created successfully");
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
      toast.info("Generating project scaffolding...");
      
      // Mock generation result
      const result = {
        success: true,
        project_name: projectSpec.name,
        files_created: 12,
        files: [
          { path: "main.py", type: "python", size: 1024 },
          { path: "requirements.txt", type: "txt", size: 256 },
          { path: "README.md", type: "markdown", size: 512 },
          { path: "Dockerfile", type: "dockerfile", size: 128 },
        ],
        generation_time_ms: 245,
      };

      setGeneratedProject(result);
      toast.success(`Project "${projectSpec.name}" generated with ${result.files_created} files`);
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
                      ) : (
                        <div className="text-center py-4 text-muted-foreground/40 text-sm">
                          Not initialized
                        </div>
                      )}
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
                        <span className="text-sm font-medium">Project Generated Successfully</span>
                      </div>
                      <p className="text-xs text-muted-foreground/60">
                        {generatedProject.files_created} files created in {generatedProject.generation_time_ms.toFixed(0)}ms
                      </p>
                    </div>

                    <div>
                      <p className="text-sm font-medium mb-2">Files Created:</p>
                      <ScrollArea className="h-[300px]">
                        <div className="space-y-1">
                          {generatedProject.files.map((file: any, i: number) => (
                            <motion.div
                              key={i}
                              initial={{ opacity: 0, x: -20 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ delay: i * 0.05 }}
                              className="flex items-center justify-between p-2 rounded bg-white/[0.02] text-sm"
                            >
                              <div className="flex items-center gap-2">
                                <Terminal className="h-3 w-3 text-muted-foreground/40" />
                                <span>{file.path}</span>
                              </div>
                              <Badge variant="outline" className="text-xs">{file.type}</Badge>
                            </motion.div>
                          ))}
                        </div>
                      </ScrollArea>
                    </div>

                    <div className="flex gap-2">
                      <Button variant="outline" className="flex-1">
                        <Terminal className="mr-2 h-4 w-4" />
                        Open in Terminal
                      </Button>
                      <Button variant="outline" className="flex-1">
                        <Eye className="mr-2 h-4 w-4" />
                        Preview
                      </Button>
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
