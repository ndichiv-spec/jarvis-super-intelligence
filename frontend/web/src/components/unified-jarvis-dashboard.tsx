"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain, Cpu, Activity, Settings, Layers, Terminal,
  Database, Network, BarChart3, Globe, Shield, Code2,
  Monitor, Zap, Sparkles, Command, Server, Cloud,
  MessageSquare, Bell, Home, Wrench, BookOpen,
  Search, Menu, X, ChevronDown, Grid, List,
  Lock, Unlock, Eye, EyeOff, RefreshCw, Play, Pause,
  Square, AlertTriangle, CheckCircle, XCircle, Rocket,
  Target, Gauge, Timer, Calendar, FileText, Folder,
  Atom, Dna, Microscope, Beaker, FlaskConical, TestTube,
  Heart, TrendingDown, Thermometer, StickyNote, Bot, Puzzle,
  HardDrive, Wifi, Battery, MemoryStick, Plug, Download, Upload,
  ArrowUpCircle, ArrowDownCircle, Users, Clock, TrendingUp,
  PieChart, LineChart, ScatterChart, AreaChart, Mic, Box
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { toast } from "sonner";

// Import existing components
import EmbeddedBrowser from "@/components/embedded-browser/EmbeddedBrowser";
import JarvisChat from "@/components/jarvis-chat";
import JarvisNotes from "@/components/jarvis-notes";
import JarvisReminders from "@/components/jarvis-reminders";
import JarvisCapabilitiesOverview from "@/components/jarvis-capabilities-overview";
import CascadeCodeViewer from "@/components/cascade-codeviewer";
import JarvisSuperiorDashboard from "@/components/jarvis-superior-dashboard";
import JarvisSmartHome from "@/components/jarvis-smart-home";
import JarvisSettings from "@/components/jarvis-settings";
import JarvisTools from "@/components/jarvis-tools";
import SelfReliantIDE from "@/app/dashboard/self-reliant/page";
import AdvancedPage from "@/app/dashboard/advanced/page";
import RealTimeMonitoring from "@/components/real-time-monitoring";
import RealAIChat from "@/components/real-ai-chat";
import AdvancedAgentOrchestration from "@/components/advanced-agent-orchestration";
import JarvisFullPotential from "@/components/jarvis-full-potential";
import Jarvis3DVisualization from "@/components/jarvis-3d-visualization";
import JarvisVoiceInterface from "@/components/jarvis-voice-interface";
import JarvisV10Chambers from "@/components/jarvis-v10-chambers";
import JarvisHolographicInterface from "@/components/jarvis-holographic-interface";
import JarvisMultidimensionalViz from "@/components/jarvis-multidimensional-viz";

interface SystemStatus {
  status: 'online' | 'offline' | 'warning';
  uptime: string;
  components: number;
  active_processes: number;
  cpu_usage: number;
  memory_usage: number;
  disk_usage: number;
  network_status: 'connected' | 'disconnected';
  last_update: string;
}

interface TierStatus {
  tier: number;
  name: string;
  status: 'active' | 'inactive' | 'error';
  features: string[];
  performance: number;
  last_update: string;
}

