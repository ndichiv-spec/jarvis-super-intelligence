"use client";

import React, { useEffect, useRef, useCallback } from 'react';
import { useNeuralTheme } from '@/lib/neural-theme-engine';

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  opacity: number;
  life: number;
  maxLife: number;
  type: 'circle' | 'line' | 'glow';
}

interface NeuralBackgroundProps {
  intensity?: 'low' | 'medium' | 'high' | 'adaptive';
  interactive?: boolean;
  className?: string;
}

export function NeuralBackground({
  intensity = 'adaptive',
  interactive = true,
  className = '',
}: NeuralBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const mouseRef = useRef({ x: 0, y: 0, active: false });
  const animationRef = useRef<number>(0);
  const { activeTheme } = useNeuralTheme();

  const getParticleCount = useCallback(() => {
    switch (intensity) {
      case 'low': return 30;
      case 'medium': return 60;
      case 'high': return 100;
      case 'adaptive': return Math.min(80, Math.max(40, window.innerWidth / 20));
      default: return 60;
    }
  }, [intensity]);

  const createParticle = useCallback((width: number, height: number): Particle => {
    const types: Particle['type'][] = ['circle', 'line', 'glow'];
    return {
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.5,
      vy: (Math.random() - 0.5) * 0.5,
      size: Math.random() * 2 + 0.5,
      opacity: Math.random() * 0.5 + 0.2,
      life: 0,
      maxLife: Math.random() * 200 + 100,
      type: types[Math.floor(Math.random() * types.length)],
    };
  }, []);

  const drawParticle = useCallback((ctx: CanvasRenderingContext2D, particle: Particle, color: string) => {
    const lifeRatio = particle.life / particle.maxLife;
    const alpha = particle.opacity * (1 - lifeRatio);

    ctx.save();
    ctx.globalAlpha = alpha;

    switch (particle.type) {
      case 'circle':
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        break;

      case 'line':
        ctx.beginPath();
        ctx.moveTo(particle.x, particle.y);
        ctx.lineTo(particle.x - particle.vx * 10, particle.y - particle.vy * 10);
        ctx.strokeStyle = color;
        ctx.lineWidth = particle.size * 0.5;
        ctx.stroke();
        break;

      case 'glow':
        const gradient = ctx.createRadialGradient(
          particle.x, particle.y, 0,
          particle.x, particle.y, particle.size * 4
        );
        gradient.addColorStop(0, color);
        gradient.addColorStop(1, 'transparent');
        ctx.fillStyle = gradient;
        ctx.fillRect(
          particle.x - particle.size * 4,
          particle.y - particle.size * 4,
          particle.size * 8,
          particle.size * 8
        );
        break;
    }

    ctx.restore();
  }, []);

  const drawConnections = useCallback((ctx: CanvasRenderingContext2D, particles: Particle[], color: string) => {
    const maxDistance = 120;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 0.5;

    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance < maxDistance) {
          const opacity = (1 - distance / maxDistance) * 0.15;
          ctx.globalAlpha = opacity;
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.stroke();
        }
      }
    }

    ctx.restore();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };

    resize();
    window.addEventListener('resize', resize);

    // Initialize particles
    particlesRef.current = Array.from(
      { length: getParticleCount() },
      () => createParticle(canvas.width, canvas.height)
    );

    const handleMouseMove = (e: MouseEvent) => {
      if (interactive) {
        mouseRef.current.x = e.clientX;
        mouseRef.current.y = e.clientY;
        mouseRef.current.active = true;
      }
    };

    const handleMouseLeave = () => {
      mouseRef.current.active = false;
    };

    if (interactive) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseleave', handleMouseLeave);
    }

    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const color = activeTheme.effects.particleColor;

      // Update and draw particles
      particlesRef.current = particlesRef.current.filter((particle) => {
        particle.life++;
        particle.x += particle.vx;
        particle.y += particle.vy;

        // Mouse interaction
        if (mouseRef.current.active) {
          const dx = particle.x - mouseRef.current.x;
          const dy = particle.y - mouseRef.current.y;
          const distance = Math.sqrt(dx * dx + dy * dy);
          const force = Math.max(0, (200 - distance) / 200);

          if (distance < 200) {
            particle.vx += (dx / distance) * force * 0.02;
            particle.vy += (dy / distance) * force * 0.02;
          }
        }

        // Damping
        particle.vx *= 0.99;
        particle.vy *= 0.99;

        // Wrap around edges
        if (particle.x < 0) particle.x = canvas.width;
        if (particle.x > canvas.width) particle.x = 0;
        if (particle.y < 0) particle.y = canvas.height;
        if (particle.y > canvas.height) particle.y = 0;

        // Draw
        drawParticle(ctx, particle, color);

        return particle.life < particle.maxLife;
      });

      // Draw connections
      drawConnections(ctx, particlesRef.current, color);

      // Spawn new particles
      while (particlesRef.current.length < getParticleCount()) {
        particlesRef.current.push(createParticle(canvas.width, canvas.height));
      }

      animationRef.current = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener('resize', resize);
      if (interactive) {
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseleave', handleMouseLeave);
      }
      cancelAnimationFrame(animationRef.current);
    };
  }, [activeTheme, getParticleCount, createParticle, drawParticle, drawConnections, interactive]);

  return (
    <canvas
      ref={canvasRef}
      className={`fixed inset-0 pointer-events-none z-0 ${className}`}
      style={{ opacity: activeTheme.effects.glowIntensity * 0.3 }}
    />
  );
}

// Neural Grid Background Component
export function NeuralGrid() {
  const { activeTheme } = useNeuralTheme();

  return (
    <div
      className="fixed inset-0 pointer-events-none z-0"
      style={{
        backgroundImage: `
          linear-gradient(rgba(6, 182, 212, ${activeTheme.effects.gridOpacity * 0.5}) 1px, transparent 1px),
          linear-gradient(90deg, rgba(6, 182, 212, ${activeTheme.effects.gridOpacity * 0.5}) 1px, transparent 1px)
        `,
        backgroundSize: '50px 50px',
        opacity: activeTheme.effects.gridOpacity,
      }}
    />
  );
}

// Ambient Glow Effect
export function AmbientGlow() {
  const { activeTheme } = useNeuralTheme();

  return (
    <div className="fixed inset-0 pointer-events-none z-0">
      <div
        className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[500px] rounded-full blur-3xl"
        style={{
          background: `radial-gradient(ellipse, ${activeTheme.colors.primaryGlow}, transparent 70%)`,
          opacity: activeTheme.effects.glowIntensity * 0.4,
        }}
      />
      <div
        className="absolute bottom-0 right-0 w-[600px] h-[400px] rounded-full blur-3xl"
        style={{
          background: `radial-gradient(ellipse, ${activeTheme.colors.primaryGlow}, transparent 70%)`,
          opacity: activeTheme.effects.glowIntensity * 0.2,
        }}
      />
    </div>
  );
}

// Combined Neural Background Wrapper
export function NeuralBackgroundWrapper({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`relative ${className}`}>
      <NeuralBackground intensity="adaptive" interactive={true} />
      <NeuralGrid />
      <AmbientGlow />
      <div className="relative z-10">
        {children}
      </div>
    </div>
  );
}
