'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence, useScroll, useTransform } from 'framer-motion';
import { 
  Sparkles, Zap, Cpu, Activity, Layers, Database, Network, Users, Clock, Bell,
  Rocket, Target, Command, Code, GitBranch, Server, Cloud, Gauge, Brain,
  Flame, Sun, Moon, Star, Award, Trophy, Medal, Gem, Atom, Beaker,
  FlaskConical, TestTube, Heart, TrendingUp, ArrowUpRight, ChevronRight,
  Play, Pause, RefreshCw, Settings, Grid, List, Monitor, Wifi, X
} from 'lucide-react';

interface MetricCard {
  id: string;
  title: string;
  value: string;
  icon: any;
  trend: 'up' | 'down' | 'stable';
  color: string;
  gradient: string;
}

const METRICS: MetricCard[] = [
  {
    id: 'total-capabilities',
    title: 'Total Capabilities',
    value: '22',
    icon: Sparkles,
    trend: 'up',
    color: 'blue',
    gradient: 'from-blue-600 to-purple-600'
  },
  {
    id: 'active-systems',
    title: 'Active Systems',
    value: '7',
    icon: Cpu,
    trend: 'up',
    color: 'green',
    gradient: 'from-green-600 to-emerald-600'
  },
  {
    id: 'components',
    title: 'Components',
    value: '209',
    icon: Layers,
    trend: 'up',
    color: 'purple',
    gradient: 'from-purple-600 to-pink-600'
  },
  {
    id: 'ai-performance',
    title: 'AI Performance',
    value: '99.9%',
    icon: Brain,
    trend: 'up',
    color: 'orange',
    gradient: 'from-orange-600 to-red-600'
  }
];

const SYSTEMS = [
  { name: 'Swarm Intelligence', status: 'active', performance: 98, icon: Users },
  { name: 'Multimodal AI', status: 'active', performance: 95, icon: Layers },
  { name: 'Causal Reasoning', status: 'active', performance: 92, icon: GitBranch },
  { name: 'Auto Optimizer', status: 'active', performance: 97, icon: Gauge },
  { name: 'Quantum AI', status: 'active', performance: 89, icon: Atom },
  { name: 'Neuro-Symbolic', status: 'active', performance: 94, icon: Brain },
  { name: 'Knowledge Graph', status: 'active', performance: 96, icon: Network }
];

