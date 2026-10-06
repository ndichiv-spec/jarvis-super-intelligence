import React from 'react';
import { motion } from 'framer-motion';
import { Command, Activity, Gauge } from 'lucide-react';

export function JarvisCapabilitiesOverview() {
  return (
    <div className="h-full flex flex-col bg-gray-800 rounded-xl p-6">
      <div className="flex items-center space-x-2 mb-6">
        <Command className="w-6 h-6 text-purple-400" />
        <h2 className="text-xl font-semibold text-white">All Capabilities</h2>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[
          { name: 'Neural Processing', status: 'active', performance: 95 },
          { name: 'Data Analysis', status: 'active', performance: 88 },
          { name: 'Natural Language', status: 'active', performance: 92 },
          { name: 'Computer Vision', status: 'beta', performance: 76 },
          { name: 'Predictive Models', status: 'active', performance: 84 },
          { name: 'Autonomous Control', status: 'experimental', performance: 67 }
        ].map((capability, index) => (
          <motion.div
            key={capability.name}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: index * 0.1 }}
            className="bg-gray-700 p-4 rounded-lg hover:bg-gray-600 transition-colors cursor-pointer"
          >
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-medium text-white">{capability.name}</h3>
              <div className={`w-2 h-2 rounded-full ${
                capability.status === 'active' ? 'bg-green-400' :
                capability.status === 'beta' ? 'bg-yellow-400' : 'bg-red-400'
              }`} />
            </div>
            <div className="flex items-center space-x-2 text-sm text-gray-400">
              <Activity className="w-4 h-4" />
              <span>{capability.performance}%</span>
            </div>
            <div className="mt-2">
              <div className="w-full bg-gray-600 rounded-full h-2">
                <div 
                  className="bg-gradient-to-r from-blue-400 to-purple-400 h-2 rounded-full"
                  style={{ width: `${capability.performance}%` }}
                />
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