export default function UnifiedJarvisDashboard() {
  const [systemStatus, setSystemStatus] = useState<SystemStatus>({
    status: 'online',
    uptime: '0h 0m 0s',
    components: 209,
    active_processes: 0,
    cpu_usage: 0,
    memory_usage: 0,
    disk_usage: 0,
    network_status: 'connected',
    last_update: new Date().toISOString()
  });

  const [tierStatuses, setTierStatuses] = useState<TierStatus[]>([
    { tier: 1, name: 'Foundation', status: 'active', features: ['Core AI', 'Basic Chat', 'Voice Interface'], performance: 95, last_update: new Date().toISOString() },
    { tier: 2, name: 'Enhanced AI', status: 'active', features: ['Advanced NLP', 'Memory System', 'Knowledge Base'], performance: 92, last_update: new Date().toISOString() },
    { tier: 3, name: 'Collaboration', status: 'active', features: ['Agent Swarm', 'Multi-Agent', 'Real-time Sync'], performance: 88, last_update: new Date().toISOString() },
    { tier: 4, name: 'Enterprise', status: 'active', features: ['Security', 'Compliance', 'Scalability'], performance: 85, last_update: new Date().toISOString() },
    { tier: 5, name: 'Advanced', status: 'active', features: ['Quantum Processing', 'Neural Networks', 'Predictive AI'], performance: 82, last_update: new Date().toISOString() },
    { tier: 6, name: 'Autonomous', status: 'active', features: ['Self-Learning', 'Self-Optimization', 'Autonomous Tasks'], performance: 78, last_update: new Date().toISOString() },
  ]);

  const [activeTab, setActiveTab] = useState("overview");
  const [loading, setLoading] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // System monitoring
  useEffect(() => {
    const updateSystemStatus = () => {
      setSystemStatus(prev => ({
        ...prev,
        cpu_usage: Math.random() * 30 + 20,
        memory_usage: Math.random() * 20 + 40,
        disk_usage: 45,
        last_update: new Date().toISOString()
      }));
    };

    const interval = setInterval(updateSystemStatus, 5000);
    updateSystemStatus();
    setLoading(false);

    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'online': return 'text-green-400';
      case 'offline': return 'text-red-400';
      case 'warning': return 'text-yellow-400';
      case 'active': return 'text-green-400';
      case 'inactive': return 'text-gray-400';
      case 'error': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'online': return <Badge className="bg-green-500">Online</Badge>;
      case 'offline': return <Badge className="bg-red-500">Offline</Badge>;
      case 'warning': return <Badge className="bg-yellow-500">Warning</Badge>;
      case 'active': return <Badge className="bg-green-500">Active</Badge>;
      case 'inactive': return <Badge className="bg-gray-500">Inactive</Badge>;
      case 'error': return <Badge className="bg-red-500">Error</Badge>;
      default: return <Badge className="bg-gray-500">Unknown</Badge>;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      <div className="flex h-screen">
        {/* Sidebar */}
        <motion.aside
          initial={{ width: 0 }}
          animate={{ width: sidebarOpen ? 280 : 0 }}
          className="bg-slate-800 border-r border-slate-700 overflow-hidden"
        >
          <div className="p-4">
            <div className="flex items-center space-x-3 mb-6">
              <div className="p-2 bg-blue-500 rounded-lg">
                <Brain className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">JARVIS</h1>
                <p className="text-xs text-gray-400">Version 10.0 Dashboard</p>
              </div>
            </div>

            <ScrollArea className="h-[calc(100vh-200px)]">
              <div className="space-y-2">
                <Button
                  variant={activeTab === "overview" ? "default" : "ghost"}
                  className="w-full justify-start"
                  onClick={() => setActiveTab("overview")}
                >
                  <Activity className="w-4 h-4 mr-2" />
                  Overview
                </Button>

                <Button
                  variant={activeTab === "browser" ? "default" : "ghost"}
                  className="w-full justify-start"
                  onClick={() => setActiveTab("browser")}
                >
                  <Globe className="w-4 h-4 mr-2" />
                  Embedded Browser
                </Button>

                <Button
                  variant={activeTab === "ide" ? "default" : "ghost"}
                  className="w-full justify-start"
                  onClick={() => setActiveTab("ide")}
                >
                  <Code2 className="w-4 h-4 mr-2" />
                  Self-Reliant IDE
                </Button>

                <Button
                  variant={activeTab === "chat" ? "default" : "ghost"}
                  className="w-full justify-start"
                  onClick={() => setActiveTab("chat")}
                >
                  <MessageSquare className="w-4 h-4 mr-2" />
                  Real AI Chat
                </Button>

                <Button
                  variant={activeTab === "advanced-agents" ? "default" : "ghost"}
                  className="w-full justify-start"
                  onClick={() => setActiveTab("advanced-agents")}
                >
                  <Bot className="w-4 h-4 mr-2" />
                  Advanced Agents
                </Button>

                <Button
                  variant={activeTab === "full-potential" ? "default" : "ghost"}
                  className="w-full justify-start bg-gradient-to-r from-purple-500 to-pink-500 text-white"
                  onClick={() => setActiveTab("full-potential")}
                >
                  <Sparkles className="w-4 h-4 mr-2" />
                  Full Potential
                </Button>

                <Button
                  variant={activeTab === "3d-visualization" ? "default" : "ghost"}
                  className="w-full justify-start"
                  onClick={() => setActiveTab("3d-visualization")}
                >
                  <Atom className="w-4 h-4 mr-2" />
                  3D Visualization
                </Button>

                <Button
                  variant={activeTab === "voice-interface" ? "default" : "ghost"}
                  className="w-full justify-start"
                  onClick={() => setActiveTab("voice-interface")}
                >
                  <Mic className="w-4 h-4 mr-2" />
                  Voice Interface
                </Button>

                <Button
                  variant={activeTab === "v10-chambers" ? "default" : "ghost"}
                  className="w-full justify-start bg-gradient-to-r from-purple-500 to-cyan-500 text-white"
                  onClick={() => setActiveTab("v10-chambers")}
                >
                  <Server className="w-4 h-4 mr-2" />
                  V10 Chambers
                </Button>

                <Button
                  variant={activeTab === "holographic" ? "default" : "ghost"}
                  className="w-full justify-start"
                  onClick={() => setActiveTab("holographic")}
                >
                  <Eye className="w-4 h-4 mr-2" />
                  Holographic
                </Button>

                <Button
                  variant={activeTab === "multidimensional" ? "default" : "ghost"}
                  className="w-full justify-start"
                  onClick={() => setActiveTab("multidimensional")}
                >
                  <Box className="w-4 h-4 mr-2" />
                  Multi-Dimensional
                </Button>

                <Button
                  variant={activeTab === "tiers" ? "default" : "ghost"}
                  className="w-full justify-start"
                  onClick={() => setActiveTab("tiers")}
                >
                  <Layers className="w-4 h-4 mr-2" />
                  Tier Management
                </Button>

                <Button
                  variant={activeTab === "monitoring" ? "default" : "ghost"}
                  className="w-full justify-start"
                  onClick={() => setActiveTab("monitoring")}
                >
                  <Monitor className="w-4 h-4 mr-2" />
                  Real-Time Monitor
                </Button>

                <Button
                  variant={activeTab === "smarthome" ? "default" : "ghost"}
                  className="w-full justify-start"
                  onClick={() => setActiveTab("smarthome")}
                >
                  <Home className="w-4 h-4 mr-2" />
                  Smart Home
                </Button>

                <Button
                  variant={activeTab === "tools" ? "default" : "ghost"}
                  className="w-full justify-start"
                  onClick={() => setActiveTab("tools")}
                >
                  <Wrench className="w-4 h-4 mr-2" />
                  Tools
                </Button>

                <Button
                  variant={activeTab === "advanced" ? "default" : "ghost"}
                  className="w-full justify-start"
                  onClick={() => setActiveTab("advanced")}
                >
                  <Sparkles className="w-4 h-4 mr-2" />
                  Advanced AI
                </Button>

                <Button
                  variant={activeTab === "settings" ? "default" : "ghost"}
                  className="w-full justify-start"
                  onClick={() => setActiveTab("settings")}
                >
                  <Settings className="w-4 h-4 mr-2" />
                  Settings
                </Button>
              </div>
            </ScrollArea>
          </div>
        </motion.aside>

        {/* Main Content */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Header */}
          <header className="bg-slate-800 border-b border-slate-700 p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-4">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setSidebarOpen(!sidebarOpen)}
                >
                  <Menu className="w-5 h-5" />
                </Button>
                <div>
                  <h2 className="text-2xl font-bold text-white">
                    {activeTab.charAt(0).toUpperCase() + activeTab.slice(1)}
                  </h2>
                  <p className="text-sm text-gray-400">
                    JARVIS Unified Control Center
                  </p>
                </div>
              </div>

              <div className="flex items-center space-x-4">
                <div className="flex items-center space-x-2">
                  <Badge className={getStatusColor(systemStatus.status)}>
                    {systemStatus.status.toUpperCase()}
                  </Badge>
                  <span className="text-sm text-gray-400">
                    Uptime: {systemStatus.uptime}
                  </span>
                </div>

                <Button variant="ghost" size="icon">
                  <Bell className="w-5 h-5" />
                </Button>

                <Button variant="ghost" size="icon">
                  <RefreshCw className="w-5 h-5" />
                </Button>
              </div>
            </div>
          </header>

          {/* Content Area */}
          <main className="flex-1 overflow-auto p-6">
            <AnimatePresence mode="wait">
              {activeTab === "overview" && (
                <motion.div
                  key="overview"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  className="space-y-6"
                >
                  {/* System Status Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <Card className="bg-slate-800 border-slate-700">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-gray-400">CPU Usage</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="text-2xl font-bold text-white">
                          {systemStatus.cpu_usage.toFixed(1)}%
                        </div>
                        <Progress value={systemStatus.cpu_usage} className="mt-2" />
                      </CardContent>
                    </Card>

                    <Card className="bg-slate-800 border-slate-700">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-gray-400">Memory Usage</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="text-2xl font-bold text-white">
                          {systemStatus.memory_usage.toFixed(1)}%
                        </div>
                        <Progress value={systemStatus.memory_usage} className="mt-2" />
                      </CardContent>
                    </Card>

                    <Card className="bg-slate-800 border-slate-700">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-gray-400">Active Components</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="text-2xl font-bold text-white">
                          {systemStatus.components}
                        </div>
                        <p className="text-xs text-gray-400 mt-2">
                          {systemStatus.active_processes} processes
                        </p>
                      </CardContent>
                    </Card>

                    <Card className="bg-slate-800 border-slate-700">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-gray-400">Network Status</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="text-2xl font-bold text-white">
                          {systemStatus.network_status}
                        </div>
                        <Badge className="mt-2 bg-green-500">Connected</Badge>
                      </CardContent>
                    </Card>
                  </div>

                  {/* Tier Status Overview */}
                  <Card className="bg-slate-800 border-slate-700">
                    <CardHeader>
                      <CardTitle className="text-white">Tier Status Overview</CardTitle>
                      <CardDescription>All JARVIS tiers and their current status</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {tierStatuses.map((tier) => (
                          <Card key={tier.tier} className="bg-slate-700 border-slate-600">
                            <CardHeader className="pb-2">
                              <div className="flex items-center justify-between">
                                <CardTitle className="text-sm text-white">
                                  Tier {tier.tier}: {tier.name}
                                </CardTitle>
                                {getStatusBadge(tier.status)}
                              </div>
                            </CardHeader>
                            <CardContent>
                              <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                  <span className="text-xs text-gray-400">Performance</span>
                                  <span className="text-sm text-white">{tier.performance}%</span>
                                </div>
                                <Progress value={tier.performance} />
                                <div className="text-xs text-gray-400">
                                  {tier.features.slice(0, 2).join(', ')}
                                </div>
                              </div>
                            </CardContent>
                          </Card>
                        ))}
                      </div>
                    </CardContent>
                  </Card>

                  {/* Quick Actions */}
                  <Card className="bg-slate-800 border-slate-700">
                    <CardHeader>
                      <CardTitle className="text-white">Quick Actions</CardTitle>
                      <CardDescription>Frequently used operations</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <Button
                          className="bg-blue-600 hover:bg-blue-700"
                          onClick={() => setActiveTab("browser")}
                        >
                          <Globe className="w-4 h-4 mr-2" />
                          Open Browser
                        </Button>
                        <Button
                          className="bg-green-600 hover:bg-green-700"
                          onClick={() => setActiveTab("ide")}
                        >
                          <Code2 className="w-4 h-4 mr-2" />
                          Open IDE
                        </Button>
                        <Button
                          className="bg-purple-600 hover:bg-purple-700"
                          onClick={() => setActiveTab("chat")}
                        >
                          <MessageSquare className="w-4 h-4 mr-2" />
                          Start Chat
                        </Button>
                        <Button
                          className="bg-orange-600 hover:bg-orange-700"
                          onClick={() => setActiveTab("monitoring")}
                        >
                          <Monitor className="w-4 h-4 mr-2" />
                          View Monitor
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              )}

              {activeTab === "browser" && (
                <motion.div
                  key="browser"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <EmbeddedBrowser />
                </motion.div>
              )}

              {activeTab === "ide" && (
                <motion.div
                  key="ide"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <SelfReliantIDE />
                </motion.div>
              )}

              {activeTab === "chat" && (
                <motion.div
                  key="chat"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <RealAIChat />
                </motion.div>
              )}

              {activeTab === "advanced-agents" && (
                <motion.div
                  key="advanced-agents"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <AdvancedAgentOrchestration />
                </motion.div>
              )}

              {activeTab === "full-potential" && (
                <motion.div
                  key="full-potential"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <JarvisFullPotential />
                </motion.div>
              )}

              {activeTab === "3d-visualization" && (
                <motion.div
                  key="3d-visualization"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <Jarvis3DVisualization />
                </motion.div>
              )}

              {activeTab === "voice-interface" && (
                <motion.div
                  key="voice-interface"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <JarvisVoiceInterface />
                </motion.div>
              )}

              {activeTab === "v10-chambers" && (
                <motion.div
                  key="v10-chambers"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <JarvisV10Chambers />
                </motion.div>
              )}

              {activeTab === "holographic" && (
                <motion.div
                  key="holographic"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <JarvisHolographicInterface />
                </motion.div>
              )}

              {activeTab === "multidimensional" && (
                <motion.div
                  key="multidimensional"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <JarvisMultidimensionalViz />
                </motion.div>
              )}

              {activeTab === "tiers" && (
                <motion.div
                  key="tiers"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  className="space-y-6"
                >
                  <Card className="bg-slate-800 border-slate-700">
                    <CardHeader>
                      <CardTitle className="text-white">Tier Management</CardTitle>
                      <CardDescription>Manage and configure JARVIS tiers</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-4">
                        {tierStatuses.map((tier) => (
                          <div key={tier.tier} className="p-4 bg-slate-700 rounded-lg">
                            <div className="flex items-center justify-between mb-2">
                              <div className="flex items-center space-x-3">
                                <div className="p-2 bg-blue-500 rounded-lg">
                                  <Layers className="w-5 h-5 text-white" />
                                </div>
                                <div>
                                  <h3 className="text-white font-medium">
                                    Tier {tier.tier}: {tier.name}
                                  </h3>
                                  <p className="text-xs text-gray-400">
                                    Last updated: {new Date(tier.last_update).toLocaleString()}
                                  </p>
                                </div>
                              </div>
                              <div className="flex items-center space-x-2">
                                {getStatusBadge(tier.status)}
                                <Switch checked={tier.status === 'active'} />
                              </div>
                            </div>
                            <div className="space-y-2">
                              <div className="flex items-center justify-between">
                                <span className="text-sm text-gray-400">Performance</span>
                                <span className="text-sm text-white">{tier.performance}%</span>
                              </div>
                              <Progress value={tier.performance} />
                              <div className="flex flex-wrap gap-2 mt-2">
                                {tier.features.map((feature) => (
                                  <Badge key={feature} variant="secondary">
                                    {feature}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              )}

              {activeTab === "monitoring" && (
                <motion.div
                  key="monitoring"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <RealTimeMonitoring />
                </motion.div>
              )}

              {activeTab === "smarthome" && (
                <motion.div
                  key="smarthome"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <JarvisSmartHome />
                </motion.div>
              )}

              {activeTab === "tools" && (
                <motion.div
                  key="tools"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <JarvisTools />
                </motion.div>
              )}

              {activeTab === "settings" && (
                <motion.div
                  key="settings"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <JarvisSettings />
                </motion.div>
              )}

              {activeTab === "advanced" && (
                <motion.div
                  key="advanced"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                >
                  <AdvancedPage />
                </motion.div>
              )}
            </AnimatePresence>
          </main>
        </div>
      </div>
    </div>
  );
}
