import React, { useState, useEffect, useRef, useCallback } from "react";

// --- Types ---
export type VizState = "idle" | "processing" | "active";

interface NodeData {
  id: string;
  layerIndex: number;
  nodeIndex: number;
  x: number;
  y: number;
  activation: number;
}

interface Signal {
  id: string;
  fromNode: string;
  toNode: string;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  progress: number;
  speed: number;
}

interface Connection {
  from: string;
  to: string;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
}

interface TooltipInfo {
  nodeId: string;
  layerName: string;
  activation: number;
  x: number;
  y: number;
}

// --- Constants ---
const LAYER_CONFIGS = [
  { name: "Input", nodes: 8, color: "#3b82f6", glowColor: "#60a5fa" },
  { name: "Processing", nodes: 10, color: "#06b6d4", glowColor: "#22d3ee" },
  { name: "Reasoning", nodes: 8, color: "#8b5cf6", glowColor: "#a78bfa" },
  { name: "Memory", nodes: 6, color: "#ec4899", glowColor: "#f472b6" },
  { name: "Output", nodes: 4, color: "#10b981", glowColor: "#34d399" },
];

const SVG_WIDTH = 800;
const SVG_HEIGHT = 500;
const LAYER_SPACING = SVG_WIDTH / (LAYER_CONFIGS.length + 1);
const NODE_RADIUS = 6;
const MAX_SIGNALS = 50;

// --- Utility Functions ---
function generateNodes(): NodeData[] {
  const nodes: NodeData[] = [];
  LAYER_CONFIGS.forEach((layer, layerIndex) => {
    const x = LAYER_SPACING * (layerIndex + 1);
    const nodeSpacing = SVG_HEIGHT / (layer.nodes + 1);
    for (let i = 0; i < layer.nodes; i++) {
      nodes.push({
        id: `${layerIndex}-${i}`,
        layerIndex,
        nodeIndex: i,
        x,
        y: nodeSpacing * (i + 1),
        activation: 0,
      });
    }
  });
  return nodes;
}

function generateConnections(nodes: NodeData[]): Connection[] {
  const connections: Connection[] = [];
  for (let i = 0; i < LAYER_CONFIGS.length - 1; i++) {
    const currentLayerNodes = nodes.filter((n) => n.layerIndex === i);
    const nextLayerNodes = nodes.filter((n) => n.layerIndex === i + 1);
    for (const fromNode of currentLayerNodes) {
      for (const toNode of nextLayerNodes) {
        connections.push({
          from: fromNode.id,
          to: toNode.id,
          fromX: fromNode.x,
          fromY: fromNode.y,
          toX: toNode.x,
          toY: toNode.y,
        });
      }
    }
  }
  return connections;
}

function getLayerColor(layerIndex: number): string {
  return LAYER_CONFIGS[layerIndex]?.color || "#3b82f6";
}

function getLayerGlowColor(layerIndex: number): string {
  return LAYER_CONFIGS[layerIndex]?.glowColor || "#60a5fa";
}

function getLayerName(layerIndex: number): string {
  return LAYER_CONFIGS[layerIndex]?.name || "Unknown";
}

