"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Atom, Brain, TrendingUp, Shield, Users, Globe, Sparkles,
  Zap, Activity, Database, Network, Cpu, Layers, ChevronRight,
  Settings, Play, Pause, RotateCw, Maximize2, Minimize2
} from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

interface Chamber {
  id: string;
  name: string;
  type: string;
  status: "active" | "idle" | "maintenance";
  capacity: number;
  activeTasks: number;
  completedTasks: number;
  metrics: Record<string, number>;
  icon: any;
  color: string;
}

export default function JarvisV10Chambers() {
  const [chambers, setChambers] = useState<Chamber[]>([
    {
      id: "quantum",
      name: "Quantum Computing Chamber",
      type: "quantum_computing",
      status: "active",
      capacity: 1,
      activeTasks: 1,
      completedTasks: 234,
      metrics: { qubits: 64, coherence: 0.95, entanglement: 0.88 },
      icon: Atom,
      color: "purple"
    },
    {
      id: "neural",
      name: "Neural Training Chamber",
      type: "neural_training",
      status: "active",
      capacity: 10,
      activeTasks: 3,
      completedTasks: 156,
      metrics: { models: 156, accuracy: 0.9678, loss: 0.0234 },
      icon: Brain,
      color: "pink"
    },
    {
      id: "predictive",
      name: "Predictive Analytics Chamber",
      type: "predictive_analytics",
      status: "active",
      capacity: 5,
      activeTasks: 2,
      completedTasks: 89,
      metrics: { predictions: 89, confidence: 0.94, uncertainty: 0.06 },
      icon: TrendingUp,
      color: "cyan"
    },
    {
      id: "security",
      name: "Advanced Security Chamber",
      type: "security",
      status: "idle",
      capacity: 1,
      activeTasks: 0,
      completedTasks: 412,
      metrics: { threats_blocked: 412, security_level: 0.99 },
      icon: Shield,
      color: "red"
    },
    {
      id: "collaborative",
      name: "Collaborative Workspace",
      type: "collaborative",
      status: "active",
      capacity: 50,
      activeTasks: 12,
      completedTasks: 567,
      metrics: { users: 12, sessions: 567, collaboration_score: 0.92 },
      icon: Users,
      color: "green"
    },
    {
      id: "global",
      name: "Global Monitoring Chamber",
      type: "global_monitoring",
      status: "active",
      capacity: 1,
      activeTasks: 1,
      completedTasks: 0,
      metrics: { regions: 24, alerts: 3, uptime: 99.9 },
      icon: Globe,
      color: "blue"
    }
  ]);

  const [selectedChamber, setSelectedChamber] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    // Simulate real-time updates
    const interval = setInterval(() => {
      setChambers(prev => prev.map(chamber => ({
        ...chamber,
        metrics: {
          ...chamber.metrics,
          ...(chamber.type === "quantum_computing" && {
            coherence: Math.random() * 0.1 + 0.9,
            entanglement: Math.random() * 0.15 + 0.85
          }),
          ...(chamber.type === "neural_training" && {
            accuracy: Math.random() * 0.05 + 0.93,
            loss: Math.random() * 0.01 + 0.02
          })
        }
      })));
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status: string) => {
    switch (status) {
      case "active": return "bg-green-500";
      case "idle": return "bg-gray-500";
      case "maintenance": return "bg-yellow-500";
      default: return "bg-gray-500";
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-purple-950 to-slate-950 p-6 space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-4xl font-bold bg-gradient-to-r from-purple-400 via-pink-400 to-cyan-400 bg-clip-text text-transparent">
            JARVIS Version 10.0
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            Advanced Virtual Chambers System
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge className="bg-purple-500 text-white px-4 py-2">
            <Sparkles className="w-4 h-4 mr-2" />
            Version 10.0
          </Badge>
          <Button
            variant="outline"
            onClick={() => setIsExpanded(!isExpanded)}
          >
            {isExpanded ? <Minimize2 className="w-4 h-4 mr-2" /> : <Maximize2 className="w-4 h-4 mr-2" />}
            {isExpanded ? "Compact" : "Expand"}
          </Button>
        </div>
      </motion.div>

      {/* Chambers Grid */}
      <div className={`grid ${isExpanded ? "grid-cols-1 md:grid-cols-2 lg:grid-cols-3" : "grid-cols-1 md:grid-cols-2 lg:grid-cols-3"} gap-6`}>
        {chambers.map((chamber, idx) => (
          <motion.div
            key={chamber.id}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: idx * 0.1 }}
          >
            <Card 
              className={`bg-white/[0.02] border-white/5 hover:border-${chamber.color}-500/30 transition-all cursor-pointer ${
                selectedChamber === chamber.id ? `border-${chamber.color}-500 ring-1 ring-${chamber.color}-500/20` : ""
              }`}
              onClick={() => setSelectedChamber(chamber.id)}
            >
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`p-3 bg-${chamber.color}-500/20 rounded-lg`}>
                      <chamber.icon className={`w-6 h-6 text-${chamber.color}-400`} />
                    </div>
                    <div>
                      <CardTitle className="text-lg">{chamber.name}</CardTitle>
                      <CardDescription className="text-xs">
                        {chamber.type.replace(/_/g, " ").toUpperCase()}
                      </CardDescription>
                    </div>
                  </div>
                  <Badge className={getStatusColor(chamber.status)}>
                    {chamber.status}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Capacity */}
                <div>
                  <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
                    <span>Capacity</span>
                    <span>{chamber.activeTasks}/{chamber.capacity}</span>
                  </div>
                  <Progress 
                    value={(chamber.activeTasks / chamber.capacity) * 100} 
                    className="h-2"
                  />
                </div>

                {/* Metrics */}
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(chamber.metrics).map(([key, value]) => (
                    <div key={key} className="p-2 bg-white/[0.02] rounded">
                      <div className="text-xs text-gray-400 capitalize">{key.replace(/_/g, " ")}</div>
                      <div className="text-sm font-bold text-white">
                        {typeof value === "number" ? value.toFixed(2) : value}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Stats */}
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-400">Completed: {chamber.completedTasks}</span>
                  <Button variant="ghost" size="sm" className="h-6">
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Selected Chamber Detail */}
      <AnimatePresence>
        {selectedChamber && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
          >
            {(() => {
              const chamber = chambers.find(c => c.id === selectedChamber);
              if (!chamber) return null;
              const Icon = chamber.icon;
              
              return (
                <Card className="bg-white/[0.02] border-white/5">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className={`p-4 bg-${chamber.color}-500/20 rounded-xl`}>
                          <Icon className={`w-8 h-8 text-${chamber.color}-400`} />
                        </div>
                        <div>
                          <CardTitle className="text-2xl">{chamber.name}</CardTitle>
                          <CardDescription>
                            {chamber.type.replace(/_/g, " ").toUpperCase()} • Version 10.0
                          </CardDescription>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button variant="outline" size="icon">
                          <Settings className="w-4 h-4" />
                        </Button>
                        <Button variant="outline" size="icon">
                          <RotateCw className="w-4 h-4" />
                        </Button>
                        <Button
                          variant={chamber.status === "active" ? "destructive" : "default"}
                          size="icon"
                        >
                          {chamber.status === "active" ? (
                            <Pause className="w-4 h-4" />
                          ) : (
                            <Play className="w-4 h-4" />
                          )}
                        </Button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                      {/* Performance Metrics */}
                      <div className="space-y-4">
                        <h3 className="text-sm font-semibold text-gray-400">Performance Metrics</h3>
                        <div className="space-y-3">
                          {Object.entries(chamber.metrics).map(([key, value]) => (
                            <div key={key} className="flex items-center justify-between">
                              <span className="text-sm text-gray-400 capitalize">{key.replace(/_/g, " ")}</span>
                              <span className="text-sm font-bold text-white">
                                {typeof value === "number" ? value.toFixed(2) : value}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Activity Graph */}
                      <div className="space-y-4">
                        <h3 className="text-sm font-semibold text-gray-400">Activity Graph</h3>
                        <div className="h-32 flex items-end gap-1">
                          {Array.from({ length: 20 }).map((_, i) => (
                            <motion.div
                              key={i}
                              animate={{ height: Math.random() * 100 + "%" }}
                              className={`flex-1 bg-${chamber.color}-500/50 rounded-t`}
                              style={{ animationDelay: `${i * 0.1}s` }}
                            />
                          ))}
                        </div>
                      </div>

                      {/* Quick Actions */}
                      <div className="space-y-4">
                        <h3 className="text-sm font-semibold text-gray-400">Quick Actions</h3>
                        <div className="space-y-2">
                          <Button variant="outline" className="w-full justify-start">
                            <Activity className="w-4 h-4 mr-2" />
                            View Activity Log
                          </Button>
                          <Button variant="outline" className="w-full justify-start">
                            <Database className="w-4 h-4 mr-2" />
                            Export Data
                          </Button>
                          <Button variant="outline" className="w-full justify-start">
                            <Network className="w-4 h-4 mr-2" />
                            Configure Network
                          </Button>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })()}
          </motion.div>
        )}
      </AnimatePresence>

      {/* System Overview */}
      <Card className="bg-gradient-to-r from-purple-500/10 via-pink-500/10 to-cyan-500/10 border-white/5">
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
              >
                <div className="p-3 bg-gradient-to-r from-purple-500 to-pink-500 rounded-full">
                  <Cpu className="w-6 h-6 text-white" />
                </div>
              </motion.div>
              <div>
                <h3 className="text-xl font-bold text-white">JARVIS Version 10.0 System</h3>
                <p className="text-sm text-gray-400">Advanced Virtual Chambers • AI-Driven Execution</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <div className="text-xs text-gray-400">Active Chambers</div>
                <div className="text-2xl font-bold text-white">
                  {chambers.filter(c => c.status === "active").length}
                </div>
              </div>
              <div className="text-right">
                <div className="text-xs text-gray-400">Total Tasks</div>
                <div className="text-2xl font-bold text-white">
                  {chambers.reduce((sum, c) => sum + c.completedTasks, 0)}
                </div>
              </div>
              <Badge className="bg-green-500 text-white px-4 py-2">
                <Activity className="w-4 h-4 mr-2" />
                All Systems Operational
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
