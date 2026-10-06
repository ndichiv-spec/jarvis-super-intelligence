'use client';

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { cn } from '@/lib/utils';
import {
  AXIS_PROPS,
  ChartFrame,
  CHART_CURSOR,
  GRID_PROPS,
  TooltipCard,
  seriesColor,
} from '@/components/ui/chart-theme';

/**
 * Chart primitives.
 *
 * `recharts` was already a declared dependency but had no call sites, so the
 * dashboards were rendering raw numbers with no visual trend. These wrappers
 * exist so each chart type is configured once -- recessive axes, subtle grid,
 * glass tooltip, consistent gutters -- and individual pages only supply data.
 *
 * All of them are responsive and SSR-safe: `ResponsiveContainer` needs a
 * bounded parent, so every chart carries a default height.
 */

// ---------------------------------------------------------------------------
// Time series
// ---------------------------------------------------------------------------

export interface SeriesConfig {
  /** Data key on each datum. */
  key: string;
  label: string;
  /** Overrides the categorical palette. */
  color?: string;
  /** Render as a filled area (only honoured when there is one series). */
  area?: boolean;
  /** Draw with dashes. */
  dashed?: boolean;
}

interface TimeSeriesChartProps {
  data: Array<Record<string, unknown>>;
  series: SeriesConfig[];
  title?: string;
  description?: string;
  /** Data key used for the x axis. */
  xKey: string;
  height?: number;
  className?: string;
  /** Draw a dashed line at this y value, e.g. a threshold. */
  threshold?: { value: number; label?: string };
  formatValue?: (value: number, name: string) => string;
  action?: React.ReactNode;
  emptyMessage?: string;
}

