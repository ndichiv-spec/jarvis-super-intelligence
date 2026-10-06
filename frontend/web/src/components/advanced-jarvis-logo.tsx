'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';

interface AdvancedJarvisLogoProps {
  variant?: 'default' | 'quantum' | 'neural' | 'cyberpunk' | 'minimal' | 'holographic';
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  animated?: boolean;
  className?: string;
}

const AdvancedJarvisLogo: React.FC<AdvancedJarvisLogoProps> = ({
  variant = 'default',
  size = 'md',
  animated = true,
  className
}) => {
  const [isHovered, setIsHovered] = useState(false);
  const [glitchIntensity, setGlitchIntensity] = useState(0);

  const sizeClasses = {
    sm: 'w-12 h-12',
    md: 'w-16 h-16',
    lg: 'w-24 h-24',
    xl: 'w-32 h-32',
    '2xl': 'w-48 h-48'
  };

  const renderLogo = () => {
    switch (variant) {
      case 'quantum':
        return <QuantumLogo size={size} animated={animated} />;
      case 'neural':
        return <NeuralLogo size={size} animated={animated} />;
      case 'cyberpunk':
        return <CyberpunkLogo size={size} animated={animated} />;
      case 'minimal':
        return <MinimalLogo size={size} />;
      case 'holographic':
        return <HolographicLogo size={size} animated={animated} />;
      default:
        return <DefaultLogo size={size} animated={animated} />;
    }
  };

  return (
    <motion.div
      className={cn(
        'relative inline-flex items-center justify-center',
        sizeClasses[size],
        className
      )}
      onHoverStart={() => setIsHovered(true)}
      onHoverEnd={() => setIsHovered(false)}
      whileHover={{ scale: 1.05 }}
      transition={{ type: 'spring', stiffness: 400, damping: 17 }}
    >
      <AnimatePresence mode="wait">
        {renderLogo()}
      </AnimatePresence>
      
      {/* Glow effect */}
      {animated && (
        <motion.div
          className="absolute inset-0 rounded-full"
          style={{
            background: `radial-gradient(circle, rgba(59, 130, 246, ${isHovered ? 0.3 : 0.1}) 0%, transparent 70%)`,
            filter: 'blur(20px)'
          }}
          animate={{
            opacity: isHovered ? 1 : 0.5,
            scale: isHovered ? 1.2 : 1
          }}
          transition={{ duration: 0.3 }}
        />
      )}
    </motion.div>
  );
};

// Default Logo with advanced gradients
const DefaultLogo: React.FC<{ size: string; animated: boolean }> = ({ size, animated }) => (
  <motion.svg
    viewBox="0 0 200 200"
    className="w-full h-full"
    initial={animated ? { rotate: 0 } : {}}
    animate={animated ? { rotate: 360 } : {}}
    transition={animated ? { duration: 20, repeat: Infinity, ease: 'linear' } : {}}
  >
    <defs>
      <linearGradient id="jarvisGradient" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="#3B82F6" />
        <stop offset="50%" stopColor="#8B5CF6" />
        <stop offset="100%" stopColor="#EC4899" />
      </linearGradient>
      <filter id="glow">
        <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
        <feMerge>
          <feMergeNode in="coloredBlur"/>
          <feMergeNode in="SourceGraphic"/>
        </feMerge>
      </filter>
    </defs>
    
    {/* Outer ring */}
    <circle
      cx="100"
      cy="100"
      r="90"
      fill="none"
      stroke="url(#jarvisGradient)"
      strokeWidth="2"
      opacity="0.8"
    />
    
    {/* Inner hexagon */}
    <path
      d="M100 30 L150 60 L150 120 L100 150 L50 120 L50 60 Z"
      fill="none"
      stroke="url(#jarvisGradient)"
      strokeWidth="3"
      filter="url(#glow)"
    />
    
    {/* J letter */}
    <text
      x="100"
      y="110"
      fontSize="60"
      fontWeight="bold"
      fill="url(#jarvisGradient)"
      textAnchor="middle"
      filter="url(#glow)"
    >
      J
    </text>
    
    {/* Neural connections */}
    {animated && (
      <g opacity="0.6">
        <circle cx="70" cy="70" r="2" fill="#3B82F6">
          <animate attributeName="opacity" values="0;1;0" dur="2s" repeatCount="indefinite" />
        </circle>
        <circle cx="130" cy="70" r="2" fill="#8B5CF6">
          <animate attributeName="opacity" values="0;1;0" dur="2s" begin="0.5s" repeatCount="indefinite" />
        </circle>
        <circle cx="130" cy="130" r="2" fill="#EC4899">
          <animate attributeName="opacity" values="0;1;0" dur="2s" begin="1s" repeatCount="indefinite" />
        </circle>
        <circle cx="70" cy="130" r="2" fill="#3B82F6">
          <animate attributeName="opacity" values="0;1;0" dur="2s" begin="1.5s" repeatCount="indefinite" />
        </circle>
      </g>
    )}
  </motion.svg>
);

