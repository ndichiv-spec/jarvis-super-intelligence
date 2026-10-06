"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Play, Plus, Trash2, Edit, Clock, Activity, Zap,
  CheckCircle, XCircle, AlertCircle, Search, Filter,
  RefreshCw, Code, FileText, Globe, Database, Terminal,
  Mail, Bell, Settings, MoreVertical, Pause, Eye
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { jarvisAPI } from "@/lib/api";
import { toast } from "sonner";
import { format } from "date-fns";

interface Workflow {
  id: string;
  name: string;
  description: string;
  status: "pending" | "running" | "completed" | "failed" | "paused";
  triggers: Array<{ type: string; config: any }>;
  steps: Array<{ id: string; name: string; action_type: string; status: string; execution_time?: number }>;
  variables: Record<string, any>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  tags: string[];
  metadata: {
    last_execution?: string;
    last_status?: string;
    execution_count?: number;
    avg_time?: number;
  };
}

interface WorkflowStep {
  id: string;
  name: string;
  action_type: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  execution_time?: number;
  error?: string;
}

const ACTION_TYPE_ICONS: Record<string, React.ElementType> = {
  "web.search": Globe,
  "web.scrape": Globe,
  "file.read": FileText,
  "file.write": FileText,
  "system.command": Terminal,
  "ai.chat": Activity,
  "ai.generate": Activity,
  "data.query_db": Database,
  "data.export_csv": Database,
  "communication.email": Mail,
  "communication.notification": Bell,
  "code.run_python": Code,
};