export function TimeSeriesChart({
  data,
  series,
  title,
  description,
  xKey,
  height = 200,
  className,
  threshold,
  formatValue,
  action,
  emptyMessage = 'No data yet',
}: TimeSeriesChartProps) {
  if (!data.length || !series.length) {
    return (
      <ChartFrame title={title} description={description} className={className} action={action}>
        <div
          className="flex items-center justify-center text-[11px] text-muted-foreground/40"
          style={{ height }}
        >
          {emptyMessage}
        </div>
      </ChartFrame>
    );
  }

  // A single filled series reads better as an area; multiple series stay lines
  // so overlapping fills do not muddy the plot.
  const asArea = series.length === 1 && series[0].area !== false;

  return (
    <ChartFrame title={title} description={description} className={className} action={action}>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          {asArea ? (
            <AreaChart data={data} margin={{ top: 4, right: 6, bottom: 0, left: -18 }}>
              <defs>
                <linearGradient id="jarvisAreaFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={series[0].color ?? seriesColor(0)} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={series[0].color ?? seriesColor(0)} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid {...GRID_PROPS} />
              <XAxis dataKey={xKey} {...AXIS_PROPS} minTickGap={24} />
              <YAxis {...AXIS_PROPS} width={46} />
              <Tooltip
                content={<TooltipCard valueFormatter={formatValue} />}
                cursor={{ stroke: CHART_CURSOR, strokeWidth: 8 }}
              />
              {threshold && (
                <ReferenceLine
                  y={threshold.value}
                  stroke="rgba(245, 158, 11, 0.5)"
                  strokeDasharray="4 4"
                  label={{
                    value: threshold.label,
                    fill: 'rgba(245, 158, 11, 0.8)',
                    fontSize: 9,
                    position: 'insideTopRight',
                  }}
                />
              )}
              {series.map((s, i) => (
                <Area
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.label}
                  stroke={s.color ?? seriesColor(i)}
                  strokeWidth={1.75}
                  fill="url(#jarvisAreaFill)"
                  isAnimationActive={false}
                  dot={false}
                  activeDot={{ r: 3 }}
                />
              ))}
            </AreaChart>
          ) : (
            <LineChart data={data} margin={{ top: 4, right: 6, bottom: 0, left: -18 }}>
              <CartesianGrid {...GRID_PROPS} />
              <XAxis dataKey={xKey} {...AXIS_PROPS} minTickGap={24} />
              <YAxis {...AXIS_PROPS} width={46} />
              <Tooltip
                content={<TooltipCard valueFormatter={formatValue} />}
                cursor={{ stroke: CHART_CURSOR, strokeWidth: 8 }}
              />
              {threshold && (
                <ReferenceLine
                  y={threshold.value}
                  stroke="rgba(245, 158, 11, 0.5)"
                  strokeDasharray="4 4"
                  label={{
                    value: threshold.label,
                    fill: 'rgba(245, 158, 11, 0.8)',
                    fontSize: 9,
                    position: 'insideTopRight',
                  }}
                />
              )}
              {series.map((s, i) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.label}
                  stroke={s.color ?? seriesColor(i)}
                  strokeWidth={1.75}
                  strokeDasharray={s.dashed ? '4 3' : undefined}
                  isAnimationActive={false}
                  dot={false}
                  activeDot={{ r: 3 }}
                />
              ))}
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

// ---------------------------------------------------------------------------
// Bar
// ---------------------------------------------------------------------------

interface BarChartProps {
  data: Array<Record<string, unknown>>;
  series: SeriesConfig[];
  xKey: string;
  title?: string;
  description?: string;
  height?: number;
  className?: string;
  /** Stack series instead of grouping them. */
  stacked?: boolean;
  formatValue?: (value: number, name: string) => string;
  action?: React.ReactNode;
  emptyMessage?: string;
}

export function MetricBarChart({
  data,
  series,
  xKey,
  title,
  description,
  height = 200,
  className,
  stacked = false,
  formatValue,
  action,
  emptyMessage = 'No data yet',
}: BarChartProps) {
  if (!data.length || !series.length) {
    return (
      <ChartFrame title={title} description={description} className={className} action={action}>
        <div
          className="flex items-center justify-center text-[11px] text-muted-foreground/40"
          style={{ height }}
        >
          {emptyMessage}
        </div>
      </ChartFrame>
    );
  }

  return (
    <ChartFrame title={title} description={description} className={className} action={action}>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            margin={{ top: 4, right: 6, bottom: 0, left: -18 }}
            barCategoryGap={stacked ? '25%' : '18%'}
          >
            <CartesianGrid {...GRID_PROPS} />
            <XAxis dataKey={xKey} {...AXIS_PROPS} interval={0} />
            <YAxis {...AXIS_PROPS} width={46} />
            <Tooltip
              content={<TooltipCard valueFormatter={formatValue} />}
              cursor={{ fill: CHART_CURSOR }}
            />
            {series.map((s, i) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                name={s.label}
                stackId={stacked ? 'stack' : undefined}
                fill={s.color ?? seriesColor(i)}
                radius={stacked ? 0 : [3, 3, 0, 0]}
                isAnimationActive={false}
                maxBarSize={stacked ? 28 : 18}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

// ---------------------------------------------------------------------------
// Radial gauge
// ---------------------------------------------------------------------------

interface RadialGaugeProps {
  value: number;
  max?: number;
  label?: string;
  unit?: string;
  size?: number;
  /** Draw the track in a warning tone, e.g. near a capacity ceiling. */
  alert?: boolean;
  className?: string;
}

export function RadialGauge({
  value,
  max = 100,
  label,
  unit = '%',
  size = 120,
  alert = false,
  className,
}: RadialGaugeProps) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  const circumference = 2 * Math.PI * 44;
  const dash = (pct / 100) * circumference;

  return (
    <div
      className={cn('flex flex-col items-center gap-1', className)}
      role="meter"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label ?? 'Utilization'}
    >
      <div className="relative" style={{ width: size, height: size }}>
        <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
          <circle
            cx="50"
            cy="50"
            r="44"
            fill="none"
            stroke="rgba(255,255,255,0.06)"
            strokeWidth="7"
          />
          <circle
            cx="50"
            cy="50"
            r="44"
            fill="none"
            stroke={alert ? 'hsl(38 92% 50%)' : 'hsl(190 100% 50%)'}
            strokeWidth="7"
            strokeLinecap="round"
            strokeDasharray={`${dash} ${circumference - dash}`}
            style={{
              filter: alert
                ? 'drop-shadow(0 0 6px rgba(245,158,11,0.5))'
                : 'drop-shadow(0 0 6px rgba(0,212,255,0.5))',
              transition: 'stroke-dasharray 400ms ease-out',
            }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono text-lg font-semibold tabular-nums text-foreground/90">
            {Math.round(pct)}
            <span className="text-[11px] text-muted-foreground/60">{unit}</span>
          </span>
          {label && (
            <span className="max-w-[80%] truncate text-[9.5px] uppercase tracking-widest text-muted-foreground/50">
              {label}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sparkline
// ---------------------------------------------------------------------------

interface SparklineProps {
  /** Most recent value last. */
  values: number[];
  width?: number;
  height?: number;
  color?: string;
  /** Fill the area under the line. */
  fill?: boolean;
  className?: string;
  label?: string;
}

/**
 * Inline trend line for stat tiles. Deliberately axis-free and chrome-free:
 * it conveys direction, not values.
 */
export function Sparkline({
  values,
  width = 100,
  height = 28,
  color = 'hsl(190 100% 50%)',
  fill = true,
  className,
  label,
}: SparklineProps) {
  if (values.length < 2) {
    return <div className={cn('opacity-30', className)} style={{ width, height }} aria-hidden="true" />;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = width / (values.length - 1);

  const points = values.map((v, i) => {
    const x = i * step;
    const y = height - ((v - min) / range) * (height - 2) - 1;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });

  const line = `M${points.join(' L')}`;
  const areaPath = `${line} L${width},${height} L0,${height} Z`;
  const gradientId = `spark-${Math.abs(hashString(line))}`;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={cn('overflow-visible', className)}
      role="img"
      aria-label={label ?? 'Trend'}
      preserveAspectRatio="none"
    >
      {fill && (
        <>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <path d={areaPath} fill={`url(#${gradientId})`} />
        </>
      )}
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth={1.25}
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ filter: `drop-shadow(0 0 3px ${color}66)` }}
      />
    </svg>
  );
}

function hashString(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return hash;
}