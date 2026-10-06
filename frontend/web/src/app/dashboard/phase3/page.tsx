"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Brain, Database, Upload, Play, BarChart3, Zap, Layers,
  Package, Plug, Download, CheckCircle, XCircle, Clock,
  RefreshCw, TrendingUp, Settings, Eye, Code, GitBranch
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";

interface DatasetStats {
  total_samples: number;
  by_category: Record<string, number>;
  high_quality_samples: number;
  average_rating: number;
}

interface TrainingJob {
  id: string;
  model_name: string;
  dataset_size: number;
  status: string;
  started_at?: string;
  metrics?: Record<string, number>;
}

interface Plugin {
  id: string;
  name: string;
  version: string;
  description: string;
  status: string;
  tools: string[];
}

export default function Phase3Page() {
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("finetune");
  const [datasetStats, setDatasetStats] = useState<DatasetStats | null>(null);
  const [trainingJobs, setTrainingJobs] = useState<TrainingJob[]>([]);
  const [plugins, setPlugins] = useState<Plugin[]>([]);

  // Form states
  const [newSample, setNewSample] = useState({ prompt: "", response: "", rating: 5, category: "general" });
  const [newJob, setNewJob] = useState({ model: "llama3", epochs: 3, learningRate: 0.0002 });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setIsLoading(true);
      // Mock data for demonstration
      setDatasetStats({
        total_samples: 1247,
        by_category: { code: 423, conversation: 312, explanation: 189, debugging: 156, creative: 167 },
        high_quality_samples: 892,
        average_rating: 4.2,
      });

      setTrainingJobs([
        { id: "job_001", model_name: "llama3-finetuned-v1", dataset_size: 892, status: "completed", started_at: new Date(Date.now() - 86400000 * 2).toISOString(), metrics: { accuracy: 0.89, loss: 0.23 } },
        { id: "job_002", model_name: "llama3-finetuned-v2", dataset_size: 1100, status: "training", started_at: new Date(Date.now() - 3600000).toISOString() },
      ]);

      setPlugins([
        { id: "github-integration", name: "GitHub Integration", version: "1.2.0", description: "Connect to GitHub repositories", status: "loaded", tools: ["search_repos", "create_issue", "review_pr"] },
        { id: "slack-notifications", name: "Slack Notifications", version: "1.0.0", description: "Send AI responses to Slack", status: "loaded", tools: ["send_message", "create_channel"] },
        { id: "jira-sync", name: "JIRA Sync", version: "0.9.0", description: "Sync with JIRA tickets", status: "unloaded", tools: ["create_ticket", "update_status"] },
        { id: "custom-api", name: "Custom API Hooks", version: "1.1.0", description: "Create custom API integrations", status: "loaded", tools: ["webhook", "rest_call", "graphql"] },
      ]);
    } catch (error) {
      console.error("Failed to load Phase 3 data:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const addSample = async () => {
    if (!newSample.prompt.trim() || !newSample.response.trim()) {
      toast.error("Prompt and response are required");
      return;
    }
    toast.success("Training sample added to dataset");
    setNewSample({ prompt: "", response: "", rating: 5, category: "general" });
    loadData();
  };

  const createTrainingJob = async () => {
    toast.info(`Creating training job for ${newJob.model}...`);
    const jobId = `job_${Date.now()}`;
    setTrainingJobs([...trainingJobs, {
      id: jobId,
      model_name: `${newJob.model}-finetuned-v${trainingJobs.length + 1}`,
      dataset_size: datasetStats?.high_quality_samples || 0,
      status: "pending",
    }]);
    toast.success("Training job created");
  };

  const togglePlugin = async (pluginId: string, action: string) => {
    toast.info(`${action} plugin ${pluginId}...`);
    setPlugins(plugins.map(p =>
      p.id === pluginId ? { ...p, status: action === "load" || action === "enable" ? "loaded" : "unloaded" } : p
    ));
    toast.success(`Plugin ${action}ed`);
  };

  const getStatusBadge = (status: string) => {
    const config: Record<string, { color: string; icon: React.ElementType }> = {
      completed: { color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30", icon: CheckCircle },
      training: { color: "bg-blue-500/20 text-blue-400 border-blue-500/30", icon: Play },
      pending: { color: "bg-amber-500/20 text-amber-400 border-amber-500/30", icon: Clock },
      failed: { color: "bg-red-500/20 text-red-400 border-red-500/30", icon: XCircle },
      loaded: { color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30", icon: CheckCircle },
      unloaded: { color: "bg-gray-500/20 text-gray-400 border-gray-500/30", icon: XCircle },
    };
    const { color, icon: Icon } = config[status] || config.pending;
    return <Badge className={`${color} border`}><Icon className="mr-1 h-3 w-3" />{status}</Badge>;
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-orange-400 via-pink-400 to-purple-400 bg-clip-text text-transparent">
            Phase 3: Advanced Systems
          </h1>
          <p className="text-muted-foreground/60 mt-1">
            AI fine-tuning, plugin ecosystem, and PWA capabilities
          </p>
        </div>
        <Button onClick={loadData} disabled={isLoading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </motion.div>

      {/* Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { label: "Training Samples", value: datasetStats?.total_samples || 0, icon: Database, color: "from-blue-500 to-cyan-400" },
          { label: "High Quality", value: datasetStats?.high_quality_samples || 0, icon: TrendingUp, color: "from-emerald-500 to-green-400" },
          { label: "Training Jobs", value: trainingJobs.length, icon: Play, color: "from-purple-500 to-pink-400" },
          { label: "Active Plugins", value: plugins.filter(p => p.status === "loaded").length, icon: Plug, color: "from-orange-500 to-amber-400" },
        ].map((stat, i) => (
          <motion.div key={stat.label} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.1 }}>
            <Card className="bg-white/[0.02] border-white/5">
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-2xl font-bold">{stat.value}</p>
                  <p className="text-xs text-muted-foreground/60">{stat.label}</p>
                </div>
                <stat.icon className={`h-8 w-8 bg-gradient-to-br ${stat.color} bg-clip-text opacity-50`} />
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-white/[0.02] border-white/5">
          <TabsTrigger value="finetune" className="text-sm">
            <Brain className="mr-2 h-4 w-4" />
            Fine-Tuning
          </TabsTrigger>
          <TabsTrigger value="dataset" className="text-sm">
            <Database className="mr-2 h-4 w-4" />
            Dataset
          </TabsTrigger>
          <TabsTrigger value="plugins" className="text-sm">
            <Plug className="mr-2 h-4 w-4" />
            Plugins
          </TabsTrigger>
          <TabsTrigger value="pwa" className="text-sm">
            <Download className="mr-2 h-4 w-4" />
            PWA
          </TabsTrigger>
        </TabsList>

        {/* Fine-Tuning Tab */}
        <TabsContent value="finetune" className="mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Add Training Sample */}
            <Card className="bg-white/[0.02] border-white/5">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Upload className="h-5 w-5 text-blue-400" />
                  Add Training Sample
                </CardTitle>
                <CardDescription>Add high-quality examples to improve AI responses</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <Label>Prompt</Label>
                    <Textarea
                      value={newSample.prompt}
                      onChange={(e) => setNewSample({...newSample, prompt: e.target.value})}
                      placeholder="User input or question..."
                      rows={3}
                    />
                  </div>
                  <div>
                    <Label>Ideal Response</Label>
                    <Textarea
                      value={newSample.response}
                      onChange={(e) => setNewSample({...newSample, response: e.target.value})}
                      placeholder="Expected AI response..."
                      rows={4}
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label>Quality Rating</Label>
                      <Select value={newSample.rating.toString()} onValueChange={(v) => setNewSample({...newSample, rating: parseInt(v)})}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {[5,4,3,2,1].map(r => <SelectItem key={r} value={r.toString()}>{r} Stars</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label>Category</Label>
                      <Select value={newSample.category} onValueChange={(v) => setNewSample({...newSample, category: v})}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {["general", "code", "conversation", "explanation", "debugging", "creative"].map(c => (
                            <SelectItem key={c} value={c}>{c}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <Button onClick={addSample} className="w-full">
                    <Upload className="mr-2 h-4 w-4" />
                    Add to Dataset
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Create Training Job */}
            <Card className="bg-white/[0.02] border-white/5">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Brain className="h-5 w-5 text-purple-400" />
                  Create Training Job
                </CardTitle>
                <CardDescription>Fine-tune AI model on your dataset</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <Label>Base Model</Label>
                    <Select value={newJob.model} onValueChange={(v) => setNewJob({...newJob, model: v})}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="llama3">Llama 3</SelectItem>
                        <SelectItem value="mistral">Mistral 7B</SelectItem>
                        <SelectItem value="phi3">Phi 3</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label>Epochs</Label>
                      <Input type="number" value={newJob.epochs} onChange={(e) => setNewJob({...newJob, epochs: parseInt(e.target.value)})} />
                    </div>
                    <div>
                      <Label>Learning Rate</Label>
                      <Input type="number" step="0.0001" value={newJob.learningRate} onChange={(e) => setNewJob({...newJob, learningRate: parseFloat(e.target.value)})} />
                    </div>
                  </div>
                  <div className="p-3 rounded bg-blue-500/10 border border-blue-500/20">
                    <p className="text-sm text-blue-400">Dataset: {datasetStats?.high_quality_samples || 0} high-quality samples</p>
                    <p className="text-xs text-muted-foreground/60 mt-1">Estimated training time: ~2-4 hours</p>
                  </div>
                  <Button onClick={createTrainingJob} className="w-full bg-gradient-to-r from-purple-500 to-pink-500">
                    <Brain className="mr-2 h-4 w-4" />
                    Start Training
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Training Jobs List */}
          <Card className="bg-white/[0.02] border-white/5 mt-6">
            <CardHeader>
              <CardTitle>Training Jobs</CardTitle>
              <CardDescription>Current and past model training jobs</CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[300px]">
                <div className="space-y-3">
                  {trainingJobs.map((job, i) => (
                    <motion.div key={job.id} initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}>
                      <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
                        <div className="flex items-start justify-between mb-2">
                          <div>
                            <h4 className="font-semibold">{job.model_name}</h4>
                            <p className="text-xs text-muted-foreground/60">Job ID: {job.id}</p>
                          </div>
                          {getStatusBadge(job.status)}
                        </div>
                        <div className="grid grid-cols-3 gap-2 text-xs mt-3">
                          <div className="p-2 rounded bg-white/[0.02]">
                            <p className="text-muted-foreground/40">Dataset</p>
                            <p className="font-medium">{job.dataset_size} samples</p>
                          </div>
                          <div className="p-2 rounded bg-white/[0.02]">
                            <p className="text-muted-foreground/40">Status</p>
                            <p className="font-medium capitalize">{job.status}</p>
                          </div>
                          {job.metrics && (
                            <div className="p-2 rounded bg-white/[0.02]">
                              <p className="text-muted-foreground/40">Accuracy</p>
                              <p className="font-medium">{(job.metrics.accuracy * 100).toFixed(0)}%</p>
                            </div>
                          )}
                        </div>
                        {job.status === "training" && (
                          <div className="mt-3">
                            <Progress value={45} className="h-1" />
                            <p className="text-xs text-muted-foreground/40 mt-1">Training in progress... 45%</p>
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

        {/* Dataset Tab */}
        <TabsContent value="dataset" className="mt-4">
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="h-5 w-5 text-emerald-400" />
                Training Dataset Overview
              </CardTitle>
              <CardDescription>
                Dataset composition and quality metrics
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Category Breakdown */}
                <div>
                  <h4 className="text-sm font-semibold mb-3">Samples by Category</h4>
                  <div className="space-y-2">
                    {datasetStats && Object.entries(datasetStats.by_category).map(([cat, count]) => (
                      <div key={cat} className="flex items-center justify-between p-2 rounded bg-white/[0.02]">
                        <span className="text-sm capitalize">{cat}</span>
                        <div className="flex items-center gap-2">
                          <Progress value={(count / datasetStats.total_samples) * 100} className="w-24 h-1" />
                          <span className="text-xs font-medium">{count}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Quality Metrics */}
                <div>
                  <h4 className="text-sm font-semibold mb-3">Quality Metrics</h4>
                  <div className="space-y-3">
                    <div className="p-3 rounded bg-white/[0.02]">
                      <p className="text-xs text-muted-foreground/60 mb-1">Total Samples</p>
                      <p className="text-2xl font-bold">{datasetStats?.total_samples || 0}</p>
                    </div>
                    <div className="p-3 rounded bg-white/[0.02]">
                      <p className="text-xs text-muted-foreground/60 mb-1">High Quality (≥0.7)</p>
                      <p className="text-2xl font-bold text-emerald-400">{datasetStats?.high_quality_samples || 0}</p>
                    </div>
                    <div className="p-3 rounded bg-white/[0.02]">
                      <p className="text-xs text-muted-foreground/60 mb-1">Average Rating</p>
                      <p className="text-2xl font-bold text-amber-400">{datasetStats?.average_rating || 0}/5.0</p>
                    </div>
                  </div>
                </div>
              </div>

              <Separator className="my-6" />

              {/* Export Options */}
              <div>
                <h4 className="text-sm font-semibold mb-3">Export Dataset</h4>
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { format: "JSONL", desc: "For training pipelines", icon: Code },
                    { format: "Alpaca", desc: "For LLaMA fine-tuning", icon: Brain },
                    { format: "JSON", desc: "For inspection & analysis", icon: Eye },
                  ].map((exp, i) => (
                    <Button key={exp.format} variant="outline" className="h-auto py-4 flex flex-col items-center gap-2">
                      <exp.icon className="h-6 w-6" />
                      <span className="text-sm font-medium">{exp.format}</span>
                      <span className="text-xs text-muted-foreground/60">{exp.desc}</span>
                    </Button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Plugins Tab */}
        <TabsContent value="plugins" className="mt-4">
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Plug className="h-5 w-5 text-orange-400" />
                    Plugin Ecosystem
                  </CardTitle>
                  <CardDescription>
                    Extend JARVIS with custom integrations and tools
                  </CardDescription>
                </div>
                <Button variant="outline">
                  <Package className="mr-2 h-4 w-4" />
                  Browse Marketplace
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {plugins.map((plugin, i) => (
                  <motion.div key={plugin.id} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.1 }}>
                    <Card className="bg-white/[0.02] border-white/5 hover:border-orange-500/20 transition-all">
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between mb-3">
                          <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-orange-500/10">
                              <Plug className="h-5 w-5 text-orange-400" />
                            </div>
                            <div>
                              <h4 className="font-semibold">{plugin.name}</h4>
                              <p className="text-xs text-muted-foreground/60">v{plugin.version}</p>
                            </div>
                          </div>
                          {getStatusBadge(plugin.status)}
                        </div>

                        <p className="text-sm text-muted-foreground/60 mb-3">{plugin.description}</p>

                        {plugin.tools.length > 0 && (
                          <div className="mb-3">
                            <p className="text-xs font-semibold text-muted-foreground/60 mb-1">Tools:</p>
                            <div className="flex gap-1 flex-wrap">
                              {plugin.tools.map((tool, idx) => (
                                <Badge key={idx} variant="outline" className="text-xs bg-white/[0.02]">
                                  <Code className="mr-1 h-2.5 w-2.5" />
                                  {tool}
                                </Badge>
                              ))}
                            </div>
                          </div>
                        )}

                        <div className="flex gap-2">
                          {plugin.status === "loaded" ? (
                            <Button variant="outline" size="sm" onClick={() => togglePlugin(plugin.id, "unload")}>
                              <XCircle className="mr-1 h-3 w-3" />
                              Disable
                            </Button>
                          ) : (
                            <Button size="sm" onClick={() => togglePlugin(plugin.id, "load")}>
                              <Play className="mr-1 h-3 w-3" />
                              Enable
                            </Button>
                          )}
                          <Button variant="ghost" size="sm">
                            <Settings className="mr-1 h-3 w-3" />
                            Settings
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  </motion.div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* PWA Tab */}
        <TabsContent value="pwa" className="mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="bg-white/[0.02] border-white/5">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Download className="h-5 w-5 text-cyan-400" />
                  Progressive Web App
                </CardTitle>
                <CardDescription>
                  Install JARVIS on your device for native-like experience
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="p-4 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                    <h4 className="font-semibold mb-2 flex items-center gap-2">
                      <CheckCircle className="h-4 w-4 text-cyan-400" />
                      PWA Features Enabled
                    </h4>
                    <ul className="space-y-1 text-sm text-muted-foreground/60">
                      <li className="flex items-center gap-2"><CheckCircle className="h-3 w-3 text-emerald-400" />Offline mode for chat history</li>
                      <li className="flex items-center gap-2"><CheckCircle className="h-3 w-3 text-emerald-400" />Add to home screen</li>
                      <li className="flex items-center gap-2"><CheckCircle className="h-3 w-3 text-emerald-400" />Push notifications</li>
                      <li className="flex items-center gap-2"><CheckCircle className="h-3 w-3 text-emerald-400" />Background sync</li>
                      <li className="flex items-center gap-2"><CheckCircle className="h-3 w-3 text-emerald-400" />App shortcuts</li>
                    </ul>
                  </div>

                  <Button className="w-full bg-gradient-to-r from-cyan-500 to-blue-500">
                    <Download className="mr-2 h-4 w-4" />
                    Install JARVIS App
                  </Button>

                  <div className="text-xs text-muted-foreground/40 text-center">
                    Works on Desktop, iOS, and Android
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="bg-white/[0.02] border-white/5">
              <CardHeader>
                <CardTitle>App Manifest</CardTitle>
                <CardDescription>
                  PWA configuration details
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {[
                    { label: "Name", value: "JARVIS Super AI" },
                    { label: "Start URL", value: "/dashboard" },
                    { label: "Display Mode", value: "standalone" },
                    { label: "Theme Color", value: "#00d4ff" },
                    { label: "Background", value: "#030712" },
                    { label: "Icons", value: "192x192, 384x384, 512x512" },
                    { label: "Shortcuts", value: "Neural Chat, Workflows, Knowledge" },
                  ].map((item, i) => (
                    <div key={i} className="flex items-center justify-between p-2 rounded bg-white/[0.02]">
                      <span className="text-sm text-muted-foreground/60">{item.label}</span>
                      <span className="text-sm font-mono">{item.value}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