export default function JarvisSuperiorDashboard() {
  const [selectedSystem, setSelectedSystem] = useState<string | null>(null);
  const [isAnimating, setIsAnimating] = useState(true);
  const { scrollYProgress } = useScroll();
  const scale = useTransform(scrollYProgress, [0, 1], [1, 0.8]);
  const opacity = useTransform(scrollYProgress, [0, 1], [1, 0.5]);

  useEffect(() => {
    const interval = setInterval(() => {
      setIsAnimating(prev => !prev);
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 text-white overflow-hidden">
      {/* Animated Background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute w-96 h-96 bg-blue-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-blob top-0 left-0"></div>
        <div className="absolute w-96 h-96 bg-purple-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-blob animation-delay-2000 top-0 right-0"></div>
        <div className="absolute w-96 h-96 bg-pink-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-blob animation-delay-4000 bottom-0 left-1/2"></div>
      </div>

      <div className="relative z-10 p-8">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          className="mb-12"
        >
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-6xl font-bold mb-2 bg-gradient-to-r from-blue-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
                JARVIS Super AI
              </h1>
              <p className="text-xl text-gray-300 flex items-center">
                <Sparkles className="w-5 h-5 mr-2 text-yellow-400" />
                Limitless Capabilities • Superior Intelligence
              </p>
            </div>
            <motion.div
              animate={{ rotate: isAnimating ? 360 : 0 }}
              transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
              className="w-20 h-20 bg-gradient-to-br from-blue-600 to-purple-600 rounded-full flex items-center justify-center shadow-2xl"
            >
              <Brain className="w-10 h-10" />
            </motion.div>
          </div>
        </motion.div>

        {/* Metrics Grid */}
        <motion.div
          style={{ scale, opacity }}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12"
        >
          {METRICS.map((metric, index) => {
            const Icon = metric.icon;
            return (
              <motion.div
                key={metric.id}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: index * 0.1, duration: 0.5 }}
                whileHover={{ scale: 1.05, rotateY: 5 }}
                className={`relative group`}
              >
                <div className={`absolute inset-0 bg-gradient-to-r ${metric.gradient} rounded-2xl blur-xl opacity-50 group-hover:opacity-75 transition-opacity`}></div>
                <div className="relative bg-gray-900/80 backdrop-blur-xl p-6 rounded-2xl border border-gray-700/50">
                  <div className="flex items-start justify-between mb-4">
                    <div className={`w-14 h-14 bg-gradient-to-br ${metric.gradient} rounded-xl flex items-center justify-center shadow-lg`}>
                      <Icon className="w-7 h-7" />
                    </div>
                    <motion.div
                      animate={{ y: metric.trend === 'up' ? [0, -5, 0] : 0 }}
                      transition={{ duration: 2, repeat: Infinity }}
                    >
                      <ArrowUpRight className={`w-5 h-5 ${metric.trend === 'up' ? 'text-green-400' : 'text-red-400'}`} />
                    </motion.div>
                  </div>
                  <h3 className="text-3xl font-bold mb-1">{metric.value}</h3>
                  <p className="text-gray-400 text-sm">{metric.title}</p>
                </div>
              </motion.div>
            );
          })}
        </motion.div>

        {/* Systems Grid */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5, duration: 0.8 }}
          className="mb-12"
        >
          <h2 className="text-3xl font-bold mb-6 flex items-center">
            <Cpu className="w-8 h-8 mr-3 text-blue-400" />
            Advanced AI Systems
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {SYSTEMS.map((system, index) => {
              const Icon = system.icon;
              return (
                <motion.div
                  key={system.name}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.6 + index * 0.1, duration: 0.5 }}
                  whileHover={{ scale: 1.03, y: -5 }}
                  onClick={() => setSelectedSystem(system.name)}
                  className="cursor-pointer"
                >
                  <div className="relative group">
                    <div className="absolute inset-0 bg-gradient-to-r from-blue-600 to-purple-600 rounded-2xl blur-xl opacity-30 group-hover:opacity-50 transition-opacity"></div>
                    <div className="relative bg-gray-900/80 backdrop-blur-xl p-6 rounded-2xl border border-gray-700/50">
                      <div className="flex items-center justify-between mb-4">
                        <div className="w-12 h-12 bg-gradient-to-br from-blue-600 to-purple-600 rounded-xl flex items-center justify-center">
                          <Icon className="w-6 h-6" />
                        </div>
                        <div className={`px-3 py-1 rounded-full text-xs font-semibold ${
                          system.status === 'active' ? 'bg-green-600' : 'bg-yellow-600'
                        }`}>
                          {system.status}
                        </div>
                      </div>
                      <h3 className="text-xl font-bold mb-2">{system.name}</h3>
                      <div className="mb-3">
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-gray-400">Performance</span>
                          <span className="text-blue-400">{system.performance}%</span>
                        </div>
                        <div className="w-full bg-gray-700 rounded-full h-2">
                          <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${system.performance}%` }}
                            transition={{ duration: 1, delay: 0.8 + index * 0.1 }}
                            className="bg-gradient-to-r from-blue-600 to-purple-600 h-2 rounded-full"
                          />
                        </div>
                      </div>
                      <div className="flex items-center text-sm text-gray-400">
                        <ChevronRight className="w-4 h-4 mr-1" />
                        View Details
                      </div>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </motion.div>

        {/* Capabilities Showcase */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1, duration: 0.8 }}
        >
          <h2 className="text-3xl font-bold mb-6 flex items-center">
            <Command className="w-8 h-8 mr-3 text-purple-400" />
            Core Capabilities
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { icon: Code, name: 'Multi-Model AI', desc: 'Claude, OpenAI, Gemini, Ollama' },
              { icon: Layers, name: 'Entity Layer', desc: 'Auto-CRUD Database System' },
              { icon: Server, name: 'Microservices', desc: 'Distributed Architecture' },
              { icon: Wifi, name: 'Real-time', desc: 'WebSocket Streaming' },
              { icon: Beaker, name: 'Skills System', desc: 'Web Search, Weather, Smart Home' },
              { icon: FlaskConical, name: 'Testing Suite', desc: 'Automated Validation' },
              { icon: Rocket, name: 'Deployment', desc: 'Container & Scaling' },
              { icon: Trophy, name: 'Performance', desc: 'Auto-Optimization' }
            ].map((item, index) => {
              const Icon = item.icon;
              return (
                <motion.div
                  key={item.name}
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 1.1 + index * 0.05, duration: 0.4 }}
                  whileHover={{ scale: 1.05, y: -3 }}
                  className="bg-gray-900/60 backdrop-blur-xl p-4 rounded-xl border border-gray-700/50 hover:border-purple-500/50 transition-colors"
                >
                  <div className="w-10 h-10 bg-gradient-to-br from-purple-600 to-pink-600 rounded-lg flex items-center justify-center mb-3">
                    <Icon className="w-5 h-5" />
                  </div>
                  <h3 className="font-semibold mb-1">{item.name}</h3>
                  <p className="text-xs text-gray-400">{item.desc}</p>
                </motion.div>
              );
            })}
          </div>
        </motion.div>

        {/* Floating Action Button */}
        <motion.div
          className="fixed bottom-8 right-8"
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ delay: 1.5, type: "spring", stiffness: 200 }}
        >
          <motion.button
            whileHover={{ scale: 1.1, rotate: 90 }}
            whileTap={{ scale: 0.9 }}
            className="w-16 h-16 bg-gradient-to-br from-blue-600 to-purple-600 rounded-full flex items-center justify-center shadow-2xl"
          >
            <Settings className="w-8 h-8" />
          </motion.button>
        </motion.div>
      </div>

      {/* System Detail Modal */}
      <AnimatePresence>
        {selectedSystem && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4"
            onClick={() => setSelectedSystem(null)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="bg-gray-900 p-8 rounded-2xl max-w-2xl w-full border border-gray-700"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-2xl font-bold">{selectedSystem}</h2>
                <button
                  onClick={() => setSelectedSystem(null)}
                  className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
                >
                  <X className="w-6 h-6" />
                </button>
              </div>
              <div className="space-y-4">
                <div className="bg-gray-800 p-4 rounded-xl">
                  <h3 className="font-semibold mb-2">Status</h3>
                  <div className="flex items-center">
                    <div className="w-3 h-3 bg-green-500 rounded-full mr-2 animate-pulse"></div>
                    <span>Active and Operational</span>
                  </div>
                </div>
                <div className="bg-gray-800 p-4 rounded-xl">
                  <h3 className="font-semibold mb-2">Performance Metrics</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <div className="text-gray-400 text-sm">Accuracy</div>
                      <div className="text-2xl font-bold text-green-400">99.9%</div>
                    </div>
                    <div>
                      <div className="text-gray-400 text-sm">Response Time</div>
                      <div className="text-2xl font-bold text-blue-400">12ms</div>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
