'use client';

import { useEffect, useRef, useState } from 'react';
import { Activity, Cpu, HardDrive, MemoryStick, Network } from 'lucide-react';

import { cn } from '@/lib/utils';
import { StatGrid, StatTile, type StatTone } from '@/components/ui/stat-tile';
import { MetricBarChart, RadialGauge, TimeSeriesChart } from '@/components/ui/charts';
import { useSystemUsage } from '@/stores/platform-store';

/**
 * Live system telemetry.
 *
 * The dashboard previously rendered four fixed numbers ("Uptime 100%",
 * "Processes 209") that never changed, because there was no chart primitive in
 * the app to plot the `monitoring_update` events the backend was already
 * publishing over the WebSocket.
 *
 * This panel consumes that stream. A rolling buffer keeps the last
 * {@link HISTORY_LENGTH} samples so charts have a time axis, and the tiles
 * derive their delta from that buffer rather than a separate statistics call.
 */

/** Samples retained per series. ~5 minutes at a 1s cadence. */
const HISTORY_LENGTH = 60;

interface Sample {
  t: number;
  cpu: number;
  memory: number;
  disk: number;
  processes: number;
}

interface SystemTelemetryProps {
  className?: string;
  /** Show the CPU/memory/disk gauges row. */
  showGauges?: boolean;
  /** Show the rolling time-series chart. */
  showChart?: boolean;
}

/** Utilisation tone thresholds, shared by tiles and gauges. */
function toneForPercent(percent: number): StatTone {
  if (percent >= 90) return 'danger';
  if (percent >= 75) return 'warning';
  return 'info';
}

/**
 * Change between the oldest and newest sample of a series, as a percentage.
 * Returns undefined when there is not enough history to be meaningful.
 */
function deltaOverWindow(values: number[]): number | undefined {
  if (values.length < 2) return undefined;
  const previous = values[0];
  const current = values[values.length - 1];
  // A zero baseline makes a percentage change undefined rather than infinite.
  if (previous === 0) return undefined;
  return ((current - previous) / previous) * 100;
}

export function SystemTelemetry({
  className,
  showGauges = true,
  showChart = true,
}: SystemTelemetryProps) {
  const usage = useSystemUsage();
  const [history, setHistory] = useState<Sample[]>([]);

  // Only append when a genuinely new sample arrives. Depending on the timestamp
  // field means a re-render with an unchanged snapshot does not grow the buffer.
  const lastSeen = useRef<number>(0);

  useEffect(() => {
    if (!usage) return;
    const timestamp = usage.timestamp ?? Date.now();
    if (timestamp <= lastSeen.current) return;
    lastSeen.current = timestamp;

    const sample: Sample = {
      t: timestamp,
      cpu: usage.cpu_percent ?? 0,
      memory: usage.memory_percent ?? 0,
      disk: usage.disk_percent ?? 0,
      processes: usage.processes ?? 0,
    };

    setHistory((prev) => {
      const next = [...prev, sample];
      return next.length > HISTORY_LENGTH ? next.slice(next.length - HISTORY_LENGTH) : next;
    });
  }, [usage]);

  if (!usage) return null;

  const cpuValues = history.map((s) => s.cpu);
  const memoryValues = history.map((s) => s.memory);
  const diskValues = history.map((s) => s.disk);
  const processValues = history.map((s) => s.processes);

  const chartData = history.map((sample) => ({
    time: new Date(sample.t).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }),
    cpu: round(sample.cpu, 1),
    memory: round(sample.memory, 1),
    disk: round(sample.disk, 1),
  }));

  return (
    <div className={cn('space-y-3', className)}>
      <StatGrid>
        <StatTile
          label="CPU"
          value={round(usage.cpu_percent ?? 0, 1)}
          unit="%"
          tone={toneForPercent(usage.cpu_percent ?? 0)}
          delta={deltaOverWindow(cpuValues)}
          trend={cpuValues}
          icon={<Cpu className="h-3.5 w-3.5" />}
        />
        <StatTile
          label="Memory"
          value={round(usage.memory_percent ?? 0, 1)}
          unit="%"
          tone={toneForPercent(usage.memory_percent ?? 0)}
          delta={deltaOverWindow(memoryValues)}
          trend={memoryValues}
          icon={<MemoryStick className="h-3.5 w-3.5" />}
        />
        <StatTile
          label="Disk"
          value={round(usage.disk_percent ?? 0, 1)}
          unit="%"
          tone={toneForPercent(usage.disk_percent ?? 0)}
          delta={deltaOverWindow(diskValues)}
          trend={diskValues}
          icon={<HardDrive className="h-3.5 w-3.5" />}
        />
        <StatTile
          label="Processes"
          value={usage.processes ?? 0}
          tone="default"
          delta={deltaOverWindow(processValues)}
          trend={processValues}
          icon={<Network className="h-3.5 w-3.5" />}
        />
      </StatGrid>

      {showGauges && (
        <div className="flex flex-wrap items-center justify-around gap-4 rounded-xl border border-white/[0.07] bg-white/[0.02] p-3">
          <RadialGauge
            value={usage.cpu_percent ?? 0}
            label="CPU"
            alert={(usage.cpu_percent ?? 0) >= 90}
          />
          <RadialGauge
            value={usage.memory_percent ?? 0}
            label="Memory"
            alert={(usage.memory_percent ?? 0) >= 90}
          />
          <RadialGauge
            value={usage.disk_percent ?? 0}
            label="Disk"
            alert={(usage.disk_percent ?? 0) >= 90}
          />
          {usage.memory_available_mb ? (
            <div className="flex flex-col items-center gap-1 px-2">
              <Activity className="h-4 w-4 text-cyan-400" />
              <span className="font-mono text-sm tabular-nums text-foreground/85">
                {round(usage.memory_available_mb, 0)}
                <span className="ml-0.5 text-[10px] text-muted-foreground/60">MB</span>
              </span>
              <span className="text-[9.5px] uppercase tracking-widest text-muted-foreground/50">
                Available
              </span>
            </div>
          ) : null}
        </div>
      )}

      {showChart && (
        <TimeSeriesChart
          title="Resource utilisation"
          description={`Last ${history.length} samples`}
          xKey="time"
          data={chartData}
          height={200}
          series={[
            { key: 'cpu', label: 'CPU %', color: 'hsl(190 100% 50%)' },
            { key: 'memory', label: 'Memory %', color: 'hsl(174 100% 45%)' },
            { key: 'disk', label: 'Disk %', color: 'hsl(258 90% 66%)' },
          ]}
          threshold={{ value: 90, label: 'critical' }}
          formatValue={(value) => `${value.toFixed(1)}%`}
        />
      )}
    </div>
  );
}

function round(value: number, digits: number): number {
  if (!Number.isFinite(value)) return 0;
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

export { MetricBarChart };