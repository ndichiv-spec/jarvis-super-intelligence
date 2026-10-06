import React, { useEffect, useRef, useCallback } from 'react';

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  opacity: number;
  pulseSpeed: number;
  pulsePhase: number;
}

interface MousePosition {
  x: number;
  y: number;
  active: boolean;
}

const PARTICLE_COUNT = 180;
const CONNECTION_DISTANCE = 150;
const MOUSE_RADIUS = 200;
const MOUSE_FORCE = 0.02;
const PARTICLE_MIN_SIZE = 1.5;
const PARTICLE_MAX_SIZE = 3.5;
const BASE_SPEED = 0.3;
const BACKGROUND_COLOR = '#0a0d12';
const PARTICLE_COLOR_BASE = { r: 0, g: 180, b: 255 };
const CONNECTION_COLOR = 'rgba(0, 180, 255,';

const ParticleSystem: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const mouseRef = useRef<MousePosition>({ x: 0, y: 0, active: false });
  const animationFrameRef = useRef<number>(0);

  const createParticle = useCallback((width: number, height: number): Particle => {
    const pulsePhase = Math.random() * Math.PI * 2;
    return {
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * BASE_SPEED * 2,
      vy: (Math.random() - 0.5) * BASE_SPEED * 2,
      size: PARTICLE_MIN_SIZE + Math.random() * (PARTICLE_MAX_SIZE - PARTICLE_MIN_SIZE),
      opacity: 0.3 + Math.random() * 0.7,
      pulseSpeed: 0.02 + Math.random() * 0.03,
      pulsePhase,
    };
  }, []);

  const initParticles = useCallback(
    (width: number, height: number) => {
      const particles: Particle[] = [];
      for (let i = 0; i < PARTICLE_COUNT; i++) {
        particles.push(createParticle(width, height));
      }
      particlesRef.current = particles;
    },
    [createParticle]
  );

  const updateParticle = useCallback(
    (particle: Particle, width: number, height: number, mouse: MousePosition) => {
      // Mouse interaction - gravity well effect
      if (mouse.active) {
        const dx = particle.x - mouse.x;
        const dy = particle.y - mouse.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance < MOUSE_RADIUS) {
          const force = (1 - distance / MOUSE_RADIUS) * MOUSE_FORCE;
          particle.vx += (dx / distance) * force;
          particle.vy += (dy / distance) * force;
        }
      }

      // Apply velocity
      particle.x += particle.vx;
      particle.y += particle.vy;

      // Damping to prevent runaway velocities
      particle.vx *= 0.99;
      particle.vy *= 0.99;

      // Ensure minimum movement
      const speed = Math.sqrt(particle.vx * particle.vx + particle.vy * particle.vy);
      if (speed < BASE_SPEED * 0.5) {
        particle.vx += (Math.random() - 0.5) * 0.05;
        particle.vy += (Math.random() - 0.5) * 0.05;
      }

      // Boundary wrapping with padding
      const padding = 50;
      if (particle.x < -padding) particle.x = width + padding;
      if (particle.x > width + padding) particle.x = -padding;
      if (particle.y < -padding) particle.y = height + padding;
      if (particle.y > height + padding) particle.y = -padding;

      // Pulse animation
      particle.pulsePhase += particle.pulseSpeed;
    },
    []
  );

  const drawParticle = useCallback(
    (ctx: CanvasRenderingContext2D, particle: Particle, time: number) => {
      const pulse = Math.sin(particle.pulsePhase + time * 0.001) * 0.3 + 0.7;
      const currentOpacity = particle.opacity * pulse;
      const currentSize = particle.size * (0.8 + pulse * 0.2);

      // Glow effect
      const gradient = ctx.createRadialGradient(
        particle.x,
        particle.y,
        0,
        particle.x,
        particle.y,
        currentSize * 3
      );

      const { r, g, b } = PARTICLE_COLOR_BASE;
      gradient.addColorStop(
        0,
        `rgba(${r}, ${g}, ${b}, ${currentOpacity})`
      );
      gradient.addColorStop(
        0.4,
        `rgba(${r}, ${g}, ${b}, ${currentOpacity * 0.4})`
      );
      gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`);

      ctx.beginPath();
      ctx.arc(particle.x, particle.y, currentSize * 3, 0, Math.PI * 2);
      ctx.fillStyle = gradient;
      ctx.fill();

      // Core particle
      ctx.beginPath();
      ctx.arc(particle.x, particle.y, currentSize, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${currentOpacity})`;
      ctx.fill();
    },
    []
  );

  const drawConnections = useCallback(
    (ctx: CanvasRenderingContext2D, particles: Particle[]) => {
      const length = particles.length;

      for (let i = 0; i < length; i++) {
        for (let j = i + 1; j < length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const distance = Math.sqrt(dx * dx + dy * dy);

          if (distance < CONNECTION_DISTANCE) {
            const opacity = (1 - distance / CONNECTION_DISTANCE) * 0.4;

            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);

            const gradient = ctx.createLinearGradient(
              particles[i].x,
              particles[i].y,
              particles[j].x,
              particles[j].y
            );

            const { r, g, b } = PARTICLE_COLOR_BASE;
            gradient.addColorStop(0, `${CONNECTION_COLOR}${opacity * 0.5})`);
            gradient.addColorStop(0.5, `${CONNECTION_COLOR}${opacity})`);
            gradient.addColorStop(1, `${CONNECTION_COLOR}${opacity * 0.5})`);

            ctx.strokeStyle = gradient;
            ctx.lineWidth = 0.8;
            ctx.stroke();
          }
        }
      }
    },
    []
  );

  const animate = useCallback(
    (ctx: CanvasRenderingContext2D, width: number, height: number) => {
      const time = performance.now();

      // Clear canvas
      ctx.fillStyle = BACKGROUND_COLOR;
      ctx.fillRect(0, 0, width, height);

      // Update particles
      const particles = particlesRef.current;
      const mouse = mouseRef.current;

      for (const particle of particles) {
        updateParticle(particle, width, height, mouse);
      }

      // Draw connections first (behind particles)
      drawConnections(ctx, particles);

      // Draw particles
      for (const particle of particles) {
        drawParticle(ctx, particle, time);
      }

      animationFrameRef.current = requestAnimationFrame(() =>
        animate(ctx, width, height)
      );
    },
    [updateParticle, drawConnections, drawParticle]
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const handleResize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      initParticles(canvas.width, canvas.height);
    };

    const handleMouseMove = (e: MouseEvent) => {
      mouseRef.current = {
        x: e.clientX,
        y: e.clientY,
        active: true,
      };
    };

    const handleMouseLeave = () => {
      mouseRef.current.active = false;
    };

    // Initialize
    handleResize();

    // Start animation
    animationFrameRef.current = requestAnimationFrame(() =>
      animate(ctx, canvas.width, canvas.height)
    );

    // Event listeners
    window.addEventListener('resize', handleResize);
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseleave', handleMouseLeave);

    // Cleanup
    return () => {
      cancelAnimationFrame(animationFrameRef.current);
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseleave', handleMouseLeave);
    };
  }, [animate, initParticles]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 0,
      }}
    />
  );
};

export default ParticleSystem;
