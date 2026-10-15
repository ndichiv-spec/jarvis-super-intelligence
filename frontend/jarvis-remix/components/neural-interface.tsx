import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence, useMotionValue, useTransform, useSpring } from 'framer-motion';
import { Brain, Cpu, Zap, Activity, Network, Users, Bot, Eye, Heart, Sparkles } from 'lucide-react';

interface NeuralNetwork {
  id: string;
  name: string;
  layers: number;
  neurons: number[];
  connections: number;
  accuracy: number;
  status: 'training' | 'active' | 'idle' | 'error';
  type: 'cnn' | 'rnn' | 'transformer' | 'gan' | 'autoencoder';
}

interface NeuralSignal {
  timestamp: number;
  amplitude: number;
  frequency: number;
  source: string;
  confidence: number;
}

interface ThoughtPattern {
  id: string;
  pattern: string;
  confidence: number;
  category: 'logic' | 'creative' | 'emotional' | 'analytical';
  timestamp: string;
}

export function NeuralInterface() {
  const [networks, setNetworks] = useState<NeuralNetwork[]>([
    {
      id: '1',
      name: 'Visual Cortex',
      layers: 8,
      neurons: [1024, 512, 256, 128, 64, 32, 16, 8],
      connections: 1024000,
      accuracy: 0.94,
      status: 'active',
      type: 'cnn'
    },
    {
      id: '2',
      name: 'Language Center',
      layers: 12,
      neurons: [2048, 1024, 512, 256, 128, 64, 32, 16, 8, 4, 2, 1],
      connections: 2048000,
      accuracy: 0.97,
      status: 'active',
      type: 'transformer'
    },
    {
      id: '3',
      name: 'Memory System',
      layers: 6,
      neurons: [512, 256, 128, 64, 32, 16],
      connections: 512000,
      accuracy: 0.91,
      status: 'training',
      type: 'rnn'
    },
    {
      id: '4',
      name: 'Creative Engine',
      layers: 10,
      neurons: [1024, 512, 256, 128, 64, 32, 16, 8, 4, 2],
      connections: 1024000,
      accuracy: 0.88,
      status: 'idle',
      type: 'gan'
    }
  ]);

  const [signals, setSignals] = useState<NeuralSignal[]>([]);
  const [thoughts, setThoughts] = useState<ThoughtPattern[]>([
    {
      id: '1',
      pattern: 'Quantum entanglement optimization',
      confidence: 0.92,
      category: 'analytical',
      timestamp: new Date().toISOString()
    },
    {
      id: '2',
      pattern: 'Creative solution synthesis',
      confidence: 0.87,
      category: 'creative',
      timestamp: new Date().toISOString()
    }
  ]);

  const [isConnected, setIsConnected] = useState(true);
  const [brainActivity, setBrainActivity] = useState(0.75);
  const [synapticStrength, setSynapticStrength] = useState(0.83);
  const [neuralPlasticity, setNeuralPlasticity] = useState(0.91);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const signalCanvasRef = useRef<HTMLCanvasElement>(null);
  const networkCanvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const interval = setInterval(() => {
      setBrainActivity(prev => Math.max(0.3, Math.min(1, prev + (Math.random() - 0.5) * 0.1)));
      setSynapticStrength(prev => Math.max(0.5, Math.min(1, prev + (Math.random() - 0.5) * 0.05)));
      setNeuralPlasticity(prev => Math.max(0.7, Math.min(1, prev + (Math.random() - 0.5) * 0.03)));

      // Generate new neural signals
      const newSignal: NeuralSignal = {
        timestamp: Date.now(),
        amplitude: Math.random() * 100,
        frequency: Math.random() * 1000,
        source: ['Visual Cortex', 'Language Center', 'Memory System', 'Creative Engine'][Math.floor(Math.random() * 4)],
        confidence: Math.random() * 0.3 + 0.7,
      };

      setSignals(prev => [...prev.slice(-99), newSignal]);

      // Update network accuracies
      setNetworks(prev => prev.map(network => ({
        ...network,
        accuracy: Math.max(0.8, Math.min(0.99, network.accuracy + (Math.random() - 0.5) * 0.02)),
      })));
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const drawBrainActivity = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      // Draw brain outline
      ctx.strokeStyle = '#8b5cf6';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.ellipse(canvas.width / 2, canvas.height / 2, canvas.width / 2 - 20, canvas.height / 2 - 20, 0, 0, Math.PI * 2);
      ctx.stroke();

      // Draw activity regions
      const regions = [
        { x: canvas.width / 2, y: canvas.height / 3, radius: 30, activity: brainActivity },
        { x: canvas.width / 3, y: canvas.height / 2, radius: 25, activity: synapticStrength },
        { x: canvas.width * 2 / 3, y: canvas.height / 2, radius: 25, activity: neuralPlasticity },
      ];

      regions.forEach(region => {
        const gradient = ctx.createRadialGradient(region.x, region.y, 0, region.x, region.y, region.radius);
        gradient.addColorStop(0, `rgba(139, 92, 246, ${region.activity})`);
        gradient.addColorStop(1, 'rgba(139, 92, 246, 0)');
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(region.x, region.y, region.radius, 0, Math.PI * 2);
        ctx.fill();
      });

      // Draw neural connections
      for (let i = 0; i < 20; i++) {
        const x1 = Math.random() * canvas.width;
        const y1 = Math.random() * canvas.height;
        const x2 = Math.random() * canvas.width;
        const y2 = Math.random() * canvas.height;
        
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.strokeStyle = `rgba(139, 92, 246, ${Math.random() * 0.3})`;
        ctx.lineWidth = Math.random() * 2;
        ctx.stroke();
      }
    };

    drawBrainActivity();
    const animationId = requestAnimationFrame(drawBrainActivity);

    return () => cancelAnimationFrame(animationId);
  }, [brainActivity, synapticStrength, neuralPlasticity]);

  useEffect(() => {
    const canvas = signalCanvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const drawSignals = () => {
      ctx.fillStyle = 'rgba(0, 0, 0, 0.1)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      signals.slice(-50).forEach((signal, index) => {
        const x = (index / 50) * canvas.width;
        const y = canvas.height / 2 + Math.sin(signal.timestamp / 100) * signal.amplitude;
        
        ctx.beginPath();
        ctx.arc(x, y, 2, 0, Math.PI * 2);
        ctx.fillStyle = `hsl(${280 + signal.frequency / 10}, 70%, 50%)`;
        ctx.fill();
      });
    };

    const interval = setInterval(drawSignals, 100);
    return () => clearInterval(interval);
  }, [signals]);

  useEffect(() => {
    const canvas = networkCanvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const drawNetworkVisualization = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      networks.forEach((network, networkIndex) => {
        const x = (networkIndex + 1) * (canvas.width / (networks.length + 1));
        const baseY = canvas.height / 2;
        
        // Draw layers
        network.neurons.forEach((neuronCount, layerIndex) => {
          const layerX = x - 50 + layerIndex * 20;
          
          for (let i = 0; i < Math.min(neuronCount / 10, 5); i++) {
            const neuronY = baseY - 30 + (i * 15);
            
            ctx.beginPath();
            ctx.arc(layerX, neuronY, 3, 0, Math.PI * 2);
            ctx.fillStyle = network.status === 'active' ? '#10b981' : 
                            network.status === 'training' ? '#f59e0b' : '#6b7280';
            ctx.fill();
          }
        });
      });
    };

    drawNetworkVisualization();
    const animationId = requestAnimationFrame(drawNetworkVisualization);

    return () => cancelAnimationFrame(animationId);
  }, [networks]);

  const trainNetwork = useCallback((networkId: string) => {
    setNetworks(prev => prev.map(network => 
      network.id === networkId ? { ...network, status: 'training' } : network
    ));

    setTimeout(() => {
      setNetworks(prev => prev.map(network => 
        network.id === networkId ? { ...network, status: 'active', accuracy: Math.min(0.99, network.accuracy + 0.02) } : network
      ));
    }, 5000);
  }, []);

  const generateThought = useCallback(() => {
    const categories: ThoughtPattern['category'][] = ['logic', 'creative', 'emotional', 'analytical'];
    const patterns = [
      'Optimized quantum algorithm discovered',
      'Novel neural architecture proposed',
      'Creative solution synthesis complete',
      'Logical paradox resolved',
      'Emotional intelligence enhanced',
      'Analytical model updated',
    ];

    const newThought: ThoughtPattern = {
      id: Date.now().toString(),
      pattern: patterns[Math.floor(Math.random() * patterns.length)],
      confidence: Math.random() * 0.3 + 0.7,
      category: categories[Math.floor(Math.random() * categories.length)],
      timestamp: new Date().toISOString(),
    };

    setThoughts(prev => [newThought, ...prev.slice(0, 9)]);
  }, []);

  return (
    <div className="space-y-6">
      {/* Neural Interface Status */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-gradient-to-br from-green-900/50 to-emerald-900/50 p-6 rounded-2xl border border-green-500/30 backdrop-blur-lg"
      >
        <h3 className="text-2xl font-bold text-white mb-4 flex items-center">
          <Brain className="w-8 h-8 mr-3 text-green-400" />
          Neural Interface Status
        </h3>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="bg-black/30 p-4 rounded-lg">
            <div className="text-sm text-gray-400 mb-1">Brain Activity</div>
            <div className="text-2xl font-bold text-green-400">{(brainActivity * 100).toFixed(1)}%</div>
            <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
              <div className="bg-green-400 h-2 rounded-full transition-all duration-500" style={{ width: `${brainActivity * 100}%` }} />
            </div>
          </div>
          <div className="bg-black/30 p-4 rounded-lg">
            <div className="text-sm text-gray-400 mb-1">Synaptic Strength</div>
            <div className="text-2xl font-bold text-emerald-400">{(synapticStrength * 100).toFixed(1)}%</div>
            <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
              <div className="bg-emerald-400 h-2 rounded-full transition-all duration-500" style={{ width: `${synapticStrength * 100}%` }} />
            </div>
          </div>
          <div className="bg-black/30 p-4 rounded-lg">
            <div className="text-sm text-gray-400 mb-1">Neural Plasticity</div>
            <div className="text-2xl font-bold text-teal-400">{(neuralPlasticity * 100).toFixed(1)}%</div>
            <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
              <div className="bg-teal-400 h-2 rounded-full transition-all duration-500" style={{ width: `${neuralPlasticity * 100}%` }} />
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
            <span className="text-white">{isConnected ? 'Neural Interface Connected' : 'Neural Interface Disconnected'}</span>
          </div>
          <motion.button
            onClick={() => setIsConnected(!isConnected)}
            className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            {isConnected ? 'Disconnect' : 'Connect'}
          </motion.button>
        </div>
      </motion.div>

      {/* Brain Activity Visualization */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="bg-gradient-to-br from-purple-900/50 to-pink-900/50 p-6 rounded-2xl border border-purple-500/30 backdrop-blur-lg"
      >
        <h3 className="text-xl font-bold text-white mb-4 flex items-center">
          <Eye className="w-6 h-6 mr-2 text-purple-400" />
          Brain Activity Monitor
        </h3>
        <canvas
          ref={canvasRef}
          width={600}
          height={300}
          className="w-full bg-black/50 rounded-lg"
        />
      </motion.div>

      {/* Neural Networks */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="bg-gradient-to-br from-blue-900/50 to-indigo-900/50 p-6 rounded-2xl border border-blue-500/30 backdrop-blur-lg"
      >
        <h3 className="text-xl font-bold text-white mb-4 flex items-center">
          <Network className="w-6 h-6 mr-2 text-blue-400" />
          Neural Networks
        </h3>
        
        <div className="mb-4">
          <canvas
            ref={networkCanvasRef}
            width={600}
            height={200}
            className="w-full bg-black/50 rounded-lg"
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {networks.map((network) => (
            <div key={network.id} className="bg-black/30 p-4 rounded-lg">
              <div className="flex justify-between items-start mb-2">
                <div>
                  <h4 className="text-white font-semibold">{network.name}</h4>
                  <p className="text-gray-400 text-sm capitalize">{network.type}</p>
                </div>
                <span className={`px-2 py-1 rounded text-xs ${
                  network.status === 'active' ? 'bg-green-600' :
                  network.status === 'training' ? 'bg-yellow-600' :
                  network.status === 'error' ? 'bg-red-600' : 'bg-gray-600'
                }`}>
                  {network.status}
                </span>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Accuracy</span>
                  <span className="text-white">{(network.accuracy * 100).toFixed(1)}%</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Layers</span>
                  <span className="text-white">{network.layers}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Connections</span>
                  <span className="text-white">{network.connections.toLocaleString()}</span>
                </div>
              </div>
              <motion.button
                onClick={() => trainNetwork(network.id)}
                disabled={network.status === 'training'}
                className="mt-3 w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white px-3 py-2 rounded text-sm"
                whileHover={{ scale: network.status === 'training' ? 1 : 1.02 }}
                whileTap={{ scale: network.status === 'training' ? 1 : 0.98 }}
              >
                {network.status === 'training' ? 'Training...' : 'Train Network'}
              </motion.button>
            </div>
          ))}
        </div>
      </motion.div>

      {/* Neural Signals */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="bg-gradient-to-br from-cyan-900/50 to-teal-900/50 p-6 rounded-2xl border border-cyan-500/30 backdrop-blur-lg"
      >
        <h3 className="text-xl font-bold text-white mb-4 flex items-center">
          <Activity className="w-6 h-6 mr-2 text-cyan-400" />
          Neural Signals
        </h3>
        <canvas
          ref={signalCanvasRef}
          width={600}
          height={200}
          className="w-full bg-black/50 rounded-lg"
        />
      </motion.div>

      {/* Thought Patterns */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="bg-gradient-to-br from-orange-900/50 to-red-900/50 p-6 rounded-2xl border border-orange-500/30 backdrop-blur-lg"
      >
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-xl font-bold text-white flex items-center">
            <Sparkles className="w-6 h-6 mr-2 text-orange-400" />
            Thought Patterns
          </h3>
          <motion.button
            onClick={generateThought}
            className="bg-orange-600 hover:bg-orange-700 text-white px-4 py-2 rounded-lg"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            Generate Thought
          </motion.button>
        </div>

        <div className="space-y-3">
          <AnimatePresence>
            {thoughts.map((thought) => (
              <motion.div
                key={thought.id}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                className="bg-black/30 p-4 rounded-lg"
              >
                <div className="flex justify-between items-start mb-2">
                  <h4 className="text-white font-medium">{thought.pattern}</h4>
                  <span className={`px-2 py-1 rounded text-xs ${
                    thought.category === 'logic' ? 'bg-blue-600' :
                    thought.category === 'creative' ? 'bg-purple-600' :
                    thought.category === 'emotional' ? 'bg-pink-600' : 'bg-green-600'
                  }`}>
                    {thought.category}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-gray-400 text-sm">Confidence: {(thought.confidence * 100).toFixed(1)}%</span>
                  <span className="text-gray-500 text-xs">{new Date(thought.timestamp).toLocaleTimeString()}</span>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
}
