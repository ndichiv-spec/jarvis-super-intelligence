/**
 * JARVIS Design System
 *
 * Centralised, single-source-of-truth for shared visual primitives.
 * Every new component should consume from here rather than defining its own
 * glass/margin/color constants — eliminating the inconsistency flagged in
 * section 36 (REMOVE FRAGMENTATION) of the upgrade spec.
 */

import { designTokens } from '@/lib/design-tokens';

// ---------------------------------------------------------------------------
// Status helpers — maps a ResourceStatus to a display variant
// ---------------------------------------------------------------------------

import type { ResourceStatus, SeverityLevel } from '@/lib/types/platform';

export type StatusVariant = 'default' | 'success' | 'warning' | 'destructive' | 'muted';

export function statusToVariant(status: ResourceStatus): StatusVariant {
  switch (status) {
    case 'completed':
    case 'idle':
    case 'working':
      return 'success';
    case 'offline':
    case 'failed':
    case 'cancelled':
      return 'destructive';
    case 'degraded':
    case 'rate_limited':
    case 'paused':
    case 'loading':
    case 'streaming':
    case 'queued':
      return 'warning';
    case 'unauthorized':
      return 'muted';
    default:
      return 'muted';
  }
}

export function severityToVariant(severity: SeverityLevel): StatusVariant {
  switch (severity) {
    case 'info':
      return 'default';
    case 'low':
      return 'success';
    case 'medium':
      return 'warning';
    case 'high':
      return 'destructive';
    case 'critical':
      return 'destructive';
    default:
      return 'muted';
  }
}

export function severityToColorClass(severity: SeverityLevel): string {
  switch (severity) {
    case 'critical':
      return 'text-red-400';
    case 'high':
      return 'text-orange-400';
    case 'medium':
      return 'text-yellow-400';
    case 'low':
      return 'text-emerald-400';
    case 'info':
    default:
      return 'text-blue-400';
  }
}

// ---------------------------------------------------------------------------
// Glassmorphic card class strings — reused by panels, dialogs, cards
// ---------------------------------------------------------------------------

export const glassCard = 'bg-[hsl(222,47%,5%)/0.6] border border-white/5 backdrop-blur-xl';
export const glassCardHover = 'hover:bg-[hsl(222,47%,6%)/0.7]';
export const glassPanel = 'bg-[hsl(222,47%,5%)/0.8] border border-white/10 backdrop-blur-2xl';
export const glassBorder = 'border-white/5';

// ---------------------------------------------------------------------------
// Spacing scale (re-exported for components that need it)
// ---------------------------------------------------------------------------

export const spacing = designTokens.spacing;
export const radius = designTokens.radius;
export const gradients = designTokens.gradients;
export const colors = designTokens.colors;

// ---------------------------------------------------------------------------
// Loading / Error / Empty state props
// ---------------------------------------------------------------------------

export interface AsyncStateProps {
  status: ResourceStatus;
  error: string | null;
  isEmpty?: boolean;
  emptyMessage?: string;
  loadingMessage?: string;
}

export const STATUS_MESSAGES: Record<ResourceStatus, string> = {
  idle: 'Ready',
  loading: 'Loading...',
  streaming: 'Streaming...',
  working: 'Processing...',
  completed: 'Complete',
  failed: 'Failed',
  offline: 'Offline',
  degraded: 'Degraded',
  unauthorized: 'Authentication required',
  rate_limited: 'Rate limited — retrying',
  queued: 'Queued',
  paused: 'Paused',
  cancelled: 'Cancelled',
};
