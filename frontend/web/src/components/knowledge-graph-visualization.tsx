'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { ZoomIn, ZoomOut, RefreshCw, Maximize2, Network } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';

interface GraphNode {
  id: string;
  label: string;
  category: string;
  size: number;
  x: number;
  y: number;
}

interface GraphEdge {
  source: string;
  target: string;
  weight: number;
  relation: string;
}

interface KnowledgeGraphProps {
  nodes?: GraphNode[];
  edges?: GraphEdge[];
  height?: number;
  interactive?: boolean;
}

const CATEGORY_COLORS: Record<string, string> = {
  system: '#3b82f6',
  ai: '#8b5cf6',
  memory: '#f59e0b',
  knowledge: '#10b981',
  agents: '#ec4899',
  interface: '#06b6d4',
  tools: '#ef4444',
  default: '#64748b',
};

export function KnowledgeGraphVisualization({ 
  nodes: initialNodes, 
  edges: initialEdges,
  height = 500,
  interactive = true 
}: KnowledgeGraphProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [nodes, setNodes] = useState<GraphNode[]>(initialNodes || []);
  const [edges, setEdges] = useState<GraphEdge[]>(initialEdges || []);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragNode, setDragNode] = useState<string | null>(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const animationRef = useRef<number | undefined>(undefined);

  // Fetch sample data if not provided
  useEffect(() => {
    if (!initialNodes || !initialEdges) {
      fetch('/api/v1/dashboard/knowledge-graph/sample')
        .then(res => res.json())
        .then(data => {
          if (data.success && data.graph) {
            setNodes(data.graph.nodes || []);
            setEdges(data.graph.edges || []);
          }
        })
        .catch(err => console.error('Failed to load knowledge graph:', err));
    }
  }, [initialNodes, initialEdges]);

  // Canvas rendering
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    // Apply transformations
    ctx.save();
    ctx.translate(width / 2 + pan.x, height / 2 + pan.y);
    ctx.scale(zoom, zoom);

    // Draw edges
    edges.forEach(edge => {
      const source = nodes.find(n => n.id === edge.source);
      const target = nodes.find(n => n.id === edge.target);
      
      if (!source || !target) return;

      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      
      // Curved edges
      const midX = (source.x + target.x) / 2;
      const midY = (source.y + target.y) / 2 - 20;
      ctx.quadraticCurveTo(midX, midY, target.x, target.y);
      
      ctx.strokeStyle = `rgba(100, 116, 139, ${edge.weight * 0.6})`;
      ctx.lineWidth = edge.weight * 2;
      ctx.stroke();

      // Edge label
      if (zoom > 0.8) {
        ctx.fillStyle = 'rgba(148, 163, 184, 0.8)';
        ctx.font = '10px Inter';
        ctx.textAlign = 'center';
        ctx.fillText(edge.relation, midX, midY - 5);
      }
    });

    // Draw nodes
    nodes.forEach(node => {
      const color = CATEGORY_COLORS[node.category] || CATEGORY_COLORS.default;
      const radius = node.size * 15 * zoom;

      // Glow effect
      const gradient = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, radius * 2);
      gradient.addColorStop(0, `${color}40`);
      gradient.addColorStop(1, 'transparent');
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius * 2, 0, Math.PI * 2);
      ctx.fill();

      // Node circle
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = `${color}80`;
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();

      // Highlight selected node
      if (selectedNode?.id === node.id) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + 5, 0, Math.PI * 2);
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 3;
        ctx.stroke();
      }

      // Node label
      if (zoom > 0.5) {
        ctx.fillStyle = '#e2e8f0';
        ctx.font = `${Math.max(10, 12 * zoom)}px Inter`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(node.label, node.x, node.y + radius + 15);
      }
    });

    ctx.restore();
  }, [nodes, edges, zoom, pan, selectedNode]);

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

  // Handle mouse interactions
  const handleMouseDown = (e: React.MouseEvent) => {
    if (!interactive) return;
    
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const x = (e.clientX - rect.left - rect.width / 2 - pan.x) / zoom;
    const y = (e.clientY - rect.top - rect.height / 2 - pan.y) / zoom;

    // Check if clicking on a node
    const clickedNode = nodes.find(node => {
      const dx = x - node.x;
      const dy = y - node.y;
      return Math.sqrt(dx * dx + dy * dy) < node.size * 15;
    });

    if (clickedNode) {
      setDragNode(clickedNode.id);
      setSelectedNode(clickedNode);
    } else {
      setIsDragging(true);
      setSelectedNode(null);
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!interactive) return;

    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top });

    if (dragNode) {
      const x = (e.clientX - rect.left - rect.width / 2 - pan.x) / zoom;
      const y = (e.clientY - rect.top - rect.height / 2 - pan.y) / zoom;

      setNodes(prev => prev.map(node => 
        node.id === dragNode ? { ...node, x, y } : node
      ));
    } else if (isDragging) {
      setPan(prev => ({
        x: prev.x + e.movementX,
        y: prev.y + e.movementY,
      }));
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
    setDragNode(null);
  };

  const handleWheel = (e: React.WheelEvent) => {
    if (!interactive) return;
    e.preventDefault();
    
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setZoom(prev => Math.max(0.3, Math.min(3, prev * delta)));
  };

  // Auto-layout using force-directed algorithm (simplified)
  useEffect(() => {
    if (nodes.length === 0) return;

    const iterations = 100;
    const newNodes = [...nodes];
    
    for (let iter = 0; iter < iterations; iter++) {
      // Repulsion between all nodes
      for (let i = 0; i < newNodes.length; i++) {
        for (let j = i + 1; j < newNodes.length; j++) {
          const dx = newNodes[j].x - newNodes[i].x;
          const dy = newNodes[j].y - newNodes[i].y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          
          if (dist < 100) {
            const force = 1000 / (dist * dist);
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            
            newNodes[i].x -= fx;
            newNodes[i].y -= fy;
            newNodes[j].x += fx;
            newNodes[j].y += fy;
          }
        }
      }

      // Attraction along edges
      edges.forEach(edge => {
        const source = newNodes.find(n => n.id === edge.source);
        const target = newNodes.find(n => n.id === edge.target);
        
        if (!source || !target) return;

        const dx = target.x - source.x;
        const dy = target.y - source.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        
        const force = (dist - 80) * 0.01;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        
        source.x += fx;
        source.y += fy;
        target.x -= fx;
        target.y -= fy;
      });
    }

    setNodes(newNodes);
  }, []); // Run once on mount

  const handleZoomIn = () => setZoom(prev => Math.min(3, prev * 1.2));
  const handleZoomOut = () => setZoom(prev => Math.max(0.3, prev / 1.2));
  const handleReset = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  return (
    <Card className="relative overflow-hidden bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-2 border-blue-500/30 backdrop-blur-xl">
      {/* Header */}
      <div className="absolute top-4 left-4 z-10 flex items-center gap-3">
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-900/80 border border-blue-500/30">
          <Network className="h-4 w-4 text-blue-400" />
          <span className="text-sm font-semibold text-white">Knowledge Graph</span>
        </div>
        {selectedNode && (
          <motion.div
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            className="px-3 py-2 rounded-lg bg-blue-500/20 border border-blue-400/40"
          >
            <span className="text-xs text-blue-200">Selected: {selectedNode.label}</span>
            <Badge variant="outline" className="ml-2 bg-blue-500/30 text-blue-300 border-blue-400/50 text-[10px]">
              {selectedNode.category}
            </Badge>
          </motion.div>
        )}
      </div>

      {/* Controls */}
      <div className="absolute top-4 right-4 z-10 flex items-center gap-2">
        <Button
          size="sm"
          variant="ghost"
          onClick={handleZoomIn}
          className="h-8 w-8 p-0 bg-slate-900/80 border border-blue-500/30 hover:bg-blue-500/20"
        >
          <ZoomIn className="h-4 w-4 text-blue-400" />
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={handleZoomOut}
          className="h-8 w-8 p-0 bg-slate-900/80 border border-blue-500/30 hover:bg-blue-500/20"
        >
          <ZoomOut className="h-4 w-4 text-blue-400" />
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={handleReset}
          className="h-8 w-8 p-0 bg-slate-900/80 border border-blue-500/30 hover:bg-blue-500/20"
        >
          <Maximize2 className="h-4 w-4 text-blue-400" />
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => window.location.reload()}
          className="h-8 w-8 p-0 bg-slate-900/80 border border-blue-500/30 hover:bg-blue-500/20"
        >
          <RefreshCw className="h-4 w-4 text-blue-400" />
        </Button>
      </div>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 z-10 space-y-2">
        <div className="px-3 py-2 rounded-lg bg-slate-900/80 border border-blue-500/30">
          <p className="text-xs font-semibold text-cyan-200 mb-2">Categories</p>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(CATEGORY_COLORS).map(([category, color]) => (
              <div key={category} className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="text-[10px] text-cyan-200/70 capitalize">{category}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="absolute bottom-4 right-4 z-10 px-3 py-2 rounded-lg bg-slate-900/80 border border-blue-500/30">
        <div className="space-y-1">
          <div className="flex items-center justify-between gap-4">
            <span className="text-[10px] text-cyan-200/70">Nodes:</span>
            <span className="text-xs font-semibold text-white">{nodes.length}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-[10px] text-cyan-200/70">Edges:</span>
            <span className="text-xs font-semibold text-white">{edges.length}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-[10px] text-cyan-200/70">Zoom:</span>
            <span className="text-xs font-semibold text-white">{Math.round(zoom * 100)}%</span>
          </div>
        </div>
      </div>

      {/* Canvas */}
      <canvas
        ref={canvasRef}
        width={containerRef.current?.offsetWidth || 800}
        height={height}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        className="w-full cursor-grab active:cursor-grabbing"
        style={{ touchAction: 'none' }}
      />
    </Card>
  );
}