// Quantum Logo with particle effects
const QuantumLogo: React.FC<{ size: string; animated: boolean }> = ({ size, animated }) => (
  <motion.svg
    viewBox="0 0 200 200"
    className="w-full h-full"
    initial={animated ? { scale: 0 } : {}}
    animate={animated ? { scale: 1 } : {}}
    transition={animated ? { type: 'spring', stiffness: 200, damping: 15 } : {}}
  >
    <defs>
      <radialGradient id="quantumCore">
        <stop offset="0%" stopColor="#00FFFF" />
        <stop offset="50%" stopColor="#FF00FF" />
        <stop offset="100%" stopColor="#FFFF00" />
      </radialGradient>
    </defs>
    
    {/* Quantum core */}
    <circle cx="100" cy="100" r="40" fill="url(#quantumCore)" opacity="0.9" />
    
    {/* Orbiting particles */}
    {animated && [0, 60, 120, 180, 240, 300].map((angle, i) => (
      <motion.circle
        key={i}
        cx="100"
        cy="40"
        r="3"
        fill="#00FFFF"
        animate={animated ? {
          rotate: [angle, angle + 360],
          transition: { duration: 3 + i * 0.5, repeat: Infinity, ease: 'linear' }
        } : {}}
        style={{ transformOrigin: '100px 100px' }}
      />
    ))}
    
    {/* Quantum field lines */}
    <path
      d="M100 20 Q180 100 100 180 Q20 100 100 20"
      fill="none"
      stroke="url(#quantumCore)"
      strokeWidth="1"
      opacity="0.5"
    />
  </motion.svg>
);

// Neural Logo with brain-like patterns
const NeuralLogo: React.FC<{ size: string; animated: boolean }> = ({ size, animated }) => (
  <motion.svg
    viewBox="0 0 200 200"
    className="w-full h-full"
  >
    <defs>
      <linearGradient id="neuralGradient" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="#00FF88" />
        <stop offset="100%" stopColor="#0088FF" />
      </linearGradient>
    </defs>
    
    {/* Neural network nodes */}
    {[
      { x: 100, y: 50, size: 8 },
      { x: 70, y: 80, size: 6 },
      { x: 130, y: 80, size: 6 },
      { x: 60, y: 120, size: 5 },
      { x: 100, y: 100, size: 10 },
      { x: 140, y: 120, size: 5 },
      { x: 80, y: 150, size: 6 },
      { x: 120, y: 150, size: 6 },
      { x: 100, y: 170, size: 8 }
    ].map((node, i) => (
      <motion.circle
        key={i}
        cx={node.x}
        cy={node.y}
        r={node.size}
        fill="url(#neuralGradient)"
        animate={animated ? {
          r: [node.size, node.size + 2, node.size],
          opacity: [0.7, 1, 0.7]
        } : {}}
        transition={animated ? {
          duration: 2 + i * 0.2,
          repeat: Infinity,
          ease: 'easeInOut'
        } : {}}
      />
    ))}
    
    {/* Neural connections */}
    <g stroke="url(#neuralGradient)" strokeWidth="1" fill="none" opacity="0.3">
      <line x1="100" y1="50" x2="70" y2="80" />
      <line x1="100" y1="50" x2="130" y2="80" />
      <line x1="70" y1="80" x2="100" y2="100" />
      <line x1="130" y1="80" x2="100" y2="100" />
      <line x1="100" y1="100" x2="60" y2="120" />
      <line x1="100" y1="100" x2="140" y2="120" />
      <line x1="60" y1="120" x2="80" y2="150" />
      <line x1="140" y1="120" x2="120" y2="150" />
      <line x1="80" y1="150" x2="100" y2="170" />
      <line x1="120" y1="150" x2="100" y2="170" />
    </g>
  </motion.svg>
);

