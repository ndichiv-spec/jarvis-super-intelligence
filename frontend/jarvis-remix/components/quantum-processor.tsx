import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  motion,
  AnimatePresence,
  Zap,
  Radio,
  BrainCircuit,
  Atom,
} from 'lucide-react';

interface QuantumState {
  entanglement: number;
  superposition: number;
  coherence: number;
  qubits: number;
  operations_per_second: number;
  error_rate: number;
  temperature: number;
  magnetic_field: number;
}

interface QuantumGate {
  id: string;
  name: string;
  type: 'hadamard' | 'cnot' | 'pauli-x' | 'pauli-y' | 'pauli-z' | 'phase' | 'measurement';
  matrix: number[][];
  probability: number;
  active: boolean;
}

export function QuantumProcessor() {
  const [quantumState, setQuantumState] = useState<QuantumState>({
    entanglement: 0.87,
    superposition: 0.92,
    coherence: 0.95,
    qubits: 1024,
    operations_per_second: 1000000,
    error_rate: 0.001,
    temperature: 0.015,
    magnetic_field: 8.5,
  });

  const [gates, setGates] = useState<QuantumGate[]>([
    { id: '1', name: 'Hadamard', type: 'hadamard', matrix: [[0.707, 0.707], [0.707, -0.707]], probability: 0.95, active: true },
    { id: '2', name: 'CNOT', type: 'cnot', matrix: [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], probability: 0.98, active: true },
    { id: '3', name: 'Pauli-X', type: 'pauli-x', matrix: [[0, 1], [1, 0]], probability: 0.99, active: false },
    { id: '4', name: 'Phase', type: 'phase', matrix: [[1, 0], [0, 1]], probability: 0.97, active: true },
  ]);

  const [algorithm, setAlgorithm] = useState('grover');
  const [isProcessing, setIsProcessing] = useState(false);
  const [results, setResults] = useState<any[]>([]);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particleCanvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const interval = setInterval(() => {
      setQuantumState(prev => ({
        ...prev,
        entanglement: Math.max(0.5, Math.min(1, prev.entanglement + (Math.random() - 0.5) * 0.05)),
        superposition: Math.max(0.5, Math.min(1, prev.superposition + (Math.random() - 0.5) * 0.03)),
        coherence: Math.max(0.8, Math.min(1, prev.coherence + (Math.random() - 0.5) * 0.02)),
        operations_per_second: Math.floor(Math.random() * 200000) + 900000,
        error_rate: Math.max(0.0001, Math.min(0.01, prev.error_rate + (Math.random() - 0.5) * 0.0005)),
        temperature: Math.max(0.01, Math.min(0.02, prev.temperature + (Math.random() - 0.5) * 0.001)),
      }));
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const drawQuantumCircuit = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      // Draw quantum circuit lines
      for (let i = 0; i < 4; i++) {
        ctx.beginPath();
        ctx.moveTo(20, 50 + i * 40);
        ctx.lineTo(canvas.width - 20, 50 + i * 40);
        ctx.strokeStyle = '#60a5fa';
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      // Draw active gates
      gates.filter(g => g.active).forEach((gate, index) => {
        const x = 100 + index * 80;
        const y = 50;
        
        ctx.fillStyle = '#8b5cf6';
        ctx.fillRect(x - 20, y - 20, 40, 160);
        
        ctx.fillStyle = '#ffffff';
        ctx.font = '12px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(gate.name, x, y + 70);
      });
    };

    drawQuantumCircuit();
    const animationId = requestAnimationFrame(drawQuantumCircuit);

    return () => cancelAnimationFrame(animationId);
  }, [gates]);

  useEffect(() => {
    const canvas = particleCanvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const particles: Array<{x: number, y: number, vx: number, vy: number, phase: number, amplitude: number}> = [];
    
    for (let i = 0; i < 50; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 2,
        vy: (Math.random() - 0.5) * 2,
        phase: Math.random() * Math.PI * 2,
        amplitude: Math.random() * 20 + 10,
      });
    }

    const animate = () => {
      ctx.fillStyle = 'rgba(0, 0, 0, 0.1)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      particles.forEach(particle => {
        particle.x += particle.vx;
        particle.y += particle.vy;
        particle.phase += 0.05;

        if (particle.x < 0 || particle.x > canvas.width) particle.vx *= -1;
        if (particle.y < 0 || particle.y > canvas.height) particle.vy *= -1;

        const waveY = particle.y + Math.sin(particle.phase) * particle.amplitude;
        
        ctx.beginPath();
        ctx.arc(particle.x, waveY, 3, 0, Math.PI * 2);
        ctx.fillStyle = `hsl(${280 + Math.sin(particle.phase) * 60}, 70%, 50%)`;
        ctx.fill();
      });

      requestAnimationFrame(animate);
    };

    animate();
  }, []);

  const runQuantumAlgorithm = useCallback(async () => {
    setIsProcessing(true);
    
    // Simulate quantum computation
    await new Promise(resolve => setTimeout(resolve, 3000));
    
    const simulatedResults = [
      { state: '|000⟩', probability: 0.25 },
      { state: '|001⟩', probability: 0.15 },
      { state: '|010⟩', probability: 0.30 },
      { state: '|011⟩', probability: 0.10 },
      { state: '|100⟩', probability: 0.12 },
      { state: '|101⟩', probability: 0.05 },
      { state: '|110⟩', probability: 0.02 },
      { state: '|111⟩', probability: 0.01 },
    ];
    
    setResults(simulatedResults);
    setIsProcessing(false);
  }, [algorithm]);

  const toggleGate = (gateId: string) => {
    setGates(prev => prev.map(gate => 
      gate.id === gateId ? { ...gate, active: !gate.active } : gate
    ));
  };

  return (
    <div className="space-y-6">
      {/* Quantum State Visualization */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-gradient-to-br from-purple-900/50 to-blue-900/50 p-6 rounded-2xl border border-purple-500/30 backdrop-blur-lg"
      >
        <h3 className="text-2xl font-bold text-white mb-4 flex items-center">
          <Atom className="w-8 h-8 mr-3 text-purple-400" />
          Quantum State Monitor
        </h3>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="bg-black/30 p-4 rounded-lg">
            <div className="text-sm text-gray-400 mb-1">Entanglement</div>
            <div className="text-2xl font-bold text-purple-400">{(quantumState.entanglement * 100).toFixed(1)}%</div>
            <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
              <div className="bg-purple-400 h-2 rounded-full transition-all duration-500" style={{ width: `${quantumState.entanglement * 100}%` }} />
            </div>
          </div>
          <div className="bg-black/30 p-4 rounded-lg">
            <div className="text-sm text-gray-400 mb-1">Superposition</div>
            <div className="text-2xl font-bold text-blue-400">{(quantumState.superposition * 100).toFixed(1)}%</div>
            <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
              <div className="bg-blue-400 h-2 rounded-full transition-all duration-500" style={{ width: `${quantumState.superposition * 100}%` }} />
            </div>
          </div>
          <div className="bg-black/30 p-4 rounded-lg">
            <div className="text-sm text-gray-400 mb-1">Coherence</div>
            <div className="text-2xl font-bold text-green-400">{(quantumState.coherence * 100).toFixed(1)}%</div>
            <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
              <div className="bg-green-400 h-2 rounded-full transition-all duration-500" style={{ width: `${quantumState.coherence * 100}%` }} />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-black/30 p-4 rounded-lg">
            <div className="text-sm text-gray-400 mb-1">Error Rate</div>
            <div className="text-xl font-bold text-red-400">{(quantumState.error_rate * 100).toFixed(3)}%</div>
          </div>
          <div className="bg-black/30 p-4 rounded-lg">
            <div className="text-sm text-gray-400 mb-1">Temperature</div>
            <div className="text-xl font-bold text-cyan-400">{quantumState.temperature.toFixed(3)}K</div>
          </div>
        </div>
      </motion.div>

      {/* Quantum BrainCircuit */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="bg-gradient-to-br from-cyan-900/50 to-teal-900/50 p-6 rounded-2xl border border-cyan-500/30 backdrop-blur-lg"
      >
        <h3 className="text-xl font-bold text-white mb-4 flex items-center">
          <BrainCircuit className="w-6 h-6 mr-2 text-cyan-400" />
          Quantum BrainCircuit
        </h3>
        <canvas
          ref={canvasRef}
          width={600}
          height={200}
          className="w-full bg-black/50 rounded-lg"
        />
        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-2">
          {gates.map((gate) => (
            <button
              key={gate.id}
              onClick={() => toggleGate(gate.id)}
              className={`p-2 rounded-lg transition-all ${
                gate.active 
                  ? 'bg-purple-600 text-white' 
                  : 'bg-gray-700 text-gray-400'
              }`}
            >
              {gate.name}
            </button>
          ))}
        </div>
      </motion.div>

      {/* Quantum Algorithm Runner */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="bg-gradient-to-br from-green-900/50 to-emerald-900/50 p-6 rounded-2xl border border-green-500/30 backdrop-blur-lg"
      >
        <h3 className="text-xl font-bold text-white mb-4 flex items-center">
          <Zap className="w-6 h-6 mr-2 text-green-400" />
          Quantum Algorithm Runner
        </h3>
        
        <div className="mb-4">
          <select
            value={algorithm}
            onChange={(e) => setAlgorithm(e.target.value)}
            className="w-full bg-black/50 text-white p-3 rounded-lg border border-green-500/30"
          >
            <option value="grover">Grover's Search Algorithm</option>
            <option value="shor">Shor's Factoring Algorithm</option>
            <option value="qft">Quantum Fourier Transform</option>
            <option value="vqe">Variational Quantum Eigensolver</option>
          </select>
        </div>

        <motion.button
          onClick={runQuantumAlgorithm}
          disabled={isProcessing}
          className="w-full bg-gradient-to-r from-green-600 to-emerald-600 text-white p-4 rounded-lg font-semibold disabled:opacity-50"
          whileHover={{ scale: isProcessing ? 1 : 1.02 }}
          whileTap={{ scale: isProcessing ? 1 : 0.98 }}
        >
          {isProcessing ? (
            <span className="flex items-center justify-center">
              <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
              Processing Quantum Algorithm...
            </span>
          ) : (
            'Run Quantum Algorithm'
          )}
        </motion.button>

        <AnimatePresence>
          {results.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="mt-6"
            >
              <h4 className="text-lg font-semibold text-white mb-3">Measurement Results</h4>
              <div className="space-y-2">
                {results.map((result, index) => (
                  <div key={index} className="flex justify-between items-center bg-black/30 p-3 rounded-lg">
                    <span className="text-gray-300">{result.state}</span>
                    <div className="flex items-center space-x-2">
                      <div className="w-32 bg-gray-700 rounded-full h-2">
                        <div 
                          className="bg-green-400 h-2 rounded-full" 
                          style={{ width: `${result.probability * 100}%` }} 
                        />
                      </div>
                      <span className="text-green-400 text-sm w-12 text-right">
                        {(result.probability * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      {/* Quantum Particle Visualization */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="bg-gradient-to-br from-indigo-900/50 to-purple-900/50 p-6 rounded-2xl border border-indigo-500/30 backdrop-blur-lg"
      >
        <h3 className="text-xl font-bold text-white mb-4 flex items-center">
          <Radio className="w-6 h-6 mr-2 text-indigo-400" />
          Quantum Particle Field
        </h3>
        <canvas
          ref={particleCanvasRef}
          width={600}
          height={300}
          className="w-full bg-black/50 rounded-lg"
        />
      </motion.div>
    </div>
  );
}
