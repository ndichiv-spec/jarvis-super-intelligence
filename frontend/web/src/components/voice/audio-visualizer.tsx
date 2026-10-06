'use client';

import { useEffect, useRef } from 'react';

import { cn } from '@/lib/utils';

/**
 * Audio-reactive visualizers.
 *
 * Voice was previously text-only: `isSpeaking` / `isListening` booleans with no
 * representation of the actual signal. A user cannot tell whether the assistant
 * heard them, is mid-sentence, or stalled on a long synthesis.
 *
 * These components render the waveform on a 2D canvas rather than with DOM
 * elements, for two reasons. Per-bar DOM nodes force layout on every animation
 * frame, and at 60fps with 48 bars that is enough to drop frames on the main
 * thread -- which is exactly where audio processing and chat rendering live.
 * Canvas keeps the cost to a single paint.
 *
 * All drawing is driven by a normalised amplitude value (0..1) passed in by the
 * caller, so the components work with any source: a live `AnalyserNode`, a
 * socket-reported level, or a synthetic idle animation when no mic is attached.
 */

export type VisualizerVariant = 'bars' | 'wave' | 'radial' | 'grid';

export interface AudioVisualizerProps {
  /** Current amplitude, 0..1. Values above 1 are clamped. */
  level?: number;
  /** Draw an idle animation when level is 0 and `animateIdle` is set. */
  animateIdle?: boolean;
  variant?: VisualizerVariant;
  width?: number;
  height?: number;
  /** Bar count for the `bars` and `grid` variants. */
  barCount?: number;
  /** Hue in degrees; defaults to the holographic cyan. */
  hue?: number;
  className?: string;
  /** Accessible description. The canvas is decorative otherwise. */
  label?: string;
}

/** Smooth a raw level toward its target so the bars do not strobe. */
function ease(current: number, target: number, smoothing: number): number {
  return current + (target - current) * smoothing;
}

export function AudioVisualizer({
  level = 0,
  animateIdle = true,
  variant = 'bars',
  width = 240,
  height = 48,
  barCount = 40,
  hue = 190,
  className,
  label = 'Audio activity',
}: AudioVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const levelRef = useRef(level);
  const smoothedRef = useRef(0);
  const phaseRef = useRef(0);
  const rafRef = useRef<number | null>(null);

  // Keep the latest level reachable from the animation loop without restarting
  // it, which would drop the smoothed state on every parent re-render.
  useEffect(() => {
    levelRef.current = level;
  }, [level]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Match the backing store to the device pixel ratio so the canvas is not
    // upscaled and blurred on HiDPI displays.
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.scale(dpr, dpr);

    const reducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

    let disposed = false;

    const render = (now: number) => {
      if (disposed) return;

      // Advance the idle phase from the frame timestamp rather than a separate
      // timer, so the animation stays coherent at any frame rate and needs no
      // extra interval.
      phaseRef.current = now / 1000;

      const target = Math.max(0, Math.min(1, levelRef.current));
      // A small idle floor keeps the display alive when nobody is speaking,
      // which reads as "connected" rather than "broken".
      const effective = animateIdle ? Math.max(target, idleFloor(phaseRef.current, target)) : target;

      smoothedRef.current = reducedMotion
        ? effective
        : ease(smoothedRef.current, effective, 0.18);

      const amplitude = smoothedRef.current;

      ctx.clearRect(0, 0, width, height);

      switch (variant) {
        case 'bars':
          drawBars(ctx, amplitude, width, height, barCount, hue, now);
          break;
        case 'wave':
          drawWave(ctx, amplitude, width, height, hue, phaseRef.current);
          break;
        case 'radial':
          drawRadial(ctx, amplitude, width, height, barCount, hue, phaseRef.current);
          break;
        case 'grid':
          drawGrid(ctx, amplitude, width, height, barCount, hue, now);
          break;
      }

      rafRef.current = requestAnimationFrame(render);
    };

    rafRef.current = requestAnimationFrame(render);

    return () => {
      disposed = true;
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [variant, width, height, barCount, hue, animateIdle]);

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      role="img"
      aria-label={label}
      className={cn('block', className)}
      style={{ width, height }}
    />
  );
}

/**
 * A low synthetic amplitude for the idle state, so the visualizer pulses gently
 * rather than sitting flat. Scales down as real audio comes in so it never
 * competes with actual speech.
 */
function idleFloor(phase: number, activeLevel: number): number {
  const pulse = (Math.sin(phase * 1.6) + 1) / 2;
  return pulse * 0.12 * (1 - activeLevel);
}

function hueColor(hue: number, saturation: number, lightness: number, alpha = 1): string {
  return `hsla(${hue}, ${saturation}%, ${lightness}%, ${alpha})`;
}