// Cyberpunk Logo with neon effects
const CyberpunkLogo: React.FC<{ size: string; animated: boolean }> = ({ size, animated }) => (
  <motion.svg
    viewBox="0 0 200 200"
    className="w-full h-full"
  >
    <defs>
      <linearGradient id="cyberpunkGradient" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="#FF0080" />
        <stop offset="50%" stopColor="#00FFFF" />
        <stop offset="100%" stopColor="#FFFF00" />
      </linearGradient>
      <filter id="neonGlow">
        <feGaussianBlur stdDeviation="4" result="coloredBlur"/>
        <feMerge>
          <feMergeNode in="coloredBlur"/>
          <feMergeNode in="SourceGraphic"/>
        </feMerge>
      </filter>
    </defs>
    
    {/* Cyberpunk hexagon */}
    <motion.path
      d="M100 20 L160 55 L160 125 L100 160 L40 125 L40 55 Z"
      fill="none"
      stroke="url(#cyberpunkGradient)"
      strokeWidth="3"
      filter="url(#neonGlow)"
      animate={animated ? {
        strokeDasharray: [0, 400],
        strokeDashoffset: [400, 0]
      } : {}}
      transition={animated ? { duration: 2, repeat: Infinity, ease: 'linear' } : {}}
    />
    
    {/* Circuit patterns */}
    <g stroke="#00FFFF" strokeWidth="1" fill="none" opacity="0.6">
      <rect x="70" y="70" width="60" height="60" />
      <line x1="70" y1="85" x2="130" y2="85" />
      <line x1="70" y1="100" x2="130" y2="100" />
      <line x1="70" y1="115" x2="130" y2="115" />
    </g>
    
    {/* JARVIS text */}
    <text
      x="100"
      y="105"
      fontSize="20"
      fontWeight="bold"
      fill="url(#cyberpunkGradient)"
      textAnchor="middle"
      filter="url(#neonGlow)"
    >
      J
    </text>
  </motion.svg>
);

// Minimal Logo
const MinimalLogo: React.FC<{ size: string }> = ({ size }) => (
  <svg viewBox="0 0 200 200" className="w-full h-full">
    <circle
      cx="100"
      cy="100"
      r="80"
      fill="none"
      stroke="#3B82F6"
      strokeWidth="2"
    />
    <text
      x="100"
      y="115"
      fontSize="48"
      fontWeight="300"
      fill="#3B82F6"
      textAnchor="middle"
    >
      J
    </text>
  </svg>
);

// Holographic Logo with rainbow effects
const HolographicLogo: React.FC<{ size: string; animated: boolean }> = ({ size, animated }) => (
  <motion.svg
    viewBox="0 0 200 200"
    className="w-full h-full"
    style={{
      filter: animated ? 'hue-rotate(0deg)' : 'none',
      animation: animated ? 'hueRotate 3s linear infinite' : 'none'
    }}
  >
    <defs>
      <linearGradient id="holographicGradient" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="#FF0000" />
        <stop offset="16.66%" stopColor="#FF8800" />
        <stop offset="33.33%" stopColor="#FFFF00" />
        <stop offset="50%" stopColor="#00FF00" />
        <stop offset="66.66%" stopColor="#0088FF" />
        <stop offset="83.33%" stopColor="#8800FF" />
        <stop offset="100%" stopColor="#FF0088" />
      </linearGradient>
    </defs>
    
    {/* Holographic layers */}
    {[1, 2, 3].map((layer) => (
      <motion.circle
        key={layer}
        cx="100"
        cy="100"
        r={90 - layer * 10}
        fill="none"
        stroke="url(#holographicGradient)"
        strokeWidth="2"
        opacity={0.3 + layer * 0.2}
        animate={animated ? {
          scale: [1, 1.1, 1],
          opacity: [0.3 + layer * 0.2, 0.8, 0.3 + layer * 0.2]
        } : {}}
        transition={animated ? {
          duration: 2 + layer * 0.5,
          repeat: Infinity,
          ease: 'easeInOut'
        } : {}}
      />
    ))}
    
    {/* Central J */}
    <text
      x="100"
      y="110"
      fontSize="48"
      fontWeight="bold"
      fill="url(#holographicGradient)"
      textAnchor="middle"
    >
      J
    </text>
  </motion.svg>
);

export default AdvancedJarvisLogo;
