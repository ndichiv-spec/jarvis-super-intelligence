import React from 'react';
import { motion } from 'framer-motion';
import { Brain, Zap, Shield, Activity, TrendingUp } from 'lucide-react';

export function JarvisSuperiorDashboard() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-blue-900 to-purple-900 text-white p-8">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-w-7xl mx-auto"
      >
        <div className="text-center mb-12">
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.2 }}
            className="inline-flex items-center justify-center w-20 h-20 bg-blue-500 rounded-full mb-6"
          >
            <Brain className="w-10 h-10" />
          </motion.div>
          <h1 className="text-5xl font-bold mb-4 bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
            JARVIS Superior Dashboard
          </h1>
          <p className="text-xl text-gray-300">Advanced AI System Control Center</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
          {[
            { icon: Zap, label: 'Power', value: '98%', color: 'from-yellow-400 to-orange-400' },
            { icon: Shield, label: 'Security', value: 'Active', color: 'from-green-400 to-emerald-400' },
            { icon: Activity, label: 'Performance', value: 'Optimal', color: 'from-blue-400 to-cyan-400' },
            { icon: TrendingUp, label: 'Efficiency', value: '94%', color: 'from-purple-400 to-pink-400' },
          ].map((stat, index) => (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 * index }}
              className={`bg-gradient-to-r ${stat.color} p-6 rounded-2xl shadow-2xl`}
            >
              <stat.icon className="w-8 h-8 mb-4" />
              <h3 className="text-lg font-semibold mb-2">{stat.label}</h3>
              <p className="text-2xl font-bold">{stat.value}</p>
            </motion.div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.5 }}
            className="bg-gray-800/50 backdrop-blur-lg p-8 rounded-2xl border border-gray-700"
          >
            <h2 className="text-2xl font-bold mb-6">System Status</h2>
            <div className="space-y-4">
              {[
                'Neural Networks: Online',
                'Data Processing: Active',
                'Security Protocols: Enabled',
                'AI Models: Operational',
              ].map((status, index) => (
                <div key={index} className="flex items-center justify-between">
                  <span className="text-gray-300">{status}</span>
                  <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.6 }}
            className="bg-gray-800/50 backdrop-blur-lg p-8 rounded-2xl border border-gray-700"
          >
            <h2 className="text-2xl font-bold mb-6">Active Capabilities</h2>
            <div className="grid grid-cols-2 gap-4">
              {[
                'Natural Language',
                'Computer Vision',
                'Predictive Analysis',
                'Autonomous Control',
              ].map((capability, index) => (
                <div
                  key={capability}
                  className="bg-gray-700/50 p-3 rounded-lg text-center hover:bg-gray-700 transition-colors cursor-pointer"
                >
                  <p className="text-sm font-medium">{capability}</p>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </motion.div>
    </div>
  );
}
