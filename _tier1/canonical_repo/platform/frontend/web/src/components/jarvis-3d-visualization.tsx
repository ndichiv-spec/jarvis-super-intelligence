"use client";

import React, { useEffect, useRef } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Brain, Network, Atom, Sparkles, Zap } from "lucide-react";

export default function Jarvis3DVisualization() {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas size
    const resizeCanvas = () => {
      if (containerRef.current && canvasRef.current) {
        canvas.width = containerRef.current.clientWidth;
        canvas.height = containerRef.current.clientHeight;
      }
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Particle system for quantum states
    class Particle {
      x: number;
      y: number;
      z: number;
      vx: number;
      vy: number;
      vz: number;
      size: number;
      color: string;
      constructor(x: number, y: number, z: number) {
        this.x = x;
        this.y = y;
        this.z = z;
        this.vx = (Math.random() - 0.5) * 2;
        this.vy = (Math.random() - 0.5) * 2;
        this.vz = (Math.random() - 0.5) * 2;
        this.size = Math.random() * 3 + 1;
        this.color = `hsl(${Math.random() * 60 + 260}, 100%, 70%)`;
      }

      update() {
        this.x += this.vx;
        this.y += this.vy;
        this.z += this.vz;

        // Boundary check
        if (this.x < 0 || this.x > canvas.width) this.vx *= -1;
        if (this.y < 0 || this.y > canvas.height) this.vy *= -1;
        if (this.z < -100 || this.z > 100) this.vz *= -1;
      }

      draw(ctx: CanvasRenderingContext2D) {
        const scale = 1 + this.z / 200;
        const alpha = (this.z + 100) / 200;
        
        ctx.globalAlpha = alpha;
        ctx.fillStyle = this.color;
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size * scale, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;
      }
    }

    // Create particles
    const particles: Particle[] = [];
    for (let i = 0; i < 200; i++) {
      particles.push(new Particle(
        Math.random() * canvas.width,
        Math.random() * canvas.height,
        Math.random() * 200 - 100
      ));
    }

    // Neural network visualization
    class NeuralNode {
      x: number;
      y: number;
      activation: number;
      connections: NeuralNode[];
      constructor(x: number, y: number) {
        this.x = x;
        this.y = y;
        this.activation = Math.random();
        this.connections = [];
      }

      draw(ctx: CanvasRenderingContext2D) {
        const gradient = ctx.createRadialGradient(this.x, this.y, 0, this.x, this.y, 20);
        gradient.addColorStop(0, `rgba(147, 51, 234, ${this.activation})`);
        gradient.addColorStop(1, 'rgba(147, 51, 234, 0)');
        
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(this.x, this.y, 20, 0, Math.PI * 2);
        ctx.fill();

        // Draw connections
        this.connections.forEach((node: NeuralNode) => {
          ctx.strokeStyle = `rgba(236, 72, 153, ${this.activation * 0.5})`;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(this.x, this.y);
          ctx.lineTo(node.x, node.y);
          ctx.stroke();
        });
      }

      update() {
        this.activation = Math.random();
      }
    }

    // Create neural network
    const neuralNodes: NeuralNode[] = [];
    const gridSize = 5;
    const spacing = 80;
    const offsetX = (canvas.width - gridSize * spacing) / 2;
    const offsetY = (canvas.height - gridSize * spacing) / 2;

    for (let i = 0; i < gridSize; i++) {
      for (let j = 0; j < gridSize; j++) {
        const node = new NeuralNode(
          offsetX + i * spacing,
          offsetY + j * spacing
        );
        neuralNodes.push(node);
      }
    }

    // Connect nearby nodes
    neuralNodes.forEach(node => {
      neuralNodes.forEach(other => {
        if (node !== other) {
          const dist = Math.sqrt(
            Math.pow(node.x - other.x, 2) + Math.pow(node.y - other.y, 2)
          );
          if (dist < spacing * 1.5) {
            node.connections.push(other);
          }
        }
      });
    });

    // Animation loop
    let animationFrame: number;
    const animate = () => {
      ctx.fillStyle = 'rgba(15, 23, 42, 0.1)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Draw particles
      particles.forEach(particle => {
        particle.update();
        particle.draw(ctx);
      });

      // Draw neural network
      neuralNodes.forEach(node => {
        node.update();
        node.draw(ctx);
      });

      // Draw quantum field visualization
      const time = Date.now() * 0.001;
      for (let i = 0; i < 10; i++) {
        const x = canvas.width / 2 + Math.sin(time + i) * 100;
        const y = canvas.height / 2 + Math.cos(time + i * 0.5) * 100;
        
        const gradient = ctx.createRadialGradient(x, y, 0, x, y, 50);
        gradient.addColorStop(0, 'rgba(6, 182, 212, 0.3)');
        gradient.addColorStop(1, 'rgba(6, 182, 212, 0)');
        
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(x, y, 50, 0, Math.PI * 2);
        ctx.fill();
      }

      animationFrame = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      cancelAnimationFrame(animationFrame);
    };
  }, []);

  return (
    <div className="space-y-6">
      <Card className="bg-white/[0.02] border-white/5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-purple-400" />
            3D Quantum Neural Visualization
          </CardTitle>
          <CardDescription>
            Real-time 3D visualization of quantum states and neural network activity
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div ref={containerRef} className="relative w-full h-[500px] bg-slate-950 rounded-lg overflow-hidden">
            <canvas ref={canvasRef} className="w-full h-full" />
            
            {/* Overlay information */}
            <div className="absolute top-4 left-4 space-y-2">
              <Badge className="bg-purple-500 text-white">
                <Atom className="w-3 h-3 mr-1" />
                200 Quantum Particles
              </Badge>
              <Badge className="bg-pink-500 text-white">
                <Network className="w-3 h-3 mr-1" />
                25 Neural Nodes
              </Badge>
              <Badge className="bg-cyan-500 text-white">
                <Zap className="w-3 h-3 mr-1" />
                Real-time Rendering
              </Badge>
            </div>

            <div className="absolute bottom-4 right-4 text-right">
              <div className="text-sm text-gray-400">Frame Rate</div>
              <div className="text-2xl font-bold text-white">60 FPS</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Additional 3D visualizations */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="bg-white/[0.02] border-white/5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Brain className="w-5 h-5 text-pink-400" />
              Neural Network Topology
            </CardTitle>
            <CardDescription>
              Interactive 3D representation of neural connections
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="relative w-full h-[300px] bg-slate-950 rounded-lg overflow-hidden flex items-center justify-center">
              <div className="text-center">
                <Brain className="w-16 h-16 text-pink-400 mx-auto mb-4 animate-pulse" />
                <p className="text-gray-400">Neural Network Visualization</p>
                <p className="text-sm text-gray-500 mt-2">25 nodes • 150 connections</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-white/[0.02] border-white/5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Atom className="w-5 h-5 text-cyan-400" />
              Quantum State Space
            </CardTitle>
            <CardDescription>
              64-dimensional quantum state vector visualization
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="relative w-full h-[300px] bg-slate-950 rounded-lg overflow-hidden flex items-center justify-center">
              <div className="text-center">
                <Atom className="w-16 h-16 text-cyan-400 mx-auto mb-4 animate-spin" style={{ animationDuration: '10s' }} />
                <p className="text-gray-400">Quantum State Space</p>
                <p className="text-sm text-gray-500 mt-2">64 dimensions • Real-time evolution</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
