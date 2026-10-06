"use client";

import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Box, Layers, Zap, Eye, Rotate3D, Maximize2, Minimize2,
  Settings, Play, Pause, Grid, Hexagon, Circle, Square
} from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";

export default function JarvisHolographicInterface() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [is3D, setIs3D] = useState(true);
  const [rotation, setRotation] = useState({ x: 0, y: 0, z: 0 });
  const [scale, setScale] = useState(1);
  const [isPlaying, setIsPlaying] = useState(true);
  const [hologramIntensity, setHologramIntensity] = useState(0.8);

  useEffect(() => {
    if (!canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resizeCanvas = () => {
      if (canvasRef.current) {
        canvas.width = canvasRef.current.clientWidth;
        canvas.height = canvasRef.current.clientHeight;
      }
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    let animationFrame: number;
    let time = 0;

    const drawHologram = () => {
      if (!ctx || !canvas) return;

      ctx.fillStyle = 'rgba(15, 23, 42, 0.1)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      const baseSize = Math.min(canvas.width, canvas.height) * 0.3 * scale;

      // Draw holographic grid
      ctx.strokeStyle = `rgba(147, 51, 234, ${hologramIntensity * 0.3})`;
      ctx.lineWidth = 1;
      
      for (let i = -5; i <= 5; i++) {
        // Vertical lines
        ctx.beginPath();
        ctx.moveTo(centerX + i * 40, centerY - 200);
        ctx.lineTo(centerX + i * 40, centerY + 200);
        ctx.stroke();
        
        // Horizontal lines
        ctx.beginPath();
        ctx.moveTo(centerX - 200, centerY + i * 40);
        ctx.lineTo(centerX + 200, centerY + i * 40);
        ctx.stroke();
      }

      // Draw rotating 3D cube
      const rotX = rotation.x + time * 0.01;
      const rotY = rotation.y + time * 0.02;
      const rotZ = rotation.z + time * 0.005;

      const cosX = Math.cos(rotX);
      const sinX = Math.sin(rotX);
      const cosY = Math.cos(rotY);
      const sinY = Math.sin(rotY);
      const cosZ = Math.cos(rotZ);
      const sinZ = Math.sin(rotZ);

      const vertices = [
        [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
        [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]
      ];

      const edges = [
        [0, 1], [1, 2], [2, 3], [3, 0],
        [4, 5], [5, 6], [6, 7], [7, 4],
        [0, 4], [1, 5], [2, 6], [3, 7]
      ];

      const projectedVertices = vertices.map(([x, y, z]) => {
        // Rotate around X
        let y1 = y * cosX - z * sinX;
        let z1 = y * sinX + z * cosX;
        
        // Rotate around Y
        let x2 = x * cosY + z1 * sinY;
        let z2 = -x * sinY + z1 * cosY;
        
        // Rotate around Z
        let x3 = x2 * cosZ - y1 * sinZ;
        let y3 = x2 * sinZ + y1 * cosZ;
        
        // Project to 2D
        const perspective = 2 / (3 - z2);
        return {
          x: centerX + x3 * baseSize * perspective,
          y: centerY + y3 * baseSize * perspective,
          z: z2
        };
      });

      // Draw edges with holographic effect
      edges.forEach(([start, end]) => {
        const v1 = projectedVertices[start];
        const v2 = projectedVertices[end];
        
        const gradient = ctx.createLinearGradient(v1.x, v1.y, v2.x, v2.y);
        gradient.addColorStop(0, `rgba(147, 51, 234, ${hologramIntensity})`);
        gradient.addColorStop(0.5, `rgba(236, 72, 153, ${hologramIntensity})`);
        gradient.addColorStop(1, `rgba(6, 182, 212, ${hologramIntensity})`);
        
        ctx.strokeStyle = gradient;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(v1.x, v1.y);
        ctx.lineTo(v2.x, v2.y);
        ctx.stroke();
      });

      // Draw vertices
      projectedVertices.forEach((v, i) => {
        const gradient = ctx.createRadialGradient(v.x, v.y, 0, v.x, v.y, 8);
        gradient.addColorStop(0, `rgba(147, 51, 234, ${hologramIntensity})`);
        gradient.addColorStop(1, 'rgba(147, 51, 234, 0)');
        
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(v.x, v.y, 8, 0, Math.PI * 2);
        ctx.fill();
      });

      // Draw holographic scan lines
      ctx.strokeStyle = `rgba(6, 182, 212, ${hologramIntensity * 0.5})`;
      ctx.lineWidth = 1;
      for (let i = 0; i < 5; i++) {
        const y = centerY - 150 + (time * 2 + i * 50) % 300;
        ctx.beginPath();
        ctx.moveTo(centerX - 150, y);
        ctx.lineTo(centerX + 150, y);
        ctx.stroke();
      }

      // Draw holographic glow
      const glowGradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, baseSize * 2);
      glowGradient.addColorStop(0, `rgba(147, 51, 234, ${hologramIntensity * 0.2})`);
      glowGradient.addColorStop(1, 'rgba(147, 51, 234, 0)');
      
      ctx.fillStyle = glowGradient;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      if (isPlaying) {
        time += 1;
      }

      animationFrame = requestAnimationFrame(drawHologram);
    };

    drawHologram();

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      cancelAnimationFrame(animationFrame);
    };
  }, [rotation, scale, isPlaying, hologramIntensity]);

  const handleReset = () => {
    setRotation({ x: 0, y: 0, z: 0 });
    setScale(1);
  };

  return (
    <div className="space-y-6">
      <Card className="bg-white/[0.02] border-white/5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Eye className="w-5 h-5 text-purple-400" />
            Holographic Interface
          </CardTitle>
          <CardDescription>
            Interactive 3D holographic visualization system
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {/* Hologram Canvas */}
            <div className="relative w-full h-[500px] bg-slate-950 rounded-lg overflow-hidden border border-purple-500/20">
              <canvas ref={canvasRef} className="w-full h-full" />
              
              {/* Overlay Controls */}
              <div className="absolute top-4 left-4 space-y-2">
                <Badge className="bg-purple-500 text-white">
                  <Zap className="w-3 h-3 mr-1" />
                  Hologram Active
                </Badge>
                <Badge className="bg-cyan-500 text-white">
                  <Rotate3D className="w-3 h-3 mr-1" />
                  3D Mode
                </Badge>
              </div>

              <div className="absolute bottom-4 right-4 flex items-center gap-2">
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => setIsPlaying(!isPlaying)}
                >
                  {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  onClick={handleReset}
                >
                  <Rotate3D className="w-4 h-4" />
                </Button>
              </div>
            </div>

            {/* Controls */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Rotation Controls */}
              <div className="space-y-3">
                <label className="text-sm text-gray-400">Rotation X</label>
                <Slider
                  value={[rotation.x]}
                  onValueChange={([v]) => setRotation(prev => ({ ...prev, x: v }))}
                  max={Math.PI * 2}
                  step={0.1}
                />
                <label className="text-sm text-gray-400">Rotation Y</label>
                <Slider
                  value={[rotation.y]}
                  onValueChange={([v]) => setRotation(prev => ({ ...prev, y: v }))}
                  max={Math.PI * 2}
                  step={0.1}
                />
                <label className="text-sm text-gray-400">Rotation Z</label>
                <Slider
                  value={[rotation.z]}
                  onValueChange={([v]) => setRotation(prev => ({ ...prev, z: v }))}
                  max={Math.PI * 2}
                  step={0.1}
                />
              </div>

              {/* Scale Control */}
              <div className="space-y-3">
                <label className="text-sm text-gray-400">Scale</label>
                <Slider
                  value={[scale]}
                  onValueChange={([v]) => setScale(v)}
                  min={0.5}
                  max={2}
                  step={0.1}
                />
                <label className="text-sm text-gray-400">Hologram Intensity</label>
                <Slider
                  value={[hologramIntensity]}
                  onValueChange={([v]) => setHologramIntensity(v)}
                  min={0.1}
                  max={1}
                  step={0.1}
                />
              </div>

              {/* Quick Actions */}
              <div className="space-y-2">
                <Button variant="outline" className="w-full justify-start" onClick={handleReset}>
                  <Rotate3D className="w-4 h-4 mr-2" />
                  Reset View
                </Button>
                <Button variant="outline" className="w-full justify-start" onClick={() => setScale(1.5)}>
                  <Maximize2 className="w-4 h-4 mr-2" />
                  Zoom In
                </Button>
                <Button variant="outline" className="w-full justify-start" onClick={() => setScale(0.8)}>
                  <Minimize2 className="w-4 h-4 mr-2" />
                  Zoom Out
                </Button>
                <Button variant="outline" className="w-full justify-start">
                  <Settings className="w-4 h-4 mr-2" />
                  Advanced Settings
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Holographic Features */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="bg-white/[0.02] border-white/5">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Box className="w-4 h-4 text-purple-400" />
              3D Projection
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-gray-400">
              Real-time 3D rendering with perspective projection and depth perception
            </p>
          </CardContent>
        </Card>

        <Card className="bg-white/[0.02] border-white/5">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Layers className="w-4 h-4 text-pink-400" />
              Multi-Layer
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-gray-400">
              Multiple holographic layers with adjustable intensity and blending
            </p>
          </CardContent>
        </Card>

        <Card className="bg-white/[0.02] border-white/5">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Grid className="w-4 h-4 text-cyan-400" />
              Spatial Grid
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-gray-400">
              Dynamic spatial reference grid for precise positioning
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
