'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Bot, CheckCircle2, AlertCircle, TrendingUp } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';

interface AgentStatus {
  active_agents: number;
  running_tasks: number;
  completed_tasks: number;
  success_rate: number;
}

export function AgentStatusWidget() {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await fetch('/api/v1/dashboard/widgets/data/agent-status');
        const data = await response.json();
        
        if (data.success) {
          setStatus(data.status);
        }
      } catch (error) {
        console.error('Failed to fetch agent status:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 10000); // Update every 10 seconds
    
    return () => clearInterval(interval);
  }, []);

  if (loading || !status) {
    return (
      <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-blue-500/30 backdrop-blur-xl">
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2 text-white">
            <Bot className="h-4 w-4 text-emerald-400 animate-pulse" />
            Agent Orchestration
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
      <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-emerald-500/30 backdrop-blur-xl hover:border-emerald-400/50 transition-all duration-300">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center justify-between text-white">
            <div className="flex items-center gap-2">
              <Bot className="h-4 w-4 text-emerald-400" />
              Agent Orchestration
            </div>
            <Badge variant="outline" className="bg-emerald-500/20 text-emerald-300 border-emerald-400/50 text-[10px]">
              Active
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Agents & Tasks */}
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
              <div className="flex items-center gap-2 mb-2">
                <Bot className="h-3 w-3 text-emerald-400" />
                <span className="text-[10px] text-cyan-200/70">Active Agents</span>
              </div>
              <p className="text-2xl font-bold text-white">{status.active_agents}</p>
              <p className="text-[10px] text-emerald-200/50 mt-1">online</p>
            </div>

            <div className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/20">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp className="h-3 w-3 text-blue-400" />
                <span className="text-[10px] text-cyan-200/70">Running Tasks</span>
              </div>
              <p className="text-2xl font-bold text-white">{status.running_tasks}</p>
              <p className="text-[10px] text-blue-200/50 mt-1">in progress</p>
            </div>
          </div>

          {/* Completed Tasks */}
          <div className="p-3 rounded-lg bg-purple-500/10 border border-purple-500/20">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-3 w-3 text-purple-400" />
                <span className="text-xs text-cyan-200/70">Completed Tasks</span>
              </div>
              <span className="text-lg font-bold text-white">{status.completed_tasks}</span>
            </div>
            <Progress value={100} className="h-1 bg-purple-500" />
          </div>

          {/* Success Rate */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                <span className="text-xs text-cyan-200/70">Success Rate</span>
              </div>
              <span className={`text-sm font-bold ${
                status.success_rate >= 0.9 ? 'text-emerald-400' :
                status.success_rate >= 0.75 ? 'text-amber-400' :
                'text-red-400'
              }`}>
                {Math.round(status.success_rate * 100)}%
              </span>
            </div>
            <Progress 
              value={status.success_rate * 100} 
              className={`h-2 ${
                status.success_rate >= 0.9 ? 'bg-emerald-500' :
                status.success_rate >= 0.75 ? 'bg-amber-500' :
                'bg-red-500'
              }`} 
            />
          </div>

          {/* Status Indicator */}
          <div className="pt-2 border-t border-emerald-500/20">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {status.success_rate >= 0.9 ? (
                  <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                ) : (
                  <AlertCircle className="h-3 w-3 text-amber-400" />
                )}
                <span className="text-xs text-cyan-200/70">System Health</span>
              </div>
              <Badge 
                variant="outline" 
                className={`text-[10px] ${
                  status.success_rate >= 0.9 
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-400/50' 
                    : 'bg-amber-500/20 text-amber-300 border-amber-400/50'
                }`}
              >
                {status.success_rate >= 0.9 ? 'Excellent' : 'Good'}
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
