'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Network, Search, ZoomIn, ZoomOut, Maximize, Brain, Code, Database, Globe, Settings, Link } from 'lucide-react';

interface GraphNode {
  id: string;
  label: string;
  type: 'concept' | 'entity' | 'action' | 'data';
  x: number;
  y: number;
  radius: number;
}

interface GraphEdge {
  source: string;
  target: string;
  label: string;
}

const NODE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  concept: { bg: 'from-blue-500/20 to-blue-600/10', border: 'border-blue-400/40', text: 'text-blue-400' },
  entity: { bg: 'from-purple-500/20 to-purple-600/10', border: 'border-purple-400/40', text: 'text-purple-400' },
  action: { bg: 'from-emerald-500/20 to-emerald-600/10', border: 'border-emerald-400/40', text: 'text-emerald-400' },
  data: { bg: 'from-amber-500/20 to-amber-600/10', border: 'border-amber-400/40', text: 'text-amber-400' },
};

const MOCK_NODES: GraphNode[] = [
  { id: '1', label: 'JARVIS Core', type: 'concept', x: 400, y: 250, radius: 35 },
  { id: '2', label: 'AI Engine', type: 'concept', x: 250, y: 150, radius: 28 },
  { id: '3', label: 'Knowledge Base', type: 'data', x: 550, y: 150, radius: 28 },
  { id: '4', label: 'Agent System', type: 'action', x: 200, y: 300, radius: 25 },
  { id: '5', label: 'Memory Module', type: 'entity', x: 600, y: 300, radius: 25 },
  { id: '6', label: 'NLP Pipeline', type: 'concept', x: 150, y: 200, radius: 22 },
  { id: '7', label: 'API Gateway', type: 'data', x: 650, y: 200, radius: 22 },
  { id: '8', label: 'Task Scheduler', type: 'action', x: 300, y: 400, radius: 22 },
  { id: '9', label: 'Vector DB', type: 'data', x: 500, y: 400, radius: 22 },
  { id: '10', label: 'Tool Executor', type: 'action', x: 100, y: 350, radius: 20 },
  { id: '11', label: 'Sentiment Analysis', type: 'concept', x: 700, y: 350, radius: 20 },
  { id: '12', label: 'Embeddings', type: 'data', x: 400, y: 120, radius: 20 },
  { id: '13', label: 'Automation', type: 'action', x: 250, y: 450, radius: 18 },
  { id: '14', label: 'Monitoring', type: 'entity', x: 550, y: 450, radius: 18 },
  { id: '15', label: 'Recovery System', type: 'action', x: 100, y: 150, radius: 18 },
];

const MOCK_EDGES: GraphEdge[] = [
  { source: '1', target: '2', label: 'uses' },
  { source: '1', target: '3', label: 'accesses' },
  { source: '1', target: '4', label: 'manages' },
  { source: '2', target: '6', label: 'includes' },
  { source: '2', target: '12', label: 'processes' },
  { source: '3', target: '5', label: 'stores in' },
  { source: '3', target: '9', label: 'indexed by' },
  { source: '4', target: '8', label: 'schedules' },
  { source: '4', target: '10', label: 'executes' },
  { source: '5', target: '11', label: 'analyzes' },
  { source: '6', target: '15', label: 'triggers' },
  { source: '7', target: '3', label: 'routes to' },
  { source: '8', target: '13', label: 'automates' },
  { source: '9', target: '5', label: 'supports' },
  { source: '10', target: '13', label: 'enables' },
  { source: '11', target: '14', label: 'feeds' },
  { source: '1', target: '7', label: 'exposes' },
];

