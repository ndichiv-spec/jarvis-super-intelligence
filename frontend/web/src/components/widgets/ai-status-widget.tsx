'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Brain, Zap, Clock, CheckCircle2, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';

interface AIStatus {
  status: string;
  model: string;
  uptime: string;
  requests_processed: number;
  avg_response_time_ms: number;
}

export function AIStatusWidget() {
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [consecutiveErrors, setConsecutiveErrors] = useState(0);

  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/dashboard/widgets/data/ai-status', {
        method: 'GET',
        headers: {
          'Cache-Control': 'no-cache',
        },
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const data = await response.json();
      
      if (data.success) {
        setStatus(data.status);
        setError(null);
        setConsecutiveErrors(0);
      } else {
        throw new Error(data.message || 'Failed to fetch AI status');
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error';
      console.error('Failed to fetch AI status:', errorMsg);
      setError(errorMsg);
      setConsecutiveErrors(prev => prev + 1);
      
      // Show toast notification after 3 consecutive errors
      if (consecutiveErrors >= 2) {
        toast.error('AI Engine Unreachable', {
          description: 'Cannot connect to AI backend. Check if Ollama is running.',
        });
      }
    } finally {
      setLoading(false);
    }
  }, [consecutiveErrors]);

  useEffect(() => {
    fetchStatus();
    
    // Adaptive polling: faster when errors occur
    const pollInterval = consecutiveErrors > 0 ? 3000 : 10000;
    const interval = setInterval(fetchStatus, pollInterval);
    
    return () => clearInterval(interval);
  }, [fetchStatus, consecutiveErrors]);

  if (error && !status) {
    return (
      <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-red-500/30 backdrop-blur-xl">
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2 text-white">
            <AlertTriangle className="h-4 w-4 text-red-400" />
            AI Engine Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <div className="text-center space-y-2">
              <AlertTriangle className="h-8 w-8 text-red-400 mx-auto" />
              <p className="text-xs text-red-300">Connection Error</p>
              <button
                onClick={fetchStatus}
                className="text-xs text-blue-400 hover:text-blue-300 underline"
              >
                Retry
              </button>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (loading || !status) {
    return (
      <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-blue-500/30 backdrop-blur-xl">
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2 text-white">
            <Brain className="h-4 w-4 text-purple-400 animate-pulse" />
            AI Engine Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-2">
            <div className="h-4 bg-slate-700 rounded w-1/2" />
            <div className="h-4 bg-slate-700 rounded w-3/4" />
            <div className="h-4 bg-slate-700 rounded w-2/3" />
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
      <Card className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-purple-500/30 backdrop-blur-xl hover:border-purple-400/50 transition-all duration-300">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center justify-between text-white">
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-purple-400" />
              AI Engine Status
            </div>
            <Badge 
              variant="outline" 
              className={`text-[10px] ${
                status.status === 'online' 
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-400/50' 
                  : 'bg-red-500/20 text-red-300 border-red-400/50'
              }`}
            >
              <span className={`w-2 h-2 rounded-full mr-2 inline-block ${
                status.status === 'online' ? 'bg-emerald-400' : 'bg-red-400'
              }`} />
              {status.status}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Model Info */}
          <div className="p-3 rounded-lg bg-purple-500/10 border border-purple-500/20">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-purple-200/70">Active Model</span>
              <Badge variant="outline" className="bg-purple-500/20 text-purple-300 border-purple-400/50 text-[10px]">
                {status.model}
              </Badge>
            </div>
            <div className="flex items-center gap-2">
              <Zap className="h-3 w-3 text-yellow-400" />
              <span className="text-xs text-purple-200/60">Multi-model routing enabled</span>
            </div>
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-2 gap-3">
            <div className="p-2 rounded-lg bg-slate-800/50 border border-blue-500/20">
              <div className="flex items-center gap-2 mb-1">
                <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                <span className="text-[10px] text-cyan-200/70">Requests</span>
              </div>
              <p className="text-lg font-bold text-white">{status.requests_processed.toLocaleString()}</p>
            </div>

            <div className="p-2 rounded-lg bg-slate-800/50 border border-blue-500/20">
              <div className="flex items-center gap-2 mb-1">
                <Clock className="h-3 w-3 text-amber-400" />
                <span className="text-[10px] text-cyan-200/70">Avg Response</span>
              </div>
              <p className="text-lg font-bold text-white">{status.avg_response_time_ms}ms</p>
            </div>
          </div>

          {/* Uptime */}
          <div className="pt-2 border-t border-purple-500/20">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Clock className="h-3 w-3 text-cyan-400" />
                <span className="text-xs text-cyan-200/70">Uptime</span>
              </div>
              <span className="text-sm font-bold text-white">{status.uptime}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
