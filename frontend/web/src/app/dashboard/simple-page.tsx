'use client';

import React from 'react';
import { motion } from 'framer-motion';

export default function SimpleDashboardPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-blue-900 to-purple-900">
      <div className="container mx-auto px-6 py-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-center mb-12"
        >
          <h1 className="text-6xl font-bold bg-gradient-to-r from-blue-400 to-purple-600 bg-clip-text text-transparent mb-4">
            JARVIS Quantum
          </h1>
          <p className="text-xl text-gray-300">
            Advanced AI Interface - Super Intelligence Platform
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {[
            { title: 'Neural Processing', value: '98.7%', color: 'from-blue-500 to-cyan-400' },
            { title: 'Quantum Speed', value: '0.001ms', color: 'from-purple-500 to-pink-400' },
            { title: 'System Status', value: 'Online', color: 'from-green-500 to-emerald-400' }
          ].map((item, index) => (
            <motion.div
              key={item.title}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: index * 0.1 }}
              className="bg-white/10 backdrop-blur-lg rounded-xl p-8 border border-white/20"
            >
              <div className={`w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-r ${item.color}`}></div>
              <h3 className="text-xl font-bold text-white mb-2">{item.title}</h3>
              <p className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-purple-600 bg-clip-text text-transparent">
                {item.value}
              </p>
            </motion.div>
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="mt-12 bg-white/10 backdrop-blur-lg rounded-xl p-8 border border-white/20"
        >
          <h2 className="text-2xl font-bold text-white mb-6">System Features</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {[
              'Advanced AI Processing',
              'Quantum Computing Integration',
              'Real-time Neural Networks',
              'Autonomous Learning',
              'Multi-dimensional Analysis',
              'Predictive Intelligence'
            ].map((feature, index) => (
              <div key={feature} className="flex items-center space-x-3">
                <div className="w-3 h-3 bg-green-400 rounded-full animate-pulse"></div>
                <span className="text-gray-300">{feature}</span>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
