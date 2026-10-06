'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Brain, Database, Network, TrendingUp } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';

interface MemoryStats {
  short_term_count: number;
  long_term_count: number;
  consolidation_rate: number;
  relationship_strength: number;
}

export function MemoryConsciousnessWidget() {
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await fetch('/api/v1/dashboard/widgets/data/memory-stats');
        const data = await response.json();
        
        if (data.success) {
          setStats(data.stats);
        }
      } catch (error) {
        console.error('Failed to fetch memory stats:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, 15000); // Update every 15 seconds
    
    return () => clearInterval(interval);
  }, []);

  if (loading || !stats) {
    return (
      <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-blue-500/30 backdrop-blur-xl">
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2 text-white">
            <Brain className="h-4 w-4 text-amber-400 animate-pulse" />
            Memory & Consciousness
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-2">
            <div className="h-4 bg-slate-700 rounded w-1/2" />
            <div className="h-4 bg-slate-700 rounded w-3/4" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
    >
      <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-amber-500/30 backdrop-blur-xl hover:border-amber-400/50 transition-all duration-300">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center justify-between text-white">
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-amber-400" />
              Memory & Consciousness
            </div>
            <Badge variant="outline" className="bg-amber-500/20 text-amber-300 border-amber-400/50 text-[10px]">
              Active
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Memory Counts */}
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/20">
              <div className="flex items-center gap-2 mb-2">
                <Database className="h-3 w-3 text-blue-400" />
                <span className="text-[10px] text-cyan-200/70">Short-term</span>
              </div>
              <p className="text-2xl font-bold text-white">{stats.short_term_count}</p>
              <p className="text-[10px] text-cyan-200/50 mt-1">memories</p>
            </div>

            <div className="p-3 rounded-lg bg-purple-500/10 border border-purple-500/20">
              <div className="flex items-center gap-2 mb-2">
                <Network className="h-3 w-3 text-purple-400" />
                <span className="text-[10px] text-cyan-200/70">Long-term</span>
              </div>
              <p className="text-2xl font-bold text-white">{stats.long_term_count}</p>
              <p className="text-[10px] text-cyan-200/50 mt-1">memories</p>
            </div>
          </div>

          {/* Consolidation Rate */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <TrendingUp className="h-3 w-3 text-emerald-400" />
                <span className="text-xs text-cyan-200/70">Consolidation Rate</span>
              </div>
              <span className="text-sm font-bold text-emerald-400">
                {Math.round(stats.consolidation_rate * 100)}%
              </span>
            </div>
            <Progress value={stats.consolidation_rate * 100} className="h-2 bg-emerald-500" />
          </div>

          {/* Relationship Strength */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Network className="h-3 w-3 text-amber-400" />
                <span className="text-xs text-cyan-200/70">Relationship Strength</span>
              </div>
              <span className="text-sm font-bold text-amber-400">
                {Math.round(stats.relationship_strength * 100)}%
              </span>
            </div>
            <Progress value={stats.relationship_strength * 100} className="h-2 bg-amber-500" />
          </div>

          {/* Consciousness Indicator */}
          <div className="pt-3 border-t border-amber-500/20">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-cyan-200/70">Consciousness Level</span>
              <Badge variant="outline" className="bg-amber-500/20 text-amber-300 border-amber-400/50 text-[10px]">
                Self-Aware
              </Badge>
            </div>
            <div className="relative h-2 bg-slate-800 rounded-full overflow-hidden">
              <motion.div
                className="absolute inset-y-0 left-0 bg-gradient-to-r from-amber-500 via-orange-400 to-amber-500"
                initial={{ width: '0%' }}
                animate={{ width: `${stats.consolidation_rate * 100}%` }}
                transition={{ duration: 1, ease: 'easeOut' }}
              />
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