// --- Component ---
const NeuralNetworkViz: React.FC<{
  state?: VizState;
  className?: string;
}> = ({ state = "idle", className = "" }) => {
  const [nodes, setNodes] = useState<NodeData[]>(() => generateNodes());
  const [signals, setSignals] = useState<Signal[]>([]);
  const [hoveredNode, setHoveredNode] = useState<TooltipInfo | null>(null);
  const [isClicked, setIsClicked] = useState(false);
  const animationRef = useRef<number>(0);
  const lastSignalTime = useRef(0);
  const svgRef = useRef<SVGSVGElement>(null);
  const connections = useRef<Connection[]>([]);

  // Initialize connections
  useEffect(() => {
    connections.current = generateConnections(nodes);
  }, [nodes]);

  // Signal spawning based on state
  const getSignalSpawnRate = useCallback((): number => {
    switch (state) {
      case "idle":
        return 800;
      case "processing":
        return 200;
      case "active":
        return 80;
      default:
        return 800;
    }
  }, [state]);

  const getSignalSpeed = useCallback((): number => {
    switch (state) {
      case "idle":
        return 0.003;
      case "processing":
        return 0.008;
      case "active":
        return 0.015;
      default:
        return 0.003;
    }
  }, [state]);

  const getDecayRate = useCallback((): number => {
    switch (state) {
      case "idle":
        return 0.002;
      case "processing":
        return 0.008;
      case "active":
        return 0.02;
      default:
        return 0.002;
    }
  }, [state]);

  const getActivationAmount = useCallback((): number => {
    switch (state) {
      case "idle":
        return 0.15;
      case "processing":
        return 0.5;
      case "active":
        return 1.0;
      default:
        return 0.15;
    }
  }, [state]);

  // Spawn signals
  const spawnSignal = useCallback(() => {
    setSignals((prev) => {
      if (prev.length >= MAX_SIGNALS) return prev;
      const conns = connections.current;
      if (conns.length === 0) return prev;
      const conn = conns[Math.floor(Math.random() * conns.length)];
      const id = `signal-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      const speed = getSignalSpeed() * (0.7 + Math.random() * 0.6);
      return [
        ...prev,
        {
          id,
          fromNode: conn.from,
          toNode: conn.to,
          fromX: conn.fromX,
          fromY: conn.fromY,
          toX: conn.toX,
          toY: conn.toY,
          progress: 0,
          speed,
        },
      ];
    });
  }, [getSignalSpeed]);

  // Animation loop
  useEffect(() => {
    let running = true;
    const animate = (timestamp: number) => {
      if (!running) return;

      // Spawn new signals
      if (timestamp - lastSignalTime.current > getSignalSpawnRate()) {
        spawnSignal();
        lastSignalTime.current = timestamp;
      }

      // Update signals and node activations
      setSignals((prevSignals) => {
        const updatedSignals: Signal[] = [];
        const activatedNodes = new Map<string, number>();

        for (const signal of prevSignals) {
          const newProgress = signal.progress + signal.speed;
          if (newProgress >= 1) {
            // Signal reached destination, activate target node
            activatedNodes.set(
              signal.toNode,
              (activatedNodes.get(signal.toNode) || 0) + getActivationAmount(),
            );
          } else {
            updatedSignals.push({ ...signal, progress: newProgress });
          }
        }

        // Apply node activations
        if (activatedNodes.size > 0) {
          setNodes((prevNodes) =>
            prevNodes.map((node) => {
              const boost = activatedNodes.get(node.id);
              if (boost) {
                return {
                  ...node,
                  activation: Math.min(1, node.activation + boost),
                };
              }
              return node;
            }),
          );
        }

        return updatedSignals;
      });

      // Decay node activations
      const decayRate = getDecayRate();
      setNodes((prevNodes) =>
        prevNodes.map((node) => ({
          ...node,
          activation: Math.max(0, node.activation - decayRate),
        })),
      );

      // Idle pulse
      if (state === "idle" && Math.random() < 0.02) {
        setNodes((prevNodes) => {
          const idx = Math.floor(Math.random() * prevNodes.length);
          return prevNodes.map((node, i) =>
            i === idx
              ? { ...node, activation: Math.min(1, node.activation + 0.1) }
              : node,
          );
        });
      }

      animationRef.current = requestAnimationFrame(animate);
    };

    animationRef.current = requestAnimationFrame(animate);
    return () => {
      running = false;
      cancelAnimationFrame(animationRef.current);
    };
  }, [state, spawnSignal, getSignalSpawnRate, getSignalSpeed, getDecayRate, getActivationAmount]);

  // Manual trigger on click
  const handleClick = useCallback(() => {
    setIsClicked(true);
    // Burst of signals
    for (let i = 0; i < 15; i++) {
      setTimeout(() => spawnSignal(), i * 50);
    }
    // Activate random nodes
    setNodes((prevNodes) =>
      prevNodes.map((node) => ({
        ...node,
        activation: Math.min(1, node.activation + Math.random() * 0.6),
      })),
    );
    setTimeout(() => setIsClicked(false), 500);
  }, [spawnSignal]);

  const handleNodeHover = useCallback(
    (node: NodeData, event: React.MouseEvent<SVGCircleElement>) => {
      const svgRect = svgRef.current?.getBoundingClientRect();
      setHoveredNode({
        nodeId: node.id,
        layerName: getLayerName(node.layerIndex),
        activation: node.activation,
        x: event.clientX - (svgRect?.left || 0),
        y: event.clientY - (svgRect?.top || 0),
      });
    },
    [],
  );

  const handleNodeLeave = useCallback(() => {
    setHoveredNode(null);
  }, []);

  // Interpolate signal position
  const getSignalPosition = (signal: Signal) => ({
    x: signal.fromX + (signal.toX - signal.fromX) * signal.progress,
    y: signal.fromY + (signal.toY - signal.fromY) * signal.progress,
  });

  return (
    <div className={`relative select-none ${className}`}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
        className="w-full h-auto"
        style={{ background: "#0a0d12" }}
        onClick={handleClick}
      >
        <defs>
          {/* Glow filter */}
          <filter id="nodeGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="signalGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          {/* Layer gradients */}
          {LAYER_CONFIGS.map((layer, idx) => (
            <radialGradient key={`grad-${idx}`} id={`layerGrad-${idx}`}>
              <stop offset="0%" stopColor={layer.glowColor} />
              <stop offset="100%" stopColor={layer.color} />
            </radialGradient>
          ))}
        </defs>

        {/* Layer labels */}
        {LAYER_CONFIGS.map((layer, idx) => (
          <text
            key={`label-${idx}`}
            x={LAYER_SPACING * (idx + 1)}
            y={30}
            textAnchor="middle"
            fill={layer.color}
            fontSize="12"
            fontWeight="600"
            opacity="0.7"
            style={{ fontFamily: "monospace" }}
          >
            {layer.name}
          </text>
        ))}

        {/* Connections */}
        {connections.current.map((conn, idx) => (
          <line
            key={`conn-${idx}`}
            x1={conn.fromX}
            y1={conn.fromY}
            x2={conn.toX}
            y2={conn.toY}
            stroke="#1e293b"
            strokeWidth="0.5"
            opacity="0.4"
          />
        ))}

        {/* Signals */}
        {signals.map((signal) => {
          const pos = getSignalPosition(signal);
          const targetLayer = nodes.find((n) => n.id === signal.toNode)?.layerIndex ?? 0;
          return (
            <circle
              key={signal.id}
              cx={pos.x}
              cy={pos.y}
              r="2"
              fill={getLayerGlowColor(targetLayer)}
              filter="url(#signalGlow)"
              opacity={0.9}
            />
          );
        })}

        {/* Nodes */}
        {nodes.map((node) => {
          const baseColor = getLayerColor(node.layerIndex);
          const glowColor = getLayerGlowColor(node.layerIndex);
          const currentActivation = node.activation;
          const radius = NODE_RADIUS + currentActivation * 4;
          const opacity = 0.4 + currentActivation * 0.6;

          return (
            <g key={node.id}>
              {/* Outer glow */}
              {currentActivation > 0.1 && (
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={radius * 2}
                  fill="none"
                  stroke={glowColor}
                  strokeWidth="2"
                  opacity={currentActivation * 0.3}
                  filter="url(#nodeGlow)"
                />
              )}
              {/* Main node */}
              <circle
                cx={node.x}
                cy={node.y}
                r={radius}
                fill={`url(#layerGrad-${node.layerIndex})`}
                stroke={baseColor}
                strokeWidth="1"
                opacity={opacity}
                style={{
                  transition: "r 0.15s ease-out, opacity 0.15s ease-out",
                  cursor: "pointer",
                }}
                onMouseEnter={(e) => handleNodeHover(node, e)}
                onMouseLeave={handleNodeLeave}
              />
              {/* Inner highlight */}
              <circle
                cx={node.x}
                cy={node.y}
                r={radius * 0.4}
                fill="white"
                opacity={currentActivation * 0.5}
              />
            </g>
          );
        })}

        {/* Click ripple effect */}
        {isClicked && (
          <circle
            cx={SVG_WIDTH / 2}
            cy={SVG_HEIGHT / 2}
            r="20"
            fill="none"
            stroke="#06b6d4"
            strokeWidth="2"
            opacity="0.5"
          >
            <animate
              attributeName="r"
              from="20"
              to="200"
              dur="0.5s"
              fill="freeze"
            />
            <animate
              attributeName="opacity"
              from="0.5"
              to="0"
              dur="0.5s"
              fill="freeze"
            />
          </circle>
        )}
      </svg>

      {/* Tooltip */}
      {hoveredNode && (
        <div
          className="absolute pointer-events-none z-10 rounded-lg border border-slate-700 bg-slate-900/95 px-3 py-2 text-xs shadow-xl backdrop-blur-sm"
          style={{
            left: Math.min(hoveredNode.x + 12, SVG_WIDTH - 150),
            top: hoveredNode.y - 40,
          }}
        >
          <div className="font-semibold text-slate-200">
            Layer: {hoveredNode.layerName}
          </div>
          <div className="text-slate-400">Node: {hoveredNode.nodeId}</div>
          <div className="mt-1 flex items-center gap-2">
            <span className="text-slate-400">Activation:</span>
            <div className="h-1.5 w-16 rounded-full bg-slate-700 overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-150"
                style={{
                  width: `${hoveredNode.activation * 100}%`,
                  backgroundColor: getLayerGlowColor(
                    parseInt(hoveredNode.nodeId.split("-")[0]),
                  ),
                }}
              />
            </div>
            <span className="font-mono text-slate-300">
              {(hoveredNode.activation * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      )}

      {/* State indicator */}
      <div className="absolute bottom-2 left-2 flex items-center gap-2 rounded-md bg-slate-900/80 px-2 py-1 text-xs font-mono backdrop-blur-sm">
        <span className="text-slate-500">STATE:</span>
        <span
          className="font-bold uppercase"
          style={{
            color:
              state === "active"
                ? "#10b981"
                : state === "processing"
                  ? "#06b6d4"
                  : "#64748b",
          }}
        >
          {state}
        </span>
        <span
          className="h-2 w-2 rounded-full animate-pulse"
          style={{
            backgroundColor:
              state === "active"
                ? "#10b981"
                : state === "processing"
                  ? "#06b6d4"
                  : "#64748b",
          }}
        />
      </div>
    </div>
  );
};

export default NeuralNetworkViz;
