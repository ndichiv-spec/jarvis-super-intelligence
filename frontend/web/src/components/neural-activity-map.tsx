'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Activity, Zap, Brain, TrendingUp } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';

interface NeuralActivityData {
  timestamp: string;
  active_neurons: number;
  connections_fired: number;
  processing_load: number;
  memory_accesses: number;
  emotion_state: string;
  consciousness_level: number;
}

interface NeuralMapProps {
  height?: number;
  autoRefresh?: boolean;
  refreshInterval?: number;
}

const EMOTION_COLORS: Record<string, string> = {
  neutral: '#06b6d4',
  analytical: '#8b5cf6',
  creative: '#f59e0b',
  focused: '#3b82f6',
  empathetic: '#ec4899',
  playful: '#10b981',
};

export function NeuralActivityMap({ 
  height = 400, 
  autoRefresh = true,
  refreshInterval = 3000 
}: NeuralMapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [activity, setActivity] = useState<NeuralActivityData | null>(null);
  const [timeline, setTimeline] = useState<NeuralActivityData[]>([]);
  const [neurons, setNeurons] = useState<Array<{ x: number; y: number; active: boolean; intensity: number }>>([]);
  const animationRef = useRef<number | undefined>(undefined);
  const frameCount = useRef(0);

  // Fetch current activity
  const fetchActivity = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/dashboard/neural-activity/current');
      const data = await response.json();
      
      if (data.success && data.activity) {
        setActivity(data.activity);
        
        // Update timeline
        setTimeline(prev => {
          const newTimeline = [...prev, data.activity].slice(-50);
          return newTimeline;
        });

        // Generate neuron positions based on activity
        generateNeurons(data.activity);
      }
    } catch (error) {
      console.error('Failed to fetch neural activity:', error);
    }
  }, []);

  // Fetch timeline data
  const fetchTimeline = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/dashboard/neural-activity/timeline?limit=50');
      const data = await response.json();
      
      if (data.success && data.timeline?.activity_timeline) {
        setTimeline(data.timeline.activity_timeline);
      }
    } catch (error) {
      console.error('Failed to fetch timeline:', error);
    }
  }, []);

  // Generate neuron grid
  const generateNeurons = (activityData: NeuralActivityData) => {
    const cols = 20;
    const rows = 15;
    const newNeurons = [];
    
    const activeRatio = activityData.active_neurons / 2000; // Normalize
    
    for (let i = 0; i < cols; i++) {
      for (let j = 0; j < rows; j++) {
        const isActive = Math.random() < activeRatio;
        newNeurons.push({
          x: (i / (cols - 1)) * 100,
          y: (j / (rows - 1)) * 100,
          active: isActive,
          intensity: isActive ? Math.random() : 0,
        });
      }
    }
    
    setNeurons(newNeurons);
  };

  // Initial data fetch
  useEffect(() => {
    fetchActivity();
    fetchTimeline();
  }, [fetchActivity, fetchTimeline]);

  // Auto-refresh
  useEffect(() => {
    if (!autoRefresh) return;
    
    const interval = setInterval(fetchActivity, refreshInterval);
    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, fetchActivity]);

  // Canvas rendering
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;

    // Clear with fade effect
    ctx.fillStyle = 'rgba(15, 23, 42, 0.1)';
    ctx.fillRect(0, 0, width, height);

    if (neurons.length === 0) return;

    const emotionColor = activity ? EMOTION_COLORS[activity.emotion_state] || EMOTION_COLORS.neutral : EMOTION_COLORS.neutral;

    // Draw connections between nearby neurons
    neurons.forEach((neuron1, i) => {
      if (!neuron1.active) return;

      const x1 = (neuron1.x / 100) * width;
      const y1 = (neuron1.y / 100) * height;

      neurons.slice(i + 1).forEach(neuron2 => {
        if (!neuron2.active) return;

        const x2 = (neuron2.x / 100) * width;
        const y2 = (neuron2.y / 100) * height;
        
        const dx = x2 - x1;
        const dy = y2 - y1;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < 80) {
          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          
          const opacity = (1 - dist / 80) * 0.3 * neuron1.intensity;
          ctx.strokeStyle = `${emotionColor}${Math.round(opacity * 255).toString(16).padStart(2, '0')}`;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      });
    });

    // Draw neurons
    neurons.forEach(neuron => {
      const x = (neuron.x / 100) * width;
      const y = (neuron.y / 100) * height;
      
      if (neuron.active) {
        // Glow effect
        const gradient = ctx.createRadialGradient(x, y, 0, x, y, 8);
        gradient.addColorStop(0, `${emotionColor}ff`);
        gradient.addColorStop(0.5, `${emotionColor}80`);
        gradient.addColorStop(1, 'transparent');
        
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(x, y, 8, 0, Math.PI * 2);
        ctx.fill();

        // Core
        ctx.fillStyle = '#ffffff';
        ctx.beginPath();
        ctx.arc(x, y, 2 * neuron.intensity, 0, Math.PI * 2);
        ctx.fill();
      } else {
        // Inactive neuron
        ctx.fillStyle = 'rgba(100, 116, 139, 0.2)';
        ctx.beginPath();
        ctx.arc(x, y, 2, 0, Math.PI * 2);
        ctx.fill();
      }
    });

    // Animate neuron intensity
    frameCount.current++;
    if (frameCount.current % 5 === 0) {
      setNeurons(prev => prev.map(neuron => ({
        ...neuron,
        intensity: neuron.active ? Math.max(0.3, Math.min(1, neuron.intensity + (Math.random() - 0.5) * 0.2)) : 0,
      })));
    }
  }, [neurons, activity]);

  // Animation loop
  useEffect(() => {
    const animate = () => {
      render();
      animationRef.current = requestAnimationFrame(animate);
    };
    
    animate();
    
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [render]);

  // Render timeline chart
  const renderTimeline = () => {
    if (timeline.length < 2) return null;

    const maxLoad = Math.max(...timeline.map(d => d.processing_load));
    const minLoad = Math.min(...timeline.map(d => d.processing_load));
    const range = maxLoad - minLoad || 1;

    return (
      <div className="mt-4 h-24 relative">
        <svg width="100%" height="100%" className="overflow-visible">
          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio, i) => (
            <line
              key={i}
              x1="0"
              y1={`${ratio * 100}%`}
              x2="100%"
              y2={`${ratio * 100}%`}
              stroke="rgba(59, 130, 246, 0.1)"
              strokeWidth="1"
            />
          ))}
          
          {/* Area under curve */}
          <defs>
            <linearGradient id="loadGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.3" />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
            </linearGradient>
          </defs>
          
          <path
            d={`
              M 0 ${96 - ((timeline[0].processing_load - minLoad) / range) * 96}
              ${timeline.map((d, i) => {
                const x = (i / (timeline.length - 1)) * 100;
                const y = 96 - ((d.processing_load - minLoad) / range) * 96;
                return `L ${x}% ${y}`;
              }).join(' ')}
              L 100% 96
              L 0 96
              Z
            `}
            fill="url(#loadGradient)"
          />
          
          {/* Line */}
          <path
            d={`
              M 0 ${96 - ((timeline[0].processing_load - minLoad) / range) * 96}
              ${timeline.map((d, i) => {
                const x = (i / (timeline.length - 1)) * 100;
                const y = 96 - ((d.processing_load - minLoad) / range) * 96;
                return `L ${x}% ${y}`;
              }).join(' ')}
            `}
            fill="none"
            stroke="#3b82f6"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    );
  };

  if (!activity) {
    return (
      <Card className="flex items-center justify-center bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-blue-500/30 backdrop-blur-xl" style={{ height }}>
        <div className="text-center">
          <Brain className="h-12 w-12 text-blue-400 mx-auto mb-3 animate-pulse" />
          <p className="text-sm text-cyan-200/70">Initializing neural activity monitor...</p>
        </div>
      </Card>
    );
  }

  const emotionColor = EMOTION_COLORS[activity.emotion_state] || EMOTION_COLORS.neutral;

  return (
    <Card className="relative overflow-hidden bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-blue-500/30 backdrop-blur-xl">
      {/* Header */}
      <div className="absolute top-4 left-4 z-10 flex items-center gap-3">
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-900/80 border border-blue-500/30">
          <Brain className="h-4 w-4 text-blue-400" />
          <span className="text-sm font-semibold text-white">Neural Activity Map</span>
        </div>
        <Badge 
          variant="outline" 
          className="bg-slate-900/80 border-blue-500/30 text-cyan-300"
          style={{ borderColor: emotionColor }}
        >
          <span className="w-2 h-2 rounded-full mr-2" style={{ backgroundColor: emotionColor }} />
          {activity.emotion_state}
        </Badge>
      </div>

      {/* Real-time stats */}
      <div className="absolute top-4 right-4 z-10 space-y-2">
        <div className="px-3 py-2 rounded-lg bg-slate-900/80 border border-blue-500/30">
          <div className="flex items-center gap-2 mb-1">
            <Zap className="h-3 w-3 text-yellow-400" />
            <span className="text-[10px] text-cyan-200/70">Active Neurons</span>
          </div>
          <p className="text-lg font-bold text-white">{activity.active_neurons.toLocaleString()}</p>
        </div>
        
        <div className="px-3 py-2 rounded-lg bg-slate-900/80 border border-blue-500/30">
          <div className="flex items-center gap-2 mb-1">
            <Activity className="h-3 w-3 text-blue-400" />
            <span className="text-[10px] text-cyan-200/70">Processing Load</span>
          </div>
          <p className="text-lg font-bold text-white">{Math.round(activity.processing_load * 100)}%</p>
          <Progress value={activity.processing_load * 100} className="h-1 mt-1" />
        </div>
      </div>

      {/* Bottom stats */}
      <div className="absolute bottom-4 left-4 right-4 z-10 grid grid-cols-3 gap-3">
        <div className="px-3 py-2 rounded-lg bg-slate-900/80 border border-blue-500/30">
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp className="h-3 w-3 text-emerald-400" />
            <span className="text-[10px] text-cyan-200/70">Connections Fired</span>
          </div>
          <p className="text-base font-bold text-white">{activity.connections_fired.toLocaleString()}</p>
        </div>

        <div className="px-3 py-2 rounded-lg bg-slate-900/80 border border-blue-500/30">
          <div className="flex items-center gap-2 mb-1">
            <Brain className="h-3 w-3 text-purple-400" />
            <span className="text-[10px] text-cyan-200/70">Memory Accesses</span>
          </div>
          <p className="text-base font-bold text-white">{activity.memory_accesses.toLocaleString()}</p>
        </div>

        <div className="px-3 py-2 rounded-lg bg-slate-900/80 border border-blue-500/30">
          <div className="flex items-center gap-2 mb-1">
            <Zap className="h-3 w-3 text-amber-400" />
            <span className="text-[10px] text-cyan-200/70">Consciousness</span>
          </div>
          <p className="text-base font-bold text-white">{Math.round(activity.consciousness_level * 100)}%</p>
          <Progress value={activity.consciousness_level * 100} className="h-1 mt-1" />
        </div>
      </div>

      {/* Canvas */}
      <canvas
        ref={canvasRef}
        width={containerRef.current?.offsetWidth || 800}
        height={height}
        className="w-full"
      />

      {/* Timeline */}
      <div className="absolute bottom-32 left-4 right-4 z-10 px-3 py-2 rounded-lg bg-slate-900/80 border border-blue-500/30">
        <p className="text-[10px] text-cyan-200/70 mb-2">Processing Load Timeline (last 50 samples)</p>
        {renderTimeline()}
      </div>
    </Card>
  );
}