export default function KnowledgeGraphApp() {
  const [nodes, setNodes] = useState<GraphNode[]>(MOCK_NODES);
  const [edges] = useState<GraphEdge[]>(MOCK_EDGES);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [zoom, setZoom] = useState(1);
  const [isDragging, setIsDragging] = useState<string | null>(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const svgRef = useRef<SVGSVGElement>(null);

  const filteredNodes = searchQuery
    ? nodes.filter((n) => n.label.toLowerCase().includes(searchQuery.toLowerCase()))
    : nodes;

  const handleNodeMouseDown = useCallback(
    (nodeId: string, e: React.MouseEvent) => {
      e.stopPropagation();
      setIsDragging(nodeId);
      const node = nodes.find((n) => n.id === nodeId);
      if (node && svgRef.current) {
        const rect = svgRef.current.getBoundingClientRect();
        setDragOffset({
          x: e.clientX - rect.left - node.x,
          y: e.clientY - rect.top - node.y,
        });
      }
    },
    [nodes]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isDragging || !svgRef.current) return;
      const rect = svgRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left - dragOffset.x;
      const y = e.clientY - rect.top - dragOffset.y;

      setNodes((prev) =>
        prev.map((n) => (n.id === isDragging ? { ...n, x, y } : n))
      );
    },
    [isDragging, dragOffset]
  );

  const handleMouseUp = useCallback(() => {
    setIsDragging(null);
  }, []);

  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelectedNode(node);
  }, []);

  const getEdgePath = (source: GraphNode, target: GraphNode) => {
    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const dr = Math.sqrt(dx * dx + dy * dy) * 1.2;
    return `M${source.x},${source.y} A${dr},${dr} 0 0,1 ${target.x},${target.y}`;
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border/50 bg-card/30">
        <div className="flex items-center gap-2">
          <Network className="w-4 h-4 text-primary" />
          <span className="text-sm font-medium">Knowledge Graph</span>
        </div>

        <div className="flex items-center gap-2">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-foreground/30" />
            <input
              type="text"
              placeholder="Search nodes..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-8 pl-8 pr-3 w-40 bg-white/5 border border-border/50 rounded-lg text-xs text-foreground placeholder:text-foreground/30 focus:outline-none focus:border-primary/50 transition-all"
            />
          </div>

          {/* Zoom controls */}
          <button
            onClick={() => setZoom((z) => Math.max(0.5, z - 0.1))}
            className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground transition-colors"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <span className="text-xs text-foreground/50 w-10 text-center">{Math.round(zoom * 100)}%</span>
          <button
            onClick={() => setZoom((z) => Math.min(2, z + 0.1))}
            className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground transition-colors"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            onClick={() => setZoom(1)}
            className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground transition-colors"
          >
            <Maximize className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Graph Content */}
      <div className="flex-1 relative overflow-hidden bg-[#060a10]">
        {/* Background pattern */}
        <div className="absolute inset-0 bg-dots opacity-20" />

        {/* SVG Graph */}
        <svg
          ref={svgRef}
          className="w-full h-full"
          viewBox="0 0 800 500"
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          style={{ transform: `scale(${zoom})`, transformOrigin: 'center center' }}
        >
          {/* Edges */}
          {edges.map((edge, idx) => {
            const source = nodes.find((n) => n.id === edge.source);
            const target = nodes.find((n) => n.id === edge.target);
            if (!source || !target) return null;

            return (
              <g key={idx}>
                <path
                  d={getEdgePath(source, target)}
                  fill="none"
                  stroke="hsl(var(--border) / 0.3)"
                  strokeWidth={1.5}
                  className="transition-all duration-200"
                />
                {/* Edge label */}
                <text
                  x={(source.x + target.x) / 2}
                  y={(source.y + target.y) / 2 - 5}
                  textAnchor="middle"
                  className="text-[8px] fill-foreground/30"
                >
                  {edge.label}
                </text>
              </g>
            );
          })}

          {/* Nodes */}
          {filteredNodes.map((node) => {
            const colors = NODE_COLORS[node.type];
            const isSelected = selectedNode?.id === node.id;

            return (
              <g
                key={node.id}
                onMouseDown={(e) => handleNodeMouseDown(node.id, e)}
                onClick={() => handleNodeClick(node)}
                className="cursor-pointer"
              >
                {/* Glow effect */}
                {isSelected && (
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={node.radius + 8}
                    fill="none"
                    stroke="hsl(var(--primary) / 0.3)"
                    strokeWidth={2}
                  />
                )}

                {/* Node circle */}
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={node.radius}
                  fill={`url(#grad-${node.type})`}
                  stroke={isSelected ? 'hsl(var(--primary))' : 'hsl(var(--border) / 0.5)'}
                  strokeWidth={isSelected ? 2 : 1}
                  className="transition-all duration-200"
                />

                {/* Label */}
                <text
                  x={node.x}
                  y={node.y}
                  textAnchor="middle"
                  dominantBaseline="central"
                  className="text-[10px] font-medium fill-foreground/80 pointer-events-none"
                >
                  {node.label}
                </text>
              </g>
            );
          })}

          {/* Gradients */}
          <defs>
            {Object.entries(NODE_COLORS).map(([type, colors]) => (
              <radialGradient key={type} id={`grad-${type}`} cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="hsl(var(--primary) / 0.2)" />
                <stop offset="100%" stopColor="hsl(var(--background) / 0.1)" />
              </radialGradient>
            ))}
          </defs>
        </svg>

        {/* Legend */}
        <div className="absolute bottom-3 left-3 glass rounded-lg px-3 py-2 border border-border/50">
          <div className="flex items-center gap-3">
            {Object.entries(NODE_COLORS).map(([type, colors]) => (
              <div key={type} className="flex items-center gap-1.5">
                <div className={`w-2.5 h-2.5 rounded-full ${colors.text}`} />
                <span className="text-[10px] text-foreground/50 capitalize">{type}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Stats */}
        <div className="absolute top-3 right-3 glass rounded-lg px-3 py-2 border border-border/50">
          <div className="flex items-center gap-4 text-[10px] text-foreground/50">
            <span>{filteredNodes.length} nodes</span>
            <span>{edges.length} edges</span>
          </div>
        </div>
      </div>

      {/* Selected Node Details */}
      {selectedNode && (
        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="absolute bottom-16 left-1/2 -translate-x-1/2 glass rounded-xl px-4 py-3 border border-border/50 min-w-[250px]"
        >
          <div className="flex items-center gap-3">
            <div
              className={`w-10 h-10 rounded-lg bg-gradient-to-br ${NODE_COLORS[selectedNode.type].bg} ${NODE_COLORS[selectedNode.type].border} border flex items-center justify-center`}
            >
              <Brain className={`w-5 h-5 ${NODE_COLORS[selectedNode.type].text}`} />
            </div>
            <div>
              <h4 className="text-sm font-semibold text-foreground">{selectedNode.label}</h4>
              <p className="text-[10px] text-foreground/40 capitalize">{selectedNode.type}</p>
            </div>
            <button
              onClick={() => setSelectedNode(null)}
              className="ml-auto text-foreground/30 hover:text-foreground/60"
            >
              <Link className="w-4 h-4" />
            </button>
          </div>
          <div className="mt-2 flex items-center gap-3 text-[10px] text-foreground/50">
            <span>Connections: {edges.filter((e) => e.source === selectedNode.id || e.target === selectedNode.id).length}</span>
          </div>
        </motion.div>
      )}
    </div>
  );
}
