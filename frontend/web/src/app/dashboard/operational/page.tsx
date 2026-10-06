'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { 
  Brain, Activity, LayoutDashboard, Grid3x3, Maximize2, Minimize2,
  Settings, RefreshCw, Layers, Shield
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { SystemMetricsWidget } from '@/components/widgets/system-metrics-widget';
import { AIStatusWidget } from '@/components/widgets/ai-status-widget';
import { MemoryConsciousnessWidget } from '@/components/widgets/memory-consciousness-widget';
import { AgentStatusWidget } from '@/components/widgets/agent-status-widget';
import { HealthMonitorWidget } from '@/components/widgets/health-monitor-widget';
import { KnowledgeGraphVisualization } from '@/components/knowledge-graph-visualization';
import { NeuralActivityMap } from '@/components/neural-activity-map';

export default function OperationalDashboardPage() {
  const [viewMode, setViewMode] = useState<'grid' | 'expanded'>('grid');
  const [activeTab, setActiveTab] = useState('overview');
  const [refreshKey, setRefreshKey] = useState(0);

  const handleRefresh = () => {
    setRefreshKey(prev => prev + 1);
  };

  return (
    <div className="min-h-screen bg-[#0a0e27] relative overflow-hidden">
      {/* Animated Background */}
      <div className="absolute inset-0 opacity-20">
        <div className="absolute inset-0" style={{
          backgroundImage: `
            linear-gradient(rgba(59, 130, 246, 0.1) 1px, transparent 1px),
            linear-gradient(90deg, rgba(59, 130, 246, 0.1) 1px, transparent 1px)
          `,
          backgroundSize: '50px 50px',
        }} />
      </div>

      {/* Glowing Orbs */}
      <div className="absolute top-20 left-20 w-96 h-96 bg-blue-500/20 rounded-full blur-3xl animate-pulse" />
      <div className="absolute bottom-20 right-20 w-96 h-96 bg-cyan-500/20 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />

      <div className="container mx-auto px-6 py-8 max-w-[1800px] relative z-10">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-6">
              <div className="relative group">
                <div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-blue-500 via-cyan-400 to-blue-600 flex items-center justify-center shadow-2xl shadow-blue-500/50">
                  <LayoutDashboard className="h-8 w-8 text-white" />
                </div>
                <div className="absolute -inset-3 rounded-2xl bg-gradient-to-br from-blue-500/30 via-cyan-400/30 to-blue-600/30 blur-2xl animate-pulse" />
              </div>
              <div>
                <h1 className="text-4xl font-black bg-gradient-to-r from-blue-400 via-cyan-300 to-blue-400 bg-clip-text text-transparent">
                  JARVIS Operational Dashboard
                </h1>
                <p className="text-cyan-200/80 mt-1 text-base">
                  Real-time system monitoring and AI orchestration
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Button
                onClick={handleRefresh}
                variant="outline"
                size="sm"
                className="bg-slate-900/60 border-blue-500/30 text-cyan-300 hover:bg-blue-500/20"
              >
                <RefreshCw className="h-4 w-4 mr-2" />
                Refresh
              </Button>
              <Button
                onClick={() => setViewMode(viewMode === 'grid' ? 'expanded' : 'grid')}
                variant="outline"
                size="sm"
                className="bg-slate-900/60 border-blue-500/30 text-cyan-300 hover:bg-blue-500/20"
              >
                {viewMode === 'grid' ? (
                  <>
                    <Maximize2 className="h-4 w-4 mr-2" />
                    Expand
                  </>
                ) : (
                  <>
                    <Minimize2 className="h-4 w-4 mr-2" />
                    Grid
                  </>
                )}
              </Button>
              <Badge variant="outline" className="bg-emerald-500/20 text-emerald-300 border-emerald-400/50">
                <span className="w-2 h-2 rounded-full bg-emerald-400 mr-2 animate-pulse" />
                Live
              </Badge>
            </div>
          </div>

          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="bg-slate-900/60 border-2 border-blue-500/30 backdrop-blur-xl p-1">
              <TabsTrigger value="overview" className="text-sm data-[state=active]:bg-gradient-to-r data-[state=active]:from-blue-500 data-[state=active]:to-cyan-500 data-[state=active]:text-white">
                <Activity className="h-4 w-4 mr-2" />
                Overview
              </TabsTrigger>
              <TabsTrigger value="knowledge" className="text-sm data-[state=active]:bg-gradient-to-r data-[state=active]:from-purple-500 data-[state=active]:to-pink-500 data-[state=active]:text-white">
                <Brain className="h-4 w-4 mr-2" />
                Knowledge Graph
              </TabsTrigger>
              <TabsTrigger value="neural" className="text-sm data-[state=active]:bg-gradient-to-r data-[state=active]:from-amber-500 data-[state=active]:to-orange-500 data-[state=active]:text-white">
                <Layers className="h-4 w-4 mr-2" />
                Neural Activity
              </TabsTrigger>
            </TabsList>

            {/* Overview Tab */}
            <TabsContent value="overview" className="mt-6">
              {viewMode === 'grid' ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.05 }}
                  >
                    <HealthMonitorWidget />
                  </motion.div>

                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.1 }}
                  >
                    <SystemMetricsWidget key={`system-${refreshKey}`} />
                  </motion.div>

                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.15 }}
                  >
                    <AIStatusWidget key={`ai-${refreshKey}`} />
                  </motion.div>

                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.2 }}
                  >
                    <MemoryConsciousnessWidget key={`memory-${refreshKey}`} />
                  </motion.div>

                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.25 }}
                    className="md:col-span-2"
                  >
                    <AgentStatusWidget key={`agent-${refreshKey}`} />
                  </motion.div>
                </div>
              ) : (
                <div className="space-y-6">
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <HealthMonitorWidget />
                    <SystemMetricsWidget key={`system-${refreshKey}`} />
                    <AIStatusWidget key={`ai-${refreshKey}`} />
                  </div>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <MemoryConsciousnessWidget key={`memory-${refreshKey}`} />
                    <AgentStatusWidget key={`agent-${refreshKey}`} />
                  </div>
                </div>
              )}

              {/* Quick Stats Bar */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 }}
                className="mt-6 p-6 rounded-xl bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-blue-500/30 backdrop-blur-xl"
              >
                <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
                  <div className="text-center">
                    <p className="text-xs text-cyan-200/70 mb-2">System Status</p>
                    <Badge className="bg-emerald-500/20 text-emerald-300 border-emerald-400/50">
                      Operational
                    </Badge>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-cyan-200/70 mb-2">AI Models</p>
                    <p className="text-2xl font-bold text-white">8+</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-cyan-200/70 mb-2">Knowledge Base</p>
                    <p className="text-2xl font-bold text-white">Active</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-cyan-200/70 mb-2">Autonomous Mode</p>
                    <Badge className="bg-blue-500/20 text-blue-300 border-blue-400/50">
                      Enabled
                    </Badge>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-cyan-200/70 mb-2">Security</p>
                    <div className="flex items-center justify-center gap-1">
                      <Shield className="h-4 w-4 text-emerald-400" />
                      <span className="text-lg font-bold text-white">Active</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            </TabsContent>

            {/* Knowledge Graph Tab */}
            <TabsContent value="knowledge" className="mt-6">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <KnowledgeGraphVisualization height={700} />
              </motion.div>
            </TabsContent>

            {/* Neural Activity Tab */}
            <TabsContent value="neural" className="mt-6">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <NeuralActivityMap height={700} autoRefresh refreshInterval={3000} />
              </motion.div>
            </TabsContent>
          </Tabs>
        </motion.div>

        {/* Footer */}
        <div className="mt-12 text-center">
          <div className="inline-block p-4 rounded-xl bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-blue-500/30 backdrop-blur-xl">
            <p className="text-cyan-200 font-semibold text-sm">
              JARVIS v3.0 • Smart Dashboard Engine • Phase 5 OMEGA Core
            </p>
            <p className="mt-1 text-xs text-cyan-200/60">
              Real-time monitoring • Contextual dashboards • AI-powered insights
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
