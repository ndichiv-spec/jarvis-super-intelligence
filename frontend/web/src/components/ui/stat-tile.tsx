'use client';

import type { ReactNode } from 'react';
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';

import { cn } from '@/lib/utils';
import { Sparkline } from '@/components/ui/charts';

/**
 * Stat tile.
 *
 * The dashboard's most repeated element: one number, its trend, and a sparkline.
 * Every metric readout in the app should use this rather than hand-rolling a
 * `<div>` with a big font, so the four states (up / down / flat / unknown) stay
 * visually consistent.
 */

export type StatTone = 'default' | 'success' | 'warning' | 'danger' | 'info';

const TONE_ACCENT: Record<StatTone, string> = {
  default: 'text-foreground',
  success: 'text-emerald-400',
  warning: 'text-amber-400',
  danger: 'text-red-400',
  info: 'text-cyan-400',
};

const TONE_GLOW: Record<StatTone, string> = {
  default: 'rgba(0,212,255,0.15)',
  success: 'rgba(34,197,94,0.15)',
  warning: 'rgba(245,158,11,0.15)',
  danger: 'rgba(239,68,68,0.15)',
  info: 'rgba(0,212,255,0.15)',
};

const SPARK_COLOR: Record<StatTone, string> = {
  default: 'hsl(190 100% 50%)',
  success: 'hsl(142 71% 45%)',
  warning: 'hsl(38 92% 50%)',
  danger: 'hsl(0 84% 60%)',
  info: 'hsl(190 100% 50%)',
};

interface StatTileProps {
  label: string;
  value: ReactNode;
  /** Unit suffix rendered smaller, e.g. `ms`, `%`, `MB`. */
  unit?: string;
  /** Percentage change against the previous window. */
  delta?: number;
  /** Invert delta colouring when a decrease is good (latency, error rate). */
  invertDelta?: boolean;
  /** Recent values, oldest first, for the inline trend line. */
  trend?: number[];
  icon?: ReactNode;
  tone?: StatTone;
  /** Called on click; omitted renders a non-interactive tile. */
  onClick?: () => void;
  className?: string;
  title?: string;
}

export function StatTile({
  label,
  value,
  unit,
  delta,
  invertDelta = false,
  trend,
  icon,
  tone = 'default',
  onClick,
  className,
  title,
}: StatTileProps) {
  const hasDelta = typeof delta === 'number' && Number.isFinite(delta);
  const isFlat = hasDelta && Math.abs(delta as number) < 0.05;
  const isUp = hasDelta && (delta as number) > 0;

  const DeltaIcon = isFlat ? Minus : isUp ? ArrowUpRight : ArrowDownRight;
  const good = isFlat ? null : invertDelta ? !isUp : isUp;

  const deltaTone = good === null
    ? 'text-muted-foreground/50'
    : good
      ? 'text-emerald-400/90'
      : 'text-red-400/90';

  const Component = onClick ? 'button' : 'div';

  return (
    <Component
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      title={title}
      className={cn(
        'group relative flex w-full flex-col gap-1 overflow-hidden rounded-xl border border-white/[0.07] bg-white/[0.02] p-3 text-left',
        'transition-colors',
        onClick && 'hover:border-white/15 hover:bg-white/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        className
      )}
    >
      {/* Top edge glow in the tile's tone */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-px"
        style={{ background: `linear-gradient(90deg, transparent, ${TONE_GLOW[tone]}, transparent)` }}
      />

      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-[10px] font-medium uppercase tracking-widest text-muted-foreground/60">
          {label}
        </span>
        {icon && <span className="shrink-0 opacity-50 transition-opacity group-hover:opacity-80">{icon}</span>}
      </div>

      <div className="flex items-baseline gap-1">
        <span className={cn('font-mono text-xl font-semibold tabular-nums leading-none', TONE_ACCENT[tone])}>
          {value}
        </span>
        {unit && <span className="text-[11px] text-muted-foreground/60">{unit}</span>}
      </div>

      {(hasDelta || trend?.length) && (
        <div className="flex items-end justify-between gap-2">
          {hasDelta ? (
            <span className={cn('flex items-center gap-0.5 font-mono text-[11px] tabular-nums', deltaTone)}>
              <DeltaIcon className="h-3 w-3" />
              {Math.abs(delta as number).toFixed(1)}%
            </span>
          ) : (
            <span />
          )}

          {trend && trend.length > 1 && (
            <Sparkline
              values={trend}
              color={SPARK_COLOR[tone]}
              width={72}
              height={20}
              label={`${label} trend`}
              className="shrink-0 opacity-80"
            />
          )}
        </div>
      )}
    </Component>
  );
}

interface StatGridProps {
  children: ReactNode;
  /** Minimum tile width; the grid reflows from there. */
  minTileWidth?: number;
  className?: string;
}

/** Responsive grid for {@link StatTile}s. */
export function StatGrid({ children, minTileWidth = 160, className }: StatGridProps) {
  return (
    <div
      className={cn('grid gap-3', className)}
      style={{ gridTemplateColumns: `repeat(auto-fit, minmax(${minTileWidth}px, 1fr))` }}
    >
      {children}
    </div>
  );
}