/**
 * JARVIS Holographic UI Enhancements
 * ====================================
 * Tony Stark-inspired visual effects:
 * - Arc Reactor animation
 * - Holographic grid background
 * - Particle systems
 * - Neural network visualization
 * - Real-time system glow effects
 * 
 * This is the visual layer that makes JARVIS look like the movie.
 * All state comes from real backend/platform state.
 */

"use client";

import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Activity, Zap, Cpu, Radio, Brain, AlertCircle, CheckCircle, XCircle, Clock, Loader2 } from "lucide-react";

interface HolographicState {
  timestamp: string;
  platform: {
    status: string;
    uptime_seconds: number;
    environment: string;
  };
  system_health: {
    backend: string;
    database: string;
  };
  ai: {
    enabled: boolean;
    provider: string;
    capabilities: string[];
    silverwing: {
      configured: boolean;
      reachable: boolean;
      healthy: boolean;
      status: string;
      last_checked: string | null;
      errors: string | null;
      model: string;
    };
  };
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

const fetchHolographicState = async (): Promise<HolographicState | null> => {
  try {
    const response = await fetch(`${API_BASE}/api/v1/holographic/state`, {
      headers: { "Accept": "application/json" },
    });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
};

const formatTimestamp = (ts: string | null): string => {
  if (!ts) return "N/A";
  try {
    return new Date(ts).toLocaleTimeString();
  } catch {
    return "N/A";
  }
};

const formatUptime = (seconds: number): string => {
  if (!seconds || seconds < 0) return "N/A";
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${mins}m`;
};

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  maxLife: number;
  size: number;
  color: string;
}

interface NeuralNode {
  x: number;
  y: number;
  connections: number[];
  activation: number;
  radius: number;
}

export default function HolographicUI() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const nodesRef = useRef<NeuralNode[]>([]);
  const animationRef = useRef<number>(0);
  const [systemGlow, setSystemGlow] = useState(0);
  const [arcReactorRotation, setArcReactorRotation] = useState(0);
  const [activeEffects, setActiveEffects] = useState({
    particles: true,
    neuralNetwork: true,
    arcReactor: true,
    holographicGrid: true,
  });
  const [holographicState, setHolographicState] = useState<HolographicState | null>(null);
  const [stateLoading, setStateLoading] = useState(true);

  // Fetch real state from backend
  useEffect(() => {
    const loadState = async () => {
      setStateLoading(true);
      const state = await fetchHolographicState();
      setHolographicState(state);
      setStateLoading(false);
    };
    loadState();
    
    // Refresh state every 5 seconds
    const interval = setInterval(loadState, 5000);
    return () => clearInterval(interval);
  }, []);

  // Initialize neural network nodes
  useEffect(() => {
    const nodes: NeuralNode[] = [];
    const nodeCount = 30;

    for (let i = 0; i < nodeCount; i++) {
      nodes.push({
        x: Math.random() * 800,
        y: Math.random() * 600,
        connections: [],
        activation: Math.random(),
        radius: 3 + Math.random() * 5,
      });
    }

    // Create connections
    nodes.forEach((node, i) => {
      const connectionCount = 2 + Math.floor(Math.random() * 3);
      for (let j = 0; j < connectionCount; j++) {
        const target = Math.floor(Math.random() * nodeCount);
        if (target !== i && !node.connections.includes(target)) {
          node.connections.push(target);
        }
      }
    });

    nodesRef.current = nodes;
  }, []);

  // Animation loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Draw holographic grid
      if (activeEffects.holographicGrid) {
        drawHolographicGrid(ctx, canvas.width, canvas.height);
      }

      // Draw neural network
      if (activeEffects.neuralNetwork) {
        drawNeuralNetwork(ctx, nodesRef.current);
        updateNeuralNodes(nodesRef.current);
      }

      // Draw particles
      if (activeEffects.particles) {
        drawParticles(ctx, particlesRef.current);
        updateParticles(particlesRef.current, canvas.width, canvas.height);

        // Spawn new particles
        if (particlesRef.current.length < 50) {
          spawnParticle(particlesRef.current, canvas.width, canvas.height);
        }
      }

      // Update system glow
      setSystemGlow((prev) => (prev + 0.02) % (Math.PI * 2));
      setArcReactorRotation((prev) => (prev + 0.5) % 360);

      animationRef.current = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      cancelAnimationFrame(animationRef.current);
    };
  }, [activeEffects]);

  const drawHolographicGrid = (
    ctx: CanvasRenderingContext2D,
    width: number,
    height: number
  ) => {
    ctx.strokeStyle = "rgba(0, 150, 255, 0.1)";
    ctx.lineWidth = 1;

    const gridSize = 40;
    const time = Date.now() * 0.001;

    // Horizontal lines with wave effect
    for (let y = 0; y < height; y += gridSize) {
      ctx.beginPath();
      for (let x = 0; x < width; x += 5) {
        const waveY = y + Math.sin(x * 0.02 + time) * 5;
        if (x === 0) {
          ctx.moveTo(x, waveY);
        } else {
          ctx.lineTo(x, waveY);
        }
      }
      ctx.stroke();
    }

    // Vertical lines
    for (let x = 0; x < width; x += gridSize) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
  };

  const drawNeuralNetwork = (
    ctx: CanvasRenderingContext2D,
    nodes: NeuralNode[]
  ) => {
    // Draw connections
    nodes.forEach((node, i) => {
      node.connections.forEach((targetIdx) => {
        const target = nodes[targetIdx];
        if (target) {
          const opacity = (node.activation + target.activation) / 2;
          ctx.strokeStyle = `rgba(0, 200, 255, ${opacity * 0.3})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(node.x, node.y);
          ctx.lineTo(target.x, target.y);
          ctx.stroke();
        }
      });
    });

    // Draw nodes
    nodes.forEach((node) => {
      const glow = node.activation;

      // Outer glow
      const gradient = ctx.createRadialGradient(
        node.x,
        node.y,
        0,
        node.x,
        node.y,
        node.radius * 3
      );
      gradient.addColorStop(0, `rgba(0, 200, 255, ${glow * 0.5})`);
      gradient.addColorStop(1, "rgba(0, 200, 255, 0)");

      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius * 3, 0, Math.PI * 2);
      ctx.fill();

      // Core
      ctx.fillStyle = `rgba(0, 200, 255, ${0.5 + glow * 0.5})`;
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      ctx.fill();
    });
  };

  const updateNeuralNodes = (nodes: NeuralNode[]) => {
    nodes.forEach((node) => {
      node.activation += (Math.random() - 0.5) * 0.1;
      node.activation = Math.max(0.1, Math.min(1, node.activation));
    });
  };

  const spawnParticle = (
    particles: Particle[],
    width: number,
    height: number
  ) => {
    const colors = [
      "rgba(0, 200, 255, 1)",
      "rgba(100, 150, 255, 1)",
      "rgba(0, 255, 200, 1)",
    ];

    particles.push({
      x: Math.random() * width,
      y: height + 10,
      vx: (Math.random() - 0.5) * 2,
      vy: -1 - Math.random() * 2,
      life: 0,
      maxLife: 100 + Math.random() * 100,
      size: 1 + Math.random() * 3,
      color: colors[Math.floor(Math.random() * colors.length)],
    });
  };

  const drawParticles = (
    ctx: CanvasRenderingContext2D,
    particles: Particle[]
  ) => {
    particles.forEach((p) => {
      const alpha = 1 - p.life / p.maxLife;
      ctx.fillStyle = p.color.replace("1)", `${alpha})`);
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fill();
    });
  };

  const updateParticles = (
    particles: Particle[],
    width: number,
    height: number
  ) => {
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i];
      p.x += p.vx;
      p.y += p.vy;
      p.life++;

      // Remove dead particles
      if (p.life > p.maxLife || p.y < -10) {
        particles.splice(i, 1);
      }
    }
  };

  const ArcReactor = () => {
    return (
      <div className="relative w-48 h-48 mx-auto">
        <svg
          viewBox="0 0 200 200"
          className="w-full h-full animate-spin"
          style={{ animationDuration: "10s" }}
        >
          <defs>
            <radialGradient id="arcGradient" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#00d4ff" stopOpacity="1" />
              <stop offset="50%" stopColor="#0099ff" stopOpacity="0.8" />
              <stop offset="100%" stopColor="#0066cc" stopOpacity="0.2" />
            </radialGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="4" result="coloredBlur" />
              <feMerge>
                <feMergeNode in="coloredBlur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Outer ring */}
          <circle
            cx="100"
            cy="100"
            r="95"
            fill="none"
            stroke="rgba(0, 200, 255, 0.3)"
            strokeWidth="2"
          />

          {/* Inner rings */}
          <circle
            cx="100"
            cy="100"
            r="70"
            fill="none"
            stroke="rgba(0, 200, 255, 0.5)"
            strokeWidth="3"
            strokeDasharray="10 5"
          />

          <circle
            cx="100"
            cy="100"
            r="50"
            fill="none"
            stroke="rgba(0, 200, 255, 0.7)"
            strokeWidth="4"
            strokeDasharray="15 8"
          />

          {/* Core */}
          <circle
            cx="100"
            cy="100"
            r="30"
            fill="url(#arcGradient)"
            filter="url(#glow)"
          />

          {/* Energy beams */}
          {[0, 45, 90, 135, 180, 225, 270, 315].map((angle, i) => (
            <line
              key={i}
              x1="100"
              y1="100"
              x2={100 + 85 * Math.cos((angle * Math.PI) / 180)}
              y2={100 + 85 * Math.sin((angle * Math.PI) / 180)}
              stroke="rgba(0, 200, 255, 0.2)"
              strokeWidth="1"
            />
          ))}
        </svg>

        {/* Pulsing overlay */}
        <div
          className="absolute inset-0 rounded-full bg-blue-500/20 blur-xl"
          style={{
            animation: "pulse 2s ease-in-out infinite",
          }}
        />
      </div>
    );
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="text-center space-y-4">
        <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-400 via-cyan-400 to-purple-400 bg-clip-text text-transparent">
          JARVIS Holographic Interface
        </h1>
        <p className="text-muted-foreground">
          Tony Stark-Inspired Visual Enhancement System
        </p>
      </div>

      {/* Arc Reactor */}
      <Card className="border-blue-500/30 bg-gradient-to-br from-blue-950/40 to-transparent">
        <CardHeader>
          <CardTitle className="text-center flex items-center justify-center gap-2">
            <Zap className="h-5 w-5 text-blue-400" />
            Arc Reactor Core
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ArcReactor />
          <p className="text-center text-sm text-muted-foreground mt-4">
            Rotation: {arcReactorRotation.toFixed(1)}° • System Glow:{" "}
            {(Math.sin(systemGlow) * 50 + 50).toFixed(1)}%
          </p>
        </CardContent>
      </Card>

      {/* Holographic Canvas */}
      <Card className="border-cyan-500/30">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-cyan-400" />
            Neural Network Visualization
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="relative rounded-lg overflow-hidden border border-cyan-500/30 bg-black/50">
            <canvas
              ref={canvasRef}
              width={800}
              height={400}
              className="w-full h-auto"
            />
          </div>

          {/* Controls */}
          <div className="flex flex-wrap gap-2 mt-4">
            <Badge
              variant={activeEffects.particles ? "default" : "secondary"}
              className="cursor-pointer"
              onClick={() =>
                setActiveEffects((prev) => ({
                  ...prev,
                  particles: !prev.particles,
                }))
              }
            >
              Particles
            </Badge>
            <Badge
              variant={activeEffects.neuralNetwork ? "default" : "secondary"}
              className="cursor-pointer"
              onClick={() =>
                setActiveEffects((prev) => ({
                  ...prev,
                  neuralNetwork: !prev.neuralNetwork,
                }))
              }
            >
              Neural Network
            </Badge>
            <Badge
              variant={activeEffects.arcReactor ? "default" : "secondary"}
              className="cursor-pointer"
              onClick={() =>
                setActiveEffects((prev) => ({
                  ...prev,
                  arcReactor: !prev.arcReactor,
                }))
              }
            >
              Arc Reactor
            </Badge>
            <Badge
              variant={activeEffects.holographicGrid ? "default" : "secondary"}
              className="cursor-pointer"
              onClick={() =>
                setActiveEffects((prev) => ({
                  ...prev,
                  holographicGrid: !prev.holographicGrid,
                }))
              }
            >
              Holographic Grid
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* System Status Indicators */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* AI Engine - Shows Silverwing status */}
        <Card className="border-blue-500/30">
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-2">
              <Brain className="h-8 w-8 text-blue-400" />
              <span className="text-sm font-medium">AI Engine</span>
              {stateLoading ? (
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Checking...
                </div>
              ) : holographicState?.ai ? (
                holographicState.ai.healthy ? (
                  <div className="flex items-center gap-1 text-xs text-green-400">
                    <CheckCircle className="h-3 w-3" />
                    <span>{holographicState.ai.provider || "silverwing"}</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-1 text-xs text-amber-400">
                    <XCircle className="h-3 w-3" />
                    <span>Unreachable</span>
                  </div>
                )
              ) : (
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <XCircle className="h-3 w-3" />
                  <span>Offline</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* System - Shows backend health */}
        <Card className="border-green-500/30">
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-2">
              <Cpu className="h-8 w-8 text-green-400" />
              <span className="text-sm font-medium">System</span>
              {stateLoading ? (
                <div className="text-xs text-muted-foreground">Loading...</div>
              ) : holographicState?.system_health?.backend === "connected" ? (
                <div className="flex items-center gap-1 text-xs text-green-400">
                  <CheckCircle className="h-3 w-3" />
                  <span>Online</span>
                </div>
              ) : (
                <div className="flex items-center gap-1 text-xs text-red-400">
                  <XCircle className="h-3 w-3" />
                  <span>Offline</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Network - Shows database health */}
        <Card className="border-purple-500/30">
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-2">
              <Radio className="h-8 w-8 text-purple-400" />
              <span className="text-sm font-medium">Network</span>
              {stateLoading ? (
                <div className="text-xs text-muted-foreground">Loading...</div>
              ) : holographicState?.system_health?.database === "connected" ? (
                <div className="flex items-center gap-1 text-xs text-green-400">
                  <CheckCircle className="h-3 w-3" />
                  <span>Connected</span>
                </div>
              ) : (
                <div className="flex items-center gap-1 text-xs text-red-400">
                  <XCircle className="h-3 w-3" />
                  <span>Disconnected</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Power - Shows platform status */}
        <Card className="border-yellow-500/30">
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-2">
              <Zap className="h-8 w-8 text-yellow-400" />
              <span className="text-sm font-medium">Power</span>
              {stateLoading ? (
                <div className="text-xs text-muted-foreground">Loading...</div>
              ) : holographicState?.platform?.status === "online" ? (
                <div className="flex items-center gap-1 text-xs text-green-400">
                  <Clock className="h-3 w-3" />
                  <span>Uptime: {formatUptime(holographicState.platform.uptime_seconds)}</span>
                </div>
              ) : (
                <div className="flex items-center gap-1 text-xs text-amber-400">
                  <Clock className="h-3 w-3" />
                  <span>Degraded</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Silverwing Status Detail */}
      <Card className="border-cyan-500/30 md:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-cyan-400" />
            Silverwing Provider Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          {stateLoading ? (
            <div className="text-center py-4 text-muted-foreground">Loading...</div>
          ) : holographicState?.ai?.silverwing ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="flex items-center gap-2">
                <span className="font-medium">Status:</span>
                <Badge 
                  variant={holographicState.ai.silverwing.healthy ? "default" : "destructive"}
                >
                  {holographicState.ai.silverwing.status}
                </Badge>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-medium">Reachability:</span>
                <Badge variant={holographicState.ai.silverwing.reachable ? "default" : "secondary"}>
                  {holographicState.ai.silverwing.reachable ? "Reachable" : "Unreachable"}
                </Badge>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-medium">Configured:</span>
                <Badge variant={holographicState.ai.silverwing.configured ? "default" : "secondary"}>
                  {holographicState.ai.silverwing.configured ? "Yes" : "No"}
                </Badge>
              </div>
              {holographicState.ai.silverwing.errors && (
                <div className="md:col-span-3 text-sm text-muted-foreground">
                  <strong>Error:</strong> {holographicState.ai.silverwing.errors}
                </div>
              )}
              {holographicState.ai.silverwing.last_checked && (
                <div className="md:col-span-3 text-xs text-muted-foreground">
                  Last checked: {formatTimestamp(holographicState.ai.silverwing.last_checked)}
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-4 text-muted-foreground">
              Silverwing status unavailable
            </div>
          )}
        </CardContent>
      </Card>

      {/* CSS Animations */}
      <style jsx>{`
        @keyframes pulse {
          0%,
          100% {
            opacity: 0.3;
          }
          50% {
            opacity: 0.6;
          }
        }
      `}</style>
    </div>
  );
}
