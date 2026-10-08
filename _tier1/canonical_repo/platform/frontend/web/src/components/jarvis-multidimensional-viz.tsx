"use client";

import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Box, Layers, Zap, Eye, Rotate3D, Maximize2, Minimize2,
  Settings, Play, Pause, Grid, Hexagon, Circle, Square,
  Pyramid, Diamond
} from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function JarvisMultidimensionalViz() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [dimensions, setDimensions] = useState(4);
  const [rotation, setRotation] = useState({ x: 0, y: 0, z: 0, w: 0 });
  const [scale, setScale] = useState(1);
  const [isPlaying, setIsPlaying] = useState(true);
  const [selectedView, setSelectedView] = useState("hypercube");
  const [projection, setProjection] = useState("perspective");

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

    const drawMultidimensional = () => {
      if (!ctx || !canvas) return;

      ctx.fillStyle = 'rgba(15, 23, 42, 0.1)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      const baseSize = Math.min(canvas.width, canvas.height) * 0.25 * scale;

      // Draw based on selected view
      if (selectedView === "hypercube") {
        drawHypercube(ctx, centerX, centerY, baseSize, time);
      } else if (selectedView === "hypersphere") {
        drawHypersphere(ctx, centerX, centerY, baseSize, time);
      } else if (selectedView === "tesseract") {
        drawTesseract(ctx, centerX, centerY, baseSize, time);
      } else if (selectedView === "manifold") {
        drawManifold(ctx, centerX, centerY, baseSize, time);
      }

      if (isPlaying) {
        time += 1;
      }

      animationFrame = requestAnimationFrame(drawMultidimensional);
    };

    const drawHypercube = (ctx: CanvasRenderingContext2D, cx: number, cy: number, size: number, t: number) => {
      const rotX = rotation.x + t * 0.01;
      const rotY = rotation.y + t * 0.02;
      const rotZ = rotation.z + t * 0.005;
      const rotW = rotation.w + t * 0.003;

      // Generate 4D hypercube vertices
      const vertices: number[][] = [];
      for (let i = 0; i < 16; i++) {
        const x = (i & 1) ? 1 : -1;
        const y = (i & 2) ? 1 : -1;
        const z = (i & 4) ? 1 : -1;
        const w = (i & 8) ? 1 : -1;
        vertices.push([x, y, z, w]);
      }

      // Project 4D to 3D
      const projected3D = vertices.map(([x, y, z, w]) => {
        // Rotate in 4D
        const cosW = Math.cos(rotW);
        const sinW = Math.sin(rotW);
        const x1 = x * cosW - w * sinW;
        const w1 = x * sinW + w * cosW;
        
        // Project to 3D
        const perspective = 2 / (3 - w1);
        return [x1 * perspective, y * perspective, z * perspective];
      });

      // Rotate in 3D
      const projected2D = projected3D.map(([x, y, z]) => {
        const cosX = Math.cos(rotX);
        const sinX = Math.sin(rotX);
        const cosY = Math.cos(rotY);
        const sinY = Math.sin(rotY);
        const cosZ = Math.cos(rotZ);
        const sinZ = Math.sin(rotZ);

        let y1 = y * cosX - z * sinX;
        let z1 = y * sinX + z * cosX;
        let x2 = x * cosY + z1 * sinY;
        let z2 = -x * sinY + z1 * cosY;
        let x3 = x2 * cosZ - y1 * sinZ;
        let y3 = x2 * sinZ + y1 * cosZ;

        const perspective3D = 2 / (3 - z2);
        return {
          x: cx + x3 * size * perspective3D,
          y: cy + y3 * size * perspective3D,
          z: z2
        };
      });

      // Draw edges
      const edges = [
        [0, 1], [1, 3], [3, 2], [2, 0],
        [4, 5], [5, 7], [7, 6], [6, 4],
        [0, 4], [1, 5], [2, 6], [3, 7],
        [8, 9], [9, 11], [11, 10], [10, 8],
        [12, 13], [13, 15], [15, 14], [14, 12],
        [8, 12], [9, 13], [10, 14], [11, 15],
        [0, 8], [1, 9], [2, 10], [3, 11],
        [4, 12], [5, 13], [6, 14], [7, 15]
      ];

      edges.forEach(([start, end]) => {
        const v1 = projected2D[start];
        const v2 = projected2D[end];
        
        const gradient = ctx.createLinearGradient(v1.x, v1.y, v2.x, v2.y);
        gradient.addColorStop(0, 'rgba(147, 51, 234, 0.8)');
        gradient.addColorStop(0.5, 'rgba(236, 72, 153, 0.8)');
        gradient.addColorStop(1, 'rgba(6, 182, 212, 0.8)');
        
        ctx.strokeStyle = gradient;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(v1.x, v1.y);
        ctx.lineTo(v2.x, v2.y);
        ctx.stroke();
      });

      // Draw vertices
      projected2D.forEach((v) => {
        const gradient = ctx.createRadialGradient(v.x, v.y, 0, v.x, v.y, 6);
        gradient.addColorStop(0, 'rgba(147, 51, 234, 1)');
        gradient.addColorStop(1, 'rgba(147, 51, 234, 0)');
        
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(v.x, v.y, 6, 0, Math.PI * 2);
        ctx.fill();
      });
    };

    const drawHypersphere = (ctx: CanvasRenderingContext2D, cx: number, cy: number, size: number, t: number) => {
      const points = 100;
      for (let i = 0; i < points; i++) {
        const theta = (i / points) * Math.PI * 2;
        const phi = Math.acos(2 * (i / points) - 1);
        
        const x = Math.sin(phi) * Math.cos(theta);
        const y = Math.sin(phi) * Math.sin(theta);
        const z = Math.cos(phi);
        const w = Math.sin(t * 0.01 + i * 0.1);
        
        // Project to 2D
        const perspective = 2 / (3 - w);
        const px = cx + x * size * perspective;
        const py = cy + y * size * perspective;
        
        const gradient = ctx.createRadialGradient(px, py, 0, px, py, 4);
        gradient.addColorStop(0, `rgba(236, 72, 153, ${0.5 + w * 0.5})`);
        gradient.addColorStop(1, 'rgba(236, 72, 153, 0)');
        
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(px, py, 4, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const drawTesseract = (ctx: CanvasRenderingContext2D, cx: number, cy: number, size: number, t: number) => {
      // Simplified tesseract visualization
      const innerSize = size * 0.5;
      const offset = Math.sin(t * 0.02) * 30;
      
      // Draw outer cube
      ctx.strokeStyle = 'rgba(147, 51, 234, 0.8)';
      ctx.lineWidth = 2;
      ctx.strokeRect(cx - size, cy - size, size * 2, size * 2);
      
      // Draw inner cube
      ctx.strokeStyle = 'rgba(236, 72, 153, 0.8)';
      ctx.strokeRect(cx - innerSize + offset, cy - innerSize + offset, innerSize * 2, innerSize * 2);
      
      // Draw connecting lines
      ctx.strokeStyle = 'rgba(6, 182, 212, 0.6)';
      const corners = [
        [-1, -1], [1, -1], [1, 1], [-1, 1]
      ];
      
      corners.forEach(([dx, dy]) => {
        ctx.beginPath();
        ctx.moveTo(cx + dx * size, cy + dy * size);
        ctx.lineTo(cx + dx * innerSize + offset, cy + dy * innerSize + offset);
        ctx.stroke();
      });
    };

    const drawManifold = (ctx: CanvasRenderingContext2D, cx: number, cy: number, size: number, t: number) => {
      // Draw a curved manifold surface
      const points = 50;
      for (let i = 0; i < points; i++) {
        for (let j = 0; j < points; j++) {
          const u = (i / points) * Math.PI * 2;
          const v = (j / points) * Math.PI;
          
          const x = Math.sin(u) * Math.sin(v);
          const y = Math.cos(u) * Math.sin(v);
          const z = Math.cos(v);
          
          const w = Math.sin(t * 0.01 + u + v);
          
          const perspective = 2 / (3 - w);
          const px = cx + x * size * perspective;
          const py = cy + y * size * perspective;
          
          const gradient = ctx.createRadialGradient(px, py, 0, px, py, 2);
          gradient.addColorStop(0, `rgba(6, 182, 212, ${0.3 + w * 0.5})`);
          gradient.addColorStop(1, 'rgba(6, 182, 212, 0)');
          
          ctx.fillStyle = gradient;
          ctx.beginPath();
          ctx.arc(px, py, 2, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    };

    drawMultidimensional();

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      cancelAnimationFrame(animationFrame);
    };
  }, [rotation, scale, isPlaying, selectedView, projection]);

  const handleReset = () => {
    setRotation({ x: 0, y: 0, z: 0, w: 0 });
    setScale(1);
  };

  return (
    <div className="space-y-6">
      <Card className="bg-white/[0.02] border-white/5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Box className="w-5 h-5 text-purple-400" />
            Multi-Dimensional Visualization
          </CardTitle>
          <CardDescription>
            Visualize 4D and higher-dimensional spaces in real-time
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs value={selectedView} onValueChange={setSelectedView}>
            <TabsList className="bg-white/[0.02] border-white/5">
              <TabsTrigger value="hypercube">
                <Box className="w-4 h-4 mr-2" />
                Hypercube
              </TabsTrigger>
              <TabsTrigger value="hypersphere">
                <Circle className="w-4 h-4 mr-2" />
                Hypersphere
              </TabsTrigger>
              <TabsTrigger value="tesseract">
                <Diamond className="w-4 h-4 mr-2" />
                Tesseract
              </TabsTrigger>
              <TabsTrigger value="manifold">
                <Layers className="w-4 h-4 mr-2" />
                Manifold
              </TabsTrigger>
            </TabsList>

            <TabsContent value={selectedView} className="space-y-4">
              {/* Visualization Canvas */}
              <div className="relative w-full h-[500px] bg-slate-950 rounded-lg overflow-hidden border border-purple-500/20">
                <canvas ref={canvasRef} className="w-full h-full" />
                
                {/* Overlay Info */}
                <div className="absolute top-4 left-4 space-y-2">
                  <Badge className="bg-purple-500 text-white">
                    <Zap className="w-3 h-3 mr-1" />
                    {dimensions}D Visualization
                  </Badge>
                  <Badge className="bg-cyan-500 text-white">
                    <Eye className="w-3 h-3 mr-1" />
                    {selectedView.toUpperCase()}
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
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="space-y-3">
                  <label className="text-sm text-gray-400">Rotation X</label>
                  <Slider
                    value={[rotation.x]}
                    onValueChange={([v]) => setRotation(prev => ({ ...prev, x: (v as any)[0] }))}
                    max={Math.PI * 2}
                    step={0.1}
                  />
                </div>
                <div className="space-y-3">
                  <label className="text-sm text-gray-400">Rotation Y</label>
                  <Slider
                    value={[rotation.y]}
                    onValueChange={([v]) => setRotation(prev => ({ ...prev, y: (v as any)[0] }))}
                    max={Math.PI * 2}
                    step={0.1}
                  />
                </div>
                <div className="space-y-3">
                  <label className="text-sm text-gray-400">Rotation Z</label>
                  <Slider
                    value={[rotation.z]}
                    onValueChange={([v]) => setRotation(prev => ({ ...prev, z: (v as any)[0] }))}
                    max={Math.PI * 2}
                    step={0.1}
                  />
                </div>
                <div className="space-y-3">
                  <label className="text-sm text-gray-400">Rotation W (4D)</label>
                  <Slider
                    value={[rotation.w]}
                    onValueChange={([v]) => setRotation(prev => ({ ...prev, w: (v as any)[0] }))}
                    max={Math.PI * 2}
                    step={0.1}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-3">
                  <label className="text-sm text-gray-400">Scale</label>
                  <Slider
                    value={[scale]}
                    onValueChange={([v]) => setScale((v as any)[0])}
                    min={0.5}
                    max={2}
                    step={0.1}
                  />
                </div>
                <div className="space-y-3">
                  <label className="text-sm text-gray-400">Dimensions</label>
                  <Slider
                    value={[dimensions]}
                    onValueChange={([v]) => setDimensions((v as any)[0])}
                    min={3}
                    max={10}
                    step={1}
                  />
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      {/* Dimension Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-white/[0.02] border-white/5">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Box className="w-4 h-4 text-purple-400" />
              Hypercube
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-gray-400">
              4D cube with 16 vertices and 32 edges
            </p>
          </CardContent>
        </Card>

        <Card className="bg-white/[0.02] border-white/5">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Circle className="w-4 h-4 text-pink-400" />
              Hypersphere
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-gray-400">
              4D sphere with all points equidistant from center
            </p>
          </CardContent>
        </Card>

        <Card className="bg-white/[0.02] border-white/5">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Diamond className="w-4 h-4 text-cyan-400" />
              Tesseract
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-gray-400">
              4D hypercube with nested cube structure
            </p>
          </CardContent>
        </Card>

        <Card className="bg-white/[0.02] border-white/5">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Layers className="w-4 h-4 text-green-400" />
              Manifold
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-gray-400">
              Curved surface in higher-dimensional space
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