function drawBars(
  ctx: CanvasRenderingContext2D,
  amplitude: number,
  width: number,
  height: number,
  barCount: number,
  hue: number,
  now: number
) {
  const gap = 2;
  const barWidth = Math.max(1, (width - gap * (barCount - 1)) / barCount);
  const mid = height / 2;

  for (let i = 0; i < barCount; i += 1) {
    // Symmetric envelope: quiet at the edges, strongest in the centre.
    const position = i / (barCount - 1);
    const envelope = Math.sin(position * Math.PI) ** 0.6;
    // Per-bar phase offset produces a travelling ripple instead of a uniform
    // pulse, which reads as more responsive to the signal.
    const jitter = 0.55 + 0.45 * Math.sin(i * 1.7 + now / 90);
    const magnitude = amplitude * envelope * jitter;

    const barHeight = Math.max(2, magnitude * height * 0.92);
    const x = i * (barWidth + gap);
    const y = mid - barHeight / 2;

    const gradient = ctx.createLinearGradient(0, y, 0, y + barHeight);
    gradient.addColorStop(0, hueColor(hue, 100, 65, 0.95));
    gradient.addColorStop(0.5, hueColor(hue + 12, 100, 55, 0.85));
    gradient.addColorStop(1, hueColor(hue + 20, 90, 45, 0.55));

    ctx.fillStyle = gradient;
    roundRect(ctx, x, y, barWidth, barHeight, Math.min(barWidth / 2, 2));
    ctx.fill();
  }
}

function drawWave(
  ctx: CanvasRenderingContext2D,
  amplitude: number,
  width: number,
  height: number,
  hue: number,
  phase: number
) {
  const mid = height / 2;
  const segments = Math.max(32, Math.floor(width / 4));

  for (let layer = 0; layer < 2; layer += 1) {
    const opacity = layer === 0 ? 0.9 : 0.35;
    const spread = layer === 0 ? 1 : 0.55;
    const offset = layer * 2.1;

    ctx.beginPath();
    for (let i = 0; i <= segments; i += 1) {
      const position = i / segments;
      const x = position * width;
      // Two summed sines give a shape that stays smooth at low amplitude but
      // still ripples visibly, without the noise a random walk would add.
      const y =
        mid +
        Math.sin(position * Math.PI * 4 + phase * 2.2 + offset) * amplitude * (height * 0.4) * spread +
        Math.sin(position * Math.PI * 9 - phase * 3.1) * amplitude * (height * 0.12) * spread;

      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }

    ctx.strokeStyle = hueColor(hue, 100, 60, opacity);
    ctx.lineWidth = layer === 0 ? 1.75 : 1;
    ctx.shadowColor = hueColor(hue, 100, 60, 0.8);
    ctx.shadowBlur = layer === 0 ? 8 : 0;
    ctx.stroke();
    ctx.shadowBlur = 0;
  }
}

function drawRadial(
  ctx: CanvasRenderingContext2D,
  amplitude: number,
  width: number,
  height: number,
  barCount: number,
  hue: number,
  phase: number
) {
  const cx = width / 2;
  const cy = height / 2;
  const baseRadius = Math.min(cx, cy) * 0.42;

  ctx.translate(cx, cy);

  for (let i = 0; i < barCount; i += 1) {
    const angle = (i / barCount) * Math.PI * 2 - Math.PI / 2;
    const ripple = 0.6 + 0.4 * Math.sin(angle * 3 + phase * 2.4);
    const magnitude = amplitude * ripple;
    const length = baseRadius * (0.35 + magnitude * 0.9);

    const inner = baseRadius * 0.55;
    const x1 = Math.cos(angle) * inner;
    const y1 = Math.sin(angle) * inner;
    const x2 = Math.cos(angle) * (inner + length);
    const y2 = Math.sin(angle) * (inner + length);

    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.strokeStyle = hueColor(hue + i * 1.5, 100, 60, 0.35 + magnitude * 0.6);
    ctx.lineWidth = Math.max(1.5, (Math.PI * 2 * baseRadius) / barCount / 2.2);
    ctx.lineCap = 'round';
    ctx.stroke();
  }

  // Inner disc, so the radial form has a solid core to glow from.
  const glow = ctx.createRadialGradient(0, 0, 0, 0, 0, baseRadius * 0.6);
  glow.addColorStop(0, hueColor(hue, 100, 65, 0.35 + amplitude * 0.4));
  glow.addColorStop(1, hueColor(hue, 100, 50, 0));
  ctx.beginPath();
  ctx.arc(0, 0, baseRadius * 0.6, 0, Math.PI * 2);
  ctx.fillStyle = glow;
  ctx.fill();

  ctx.setTransform(1, 0, 0, 1, 0, 0);
}

function drawGrid(
  ctx: CanvasRenderingContext2D,
  amplitude: number,
  width: number,
  height: number,
  barCount: number,
  hue: number,
  now: number
) {
  const rows = 5;
  const cols = barCount;
  const cellWidth = width / cols;
  const cellHeight = height / rows;

  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      // Brightest along the vertical centre line.
      const centreBias = 1 - Math.abs(row - (rows - 1) / 2) / ((rows - 1) / 2);
      const ripple = 0.5 + 0.5 * Math.sin(col * 0.9 + now / 130);
      const magnitude = amplitude * centreBias * ripple;

      const size = Math.max(1.5, magnitude * Math.min(cellWidth, cellHeight) * 1.5);
      const x = col * cellWidth + (cellWidth - size) / 2;
      const y = row * cellHeight + (cellHeight - size) / 2;

      ctx.fillStyle = hueColor(hue, 100, 60, 0.2 + magnitude * 0.8);
      ctx.beginPath();
      ctx.arc(x + size / 2, y + size / 2, size / 2, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number
) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + width, y, x + width, y + height, r);
  ctx.arcTo(x + width, y + height, x, y + height, r);
  ctx.arcTo(x, y + height, x, y, r);
  ctx.arcTo(x, y, x + width, y, r);
  ctx.closePath();
}