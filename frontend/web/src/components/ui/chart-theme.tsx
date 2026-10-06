'use client';

import { cn } from '@/lib/utils';

/**
 * Chart theming.
 *
 * Recharts ships its own defaults (grey gridlines, `#1f2937` tooltip) which
 * look foreign against this app's surfaces. These tokens are derived from the
 * holographic palette already defined in `globals.css`, so charts adopt the
 * theme automatically and follow dark/light or future palette changes without
 * touching chart call sites.
 *
 * Colours are read from CSS custom properties at call time rather than being
 * duplicated here as literals, keeping one source of truth.
 */

export const CHART_COLORS = {
  cyan: 'hsl(190 100% 50%)',
  teal: 'hsl(174 100% 45%)',
  violet: 'hsl(258 90% 66%)',
  amber: 'hsl(38 92% 50%)',
  emerald: 'hsl(142 71% 45%)',
  rose: 'hsl(350 89% 60%)',
  blue: 'hsl(199 89% 48%)',
} as const;

/** Categorical sequence, ordered so adjacent series stay distinguishable. */
export const CHART_SERIES = [
  CHART_COLORS.cyan,
  CHART_COLORS.teal,
  CHART_COLORS.violet,
  CHART_COLORS.amber,
  CHART_COLORS.blue,
  CHART_COLORS.rose,
] as const;

export const CHART_GRID = 'rgba(255, 255, 255, 0.06)';
export const CHART_AXIS = 'rgba(179, 229, 252, 0.45)';
export const CHART_CURSOR = 'rgba(0, 212, 255, 0.08)';

/** Shared props for a recessive, unobtrusive axis. */
export const AXIS_PROPS = {
  stroke: CHART_AXIS,
  tick: { fill: CHART_AXIS, fontSize: 10 },
  tickLine: false,
  axisLine: false,
} as const;

/** Shared props for a subtle grid. */
export const GRID_PROPS = {
  stroke: CHART_GRID,
  strokeDasharray: '3 3',
  vertical: false,
} as const;

/**
 * Pick a categorical colour by index, wrapping around the palette.
 */
export function seriesColor(index: number): string {
  return CHART_SERIES[index % CHART_SERIES.length];
}

interface ChartFrameProps {
  title?: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}

/**
 * Consistent chart chrome: title, optional description, right-aligned action
 * slot, and a fixed height so charts do not jump as data arrives.
 */
export function ChartFrame({
  title,
  description,
  action,
  className,
  children,
}: ChartFrameProps) {
  return (
    <figure
      className={cn(
        'rounded-xl border border-white/[0.07] bg-white/[0.02] p-3 backdrop-blur-sm',
        className
      )}
    >
      {(title || action) && (
        <div className="mb-2 flex items-start justify-between gap-2">
          <div className="min-w-0">
            {title && (
              <figcaption className="truncate text-[11px] font-medium uppercase tracking-widest text-foreground/70">
                {title}
              </figcaption>
            )}
            {description && (
              <p className="mt-0.5 truncate text-[10.5px] text-muted-foreground/50">
                {description}
              </p>
            )}
          </div>
          {action}
        </div>
      )}
      {children}
    </figure>
  );
}

interface TooltipCardProps {
  active?: boolean;
  label?: React.ReactNode;
  payload?: Array<{ name?: string; value?: number | string; color?: string }>;
  valueFormatter?: (value: number, name: string) => string;
}

/**
 * Tooltip body styled to match the app surfaces. Kept local so the tooltip has
 * the same glass treatment as every other floating element.
 */
export function TooltipCard({ active, label, payload, valueFormatter }: TooltipCardProps) {
  if (!active || !payload?.length) return null;

  return (
    <div className="rounded-lg border border-white/10 bg-black/85 px-2.5 py-1.5 text-[11px] shadow-[0_0_24px_rgba(0,0,0,0.6)] backdrop-blur-sm">
      {label !== undefined && label !== null && (
        <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground/60">
          {label}
        </div>
      )}
      <div className="space-y-0.5">
        {payload.map((entry, index) => {
          const numeric = typeof entry.value === 'number' ? entry.value : Number(entry.value);
          const display =
            valueFormatter && Number.isFinite(numeric)
              ? valueFormatter(numeric, entry.name ?? '')
              : String(entry.value);
          return (
            <div key={index} className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ background: entry.color }}
              />
              <span className="text-muted-foreground/70">{entry.name}</span>
              <span className="ml-auto font-mono tabular-nums text-foreground/90">
                {display}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}