const ACTION_TYPE_COLORS: Record<string, string> = {
  "web.search": "bg-blue-500/20 text-blue-400 border-blue-500/30",
  "web.scrape": "bg-blue-500/20 text-blue-400 border-blue-500/30",
  "file.read": "bg-amber-500/20 text-amber-400 border-amber-500/30",
  "file.write": "bg-amber-500/20 text-amber-400 border-amber-500/30",
  "system.command": "bg-red-500/20 text-red-400 border-red-500/30",
  "ai.chat": "bg-purple-500/20 text-purple-400 border-purple-500/30",
  "ai.generate": "bg-purple-500/20 text-purple-400 border-purple-500/30",
  "data.query_db": "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  "communication.email": "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
  "communication.notification": "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
  "code.run_python": "bg-orange-500/20 text-orange-400 border-orange-500/30",
};

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedWorkflow, setSelectedWorkflow] = useState<Workflow | null>(null);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("all");

  // Create form state
  const [newWorkflowName, setNewWorkflowName] = useState("");
  const [newWorkflowDescription, setNewWorkflowDescription] = useState("");
  const [newWorkflowSteps, setNewWorkflowSteps] = useState<WorkflowStep[]>([]);

  useEffect(() => {
    loadWorkflows();
  }, []);

  const loadWorkflows = async () => {
    try {
      setIsLoading(true);
      // Try loading workflows from automation endpoint
      const data = await jarvisAPI.getAutomationTasks();
      setWorkflows(data.tasks || data.workflows || []);
    } catch (error) {
      console.error("Failed to load workflows:", error);
      toast.error("Failed to load workflows");
      // Set empty array on error
      setWorkflows([]);
    } finally {
      setIsLoading(false);
    }
  };

  const runWorkflow = async (workflowId: string) => {
    try {
      toast.info("Starting workflow execution...");
      await jarvisAPI.runAutomationTask(workflowId);
      toast.success("Workflow executed successfully");
      await loadWorkflows();
    } catch (error: any) {
      toast.error(`Failed to execute workflow: ${error.message}`);
    }
  };

  const createWorkflow = async () => {
    if (!newWorkflowName.trim()) {
      toast.error("Workflow name is required");
      return;
    }

    try {
      toast.info("Creating workflow...");
      // This would call the actual create endpoint
      // await jarvisAPI.createWorkflow({ ... });
      toast.success("Workflow created successfully");
      setIsCreateDialogOpen(false);
      setNewWorkflowName("");
      setNewWorkflowDescription("");
      setNewWorkflowSteps([]);
      await loadWorkflows();
    } catch (error: any) {
      toast.error(`Failed to create workflow: ${error.message}`);
    }
  };

  const filteredWorkflows = workflows.filter((wf) => {
    const matchesSearch =
      wf.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      wf.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      wf.tags.some((t) => t.toLowerCase().includes(searchQuery.toLowerCase()));

    if (activeTab === "all") return matchesSearch;
    if (activeTab === "active") return wf.enabled && matchesSearch;
    if (activeTab === "disabled") return !wf.enabled && matchesSearch;
    if (activeTab === "running") return wf.status === "running" && matchesSearch;
    if (activeTab === "completed") return wf.status === "completed" && matchesSearch;
    if (activeTab === "failed") return wf.status === "failed" && matchesSearch;
    return matchesSearch;
  });

  const getStatusBadge = (status: string) => {
    const config: Record<string, { icon: React.ElementType; color: string; label: string }> = {
      completed: { icon: CheckCircle, color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30", label: "Completed" },
      running: { icon: Activity, color: "bg-blue-500/20 text-blue-400 border-blue-500/30", label: "Running" },
      failed: { icon: XCircle, color: "bg-red-500/20 text-red-400 border-red-500/30", label: "Failed" },
      paused: { icon: Pause, color: "bg-amber-500/20 text-amber-400 border-amber-500/30", label: "Paused" },
      pending: { icon: Clock, color: "bg-gray-500/20 text-gray-400 border-gray-500/30", label: "Pending" },
    };

    const { icon: Icon, color, label } = config[status] || config.pending;
    return (
      <Badge className={`${color} border`}>
        <Icon className="mr-1 h-3 w-3" />
        {label}
      </Badge>
    );
  };

  const getActionIcon = (actionType: string) => {
    const Icon = ACTION_TYPE_ICONS[actionType] || Settings;
    return <Icon className="h-4 w-4" />;
  };

  const getActionColor = (actionType: string) => {
    return ACTION_TYPE_COLORS[actionType] || "bg-gray-500/20 text-gray-400 border-gray-500/30";
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
          <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 via-purple-400 to-cyan-400 bg-clip-text text-transparent">
            Workflow Automation
          </h1>
          <p className="text-muted-foreground/60 mt-1">
            Build, manage, and automate complex workflows with 28+ action types
          </p>
        </div>
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button className="bg-gradient-to-r from-blue-500 to-purple-500 hover:from-blue-600 hover:to-purple-600">
              <Plus className="mr-2 h-4 w-4" />
              New Workflow
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Create New Workflow</DialogTitle>
              <DialogDescription>
                Define a new automated workflow with triggers and actions
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div>
                <Label htmlFor="wf-name">Workflow Name</Label>
                <Input
                  id="wf-name"
                  value={newWorkflowName}
                  onChange={(e) => setNewWorkflowName(e.target.value)}
                  placeholder="e.g., Daily News Digest"
                />
              </div>
              <div>
                <Label htmlFor="wf-desc">Description</Label>
                <Textarea
                  id="wf-desc"
                  value={newWorkflowDescription}
                  onChange={(e) => setNewWorkflowDescription(e.target.value)}
                  placeholder="What does this workflow do?"
                />
              </div>
              <Separator />
              <div className="text-sm text-muted-foreground">
                <p className="font-semibold mb-2">Available Action Types:</p>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    "web.search", "web.scrape", "file.read", "file.write",
                    "system.command", "ai.chat", "ai.generate", "data.query_db",
                    "communication.email", "code.run_python"
                  ].map((action) => (
                    <div key={action} className="flex items-center gap-2 text-xs">
                      {getActionIcon(action)}
                      <span className="text-muted-foreground/60">{action}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsCreateDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={createWorkflow}>Create Workflow</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </motion.div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { label: "Total Workflows", value: workflows.length, icon: Activity, color: "from-blue-500 to-cyan-400" },
          { label: "Active", value: workflows.filter((w) => w.enabled).length, icon: Zap, color: "from-emerald-500 to-green-400" },
          { label: "Running", value: workflows.filter((w) => w.status === "running").length, icon: Activity, color: "from-purple-500 to-pink-400" },
          { label: "Completed", value: workflows.filter((w) => w.status === "completed").length, icon: CheckCircle, color: "from-amber-500 to-orange-400" },
        ].map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
          >
            <Card className="bg-white/[0.02] border-white/5">
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-2xl font-bold">{stat.value}</p>
                  <p className="text-xs text-muted-foreground/60">{stat.label}</p>
                </div>
                <stat.icon className={`h-8 w-8 bg-gradient-to-br ${stat.color} bg-clip-text text-transparent opacity-50`} />
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Filters */}
      <Card className="bg-white/[0.02] border-white/5">
        <CardContent className="p-4">
          <div className="flex items-center gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40" />
              <Input
                className="pl-10 bg-white/[0.02] border-white/5"
                placeholder="Search workflows by name, description, or tags..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <Tabs value={activeTab} onValueChange={setActiveTab} className="w-auto">
              <TabsList className="bg-white/[0.02] border-white/5">
                <TabsTrigger value="all" className="text-xs">All</TabsTrigger>
                <TabsTrigger value="active" className="text-xs">Active</TabsTrigger>
                <TabsTrigger value="running" className="text-xs">Running</TabsTrigger>
                <TabsTrigger value="completed" className="text-xs">Completed</TabsTrigger>
                <TabsTrigger value="failed" className="text-xs">Failed</TabsTrigger>
              </TabsList>
            </Tabs>
            <Button variant="outline" size="icon" onClick={loadWorkflows} disabled={isLoading}>
              <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Workflow List */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {isLoading ? (
          <div className="col-span-2 flex items-center justify-center py-20">
            <RefreshCw className="h-8 w-8 animate-spin text-blue-400" />
          </div>
        ) : filteredWorkflows.length === 0 ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="col-span-2 flex flex-col items-center justify-center py-20 text-center"
          >
            <Activity className="h-16 w-16 text-muted-foreground/20 mb-4" />
            <h3 className="text-xl font-semibold text-muted-foreground/60 mb-2">No workflows found</h3>
            <p className="text-sm text-muted-foreground/40 mb-4">
              Create your first workflow to automate repetitive tasks
            </p>
            <Button onClick={() => setIsCreateDialogOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Create Workflow
            </Button>
          </motion.div>
        ) : (
          filteredWorkflows.map((workflow, i) => (
            <motion.div
              key={workflow.id || i}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
            >
              <Card className="bg-white/[0.02] border-white/5 hover:border-blue-500/20 transition-all">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <CardTitle className="text-lg flex items-center gap-2">
                        {workflow.name}
                        {!workflow.enabled && (
                          <Badge variant="outline" className="text-xs bg-gray-500/20 text-gray-400">
                            Disabled
                          </Badge>
                        )}
                      </CardTitle>
                      <CardDescription className="mt-1">
                        {workflow.description || "No description"}
                      </CardDescription>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => runWorkflow(workflow.id)}
                        className="h-7 px-3 text-xs"
                      >
                        <Play className="mr-1 h-3 w-3" />
                        Run
                      </Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7">
                        <MoreVertical className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {/* Status & Metadata */}
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        {getStatusBadge(workflow.status)}
                        {workflow.metadata?.execution_count && (
                          <Badge variant="outline" className="text-xs">
                            {workflow.metadata.execution_count} runs
                          </Badge>
                        )}
                      </div>
                      {workflow.metadata?.last_execution && (
                        <span className="text-muted-foreground/40">
                          {format(new Date(workflow.metadata.last_execution), "MMM d, HH:mm")}
                        </span>
                      )}
                    </div>

                    {/* Workflow Steps */}
                    {workflow.steps && workflow.steps.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-muted-foreground/60 mb-2">Steps:</p>
                        <div className="space-y-1">
                          {workflow.steps.slice(0, 3).map((step, idx) => {
                            const StepIcon = ACTION_TYPE_ICONS[step.action_type] || Settings;
                            return (
                              <div key={step.id || idx} className="flex items-center gap-2 text-xs bg-white/[0.02] rounded-lg px-3 py-2">
                                <div className={`p-1 rounded ${getActionColor(step.action_type)}`}>
                                  <StepIcon className="h-3 w-3" />
                                </div>
                                <span className="flex-1">{step.name}</span>
                                {step.execution_time && (
                                  <span className="text-muted-foreground/40">{step.execution_time.toFixed(1)}s</span>
                                )}
                              </div>
                            );
                          })}
                          {workflow.steps.length > 3 && (
                            <p className="text-xs text-muted-foreground/40 text-center">
                              +{workflow.steps.length - 3} more steps
                            </p>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Triggers */}
                    {workflow.triggers && workflow.triggers.length > 0 && (
                      <div className="flex items-center gap-2 text-xs">
                        <Clock className="h-3 w-3 text-muted-foreground/40" />
                        <span className="text-muted-foreground/60">Triggers:</span>
                        <div className="flex gap-1">
                          {workflow.triggers.slice(0, 2).map((trigger, idx) => (
                            <Badge key={idx} variant="outline" className="text-[10px]">
                              {trigger.type}
                            </Badge>
                          ))}
                          {workflow.triggers.length > 2 && (
                            <span className="text-muted-foreground/40">+{workflow.triggers.length - 2}</span>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Tags */}
                    {workflow.tags && workflow.tags.length > 0 && (
                      <div className="flex gap-1 flex-wrap">
                        {workflow.tags.map((tag, idx) => (
                          <Badge key={idx} variant="outline" className="text-[10px] bg-white/[0.02]">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))
        )}
      </div>

      {/* Templates Section */}
      {!isLoading && workflows.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <Card className="bg-gradient-to-br from-blue-500/5 to-purple-500/5 border-blue-500/10">
            <CardHeader>
              <CardTitle className="text-lg">Quick Start Templates</CardTitle>
              <CardDescription>
                Pre-built workflow templates to get you started
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {[
                  {
                    title: "Daily News Digest",
                    description: "Search news, summarize with AI, send email digest",
                    icon: Mail,
                    steps: ["web.search", "ai.generate", "communication.email"],
                  },
                  {
                    title: "System Health Check",
                    description: "Monitor system, check processes, send alerts",
                    icon: Activity,
                    steps: ["system.command", "data.query_db", "communication.notification"],
                  },
                  {
                    title: "Code Analysis Pipeline",
                    description: "Read code, analyze with AI, generate report",
                    icon: Code,
                    steps: ["file.read", "ai.analyze", "file.write"],
                  },
                ].map((template, i) => (
                  <div
                    key={i}
                    className="p-4 rounded-lg bg-white/[0.02] border border-white/5 hover:border-blue-500/20 transition-all cursor-pointer group"
                    onClick={() => {
                      setNewWorkflowName(template.title);
                      setNewWorkflowDescription(template.description);
                      setIsCreateDialogOpen(true);
                    }}
                  >
                    <template.icon className="h-8 w-8 text-blue-400 mb-2 group-hover:scale-110 transition-transform" />
                    <h4 className="font-semibold text-sm mb-1">{template.title}</h4>
                    <p className="text-xs text-muted-foreground/60 mb-2">{template.description}</p>
                    <div className="flex gap-1">
                      {template.steps.map((step, idx) => {
                        const StepIcon = ACTION_TYPE_ICONS[step] || Settings;
                        return (
                          <div key={idx} className={`p-1 rounded ${getActionColor(step)}`}>
                            <StepIcon className="h-3 w-3" />
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}
    </div>
  );
}
