'use client';

import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Loader2,
  Terminal,
  Wrench,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import { CodeBlock } from '@/components/chat/code-block';
import type { ToolCall } from '@/features/chat/types';

/**
 * Tool-call rendering.
 *
 * When the agent invokes a backend capability, the invocation is otherwise
 * invisible: the user sees text appear with no indication that a browser
 * session, a file read, or a provider call happened. These components make each
 * invocation observable -- its arguments, its live status, its result, and its
 * failure -- which is what turns "the assistant answered" into "the assistant
 * went and did the thing".
 *
 * This is the Controlled flavour of generative UI: renderers are registered by
 * tool name against components we own, so the agent chooses *what* appears while
 * the frontend retains full control over presentation and accessibility.
 */

export type ToolCallStatus = 'pending' | 'running' | 'completed' | 'failed';

const STATUS_META: Record<
  ToolCallStatus,
  { label: string; icon: typeof Wrench; tone: string; ring: string }
> = {
  pending: {
    label: 'Queued',
    icon: Wrench,
    tone: 'text-muted-foreground',
    ring: 'border-white/10',
  },
  running: {
    label: 'Running',
    icon: Loader2,
    tone: 'text-cyan-400',
    ring: 'border-cyan-400/30',
  },
  completed: {
    label: 'Completed',
    icon: CheckCircle2,
    tone: 'text-emerald-400',
    ring: 'border-emerald-400/20',
  },
  failed: {
    label: 'Failed',
    icon: AlertTriangle,
    tone: 'text-red-400',
    ring: 'border-red-400/30',
  },
};

/**
 * Human-readable tool labels.
 *
 * Falls back to a title-cased version of the raw name so unregistered tools
 * still read well instead of appearing as `web_search`.
 */
const TOOL_LABELS: Record<string, string> = {
  web_search: 'Web Search',
  browser_navigate: 'Navigate Browser',
  browser_extract: 'Extract Page Content',
  browser_click: 'Click Element',
  browser_type: 'Type Into Element',
  read_file: 'Read File',
  write_file: 'Write File',
  list_directory: 'List Directory',
  run_command: 'Run Command',
  run_python: 'Run Python',
  search_memory: 'Search Memory',
  store_memory: 'Store Memory',
  generate_image: 'Generate Image',
  speak: 'Text to Speech',
  query_database: 'Query Database',
  create_workflow: 'Create Workflow',
  spawn_agent: 'Delegate to Agent',
};

export function toolLabel(name: string): string {
  if (TOOL_LABELS[name]) return TOOL_LABELS[name];
  return name
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

function resolveStatus(tool: ToolCall): ToolCallStatus {
  if (tool.status) return tool.status;
  if (tool.result === undefined) return 'running';
  return 'completed';
}

interface ToolCallCardProps {
  tool: ToolCall;
  /** Expand the result body by default. */
  defaultOpen?: boolean;
  className?: string;
}

/** Renders one tool invocation: header with status, collapsible detail. */
export function ToolCallCard({ tool, defaultOpen = false, className }: ToolCallCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const status = resolveStatus(tool);
  const meta = STATUS_META[status];
  const StatusIcon = meta.icon;

  const { argsText, resultBody, resultLanguage } = useMemo(
    () => describeTool(tool),
    [tool]
  );

  const hasDetail = Boolean(argsText || resultBody);

  return (
    <div
      className={cn(
        'my-2 overflow-hidden rounded-lg border bg-white/[0.02] backdrop-blur-sm',
        meta.ring,
        className
      )}
    >
      <button
        type="button"
        onClick={() => hasDetail && setOpen((v) => !v)}
        aria-expanded={hasDetail ? open : undefined}
        disabled={!hasDetail}
        className={cn(
          'flex w-full items-center gap-2 px-3 py-2 text-left',
          hasDetail && 'transition-colors hover:bg-white/[0.03]',
          !hasDetail && 'cursor-default'
        )}
      >
        <StatusIcon
          className={cn(
            'h-3.5 w-3.5 shrink-0',
            meta.tone,
            status === 'running' && 'animate-spin'
          )}
        />

        <span className="min-w-0 flex-1">
          <span className="block truncate text-[12.5px] font-medium text-foreground/90">
            {toolLabel(tool.name)}
          </span>
          <span className={cn('block text-[10px] uppercase tracking-wider', meta.tone)}>
            {meta.label}
            {tool.result !== undefined && status === 'completed' ? '' : ''}
          </span>
        </span>

        {hasDetail && (
          <ChevronDown
            className={cn(
              'h-3.5 w-3.5 shrink-0 text-muted-foreground/50 transition-transform',
              open && 'rotate-180'
            )}
          />
        )}
      </button>

      {hasDetail && open && (
        <div className="space-y-3 border-t border-white/5 px-3 py-2.5">
          {argsText && (
            <div>
              <SectionLabel>Arguments</SectionLabel>
              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded-md bg-black/30 p-2 font-mono text-[11.5px] leading-relaxed text-foreground/75">
                {argsText}
              </pre>
            </div>
          )}

          {resultBody && (
            <div>
              <SectionLabel>Result</SectionLabel>
              {resultLanguage ? (
                <CodeBlock
                  code={resultBody}
                  language={resultLanguage}
                  className="my-0"
                  showLanguage={false}
                />
              ) : (
                <pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md bg-black/30 p-2 font-mono text-[11.5px] leading-relaxed text-foreground/75">
                  {resultBody}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/50">
      {children}
    </span>
  );
}

interface ToolCallListProps {
  tools: ToolCall[];
  className?: string;
  /** Show a header summarising how many capabilities were invoked. */
  showSummary?: boolean;
}

/** Renders a message's tool calls as a stacked activity list. */
export function ToolCallList({ tools, className, showSummary = true }: ToolCallListProps) {
  if (!tools.length) return null;

  const running = tools.filter((t) => resolveStatus(t) === 'running').length;
  const failed = tools.filter((t) => resolveStatus(t) === 'failed').length;

  return (
    <div className={cn('my-2', className)}>
      {showSummary && (
        <div className="mb-1.5 flex items-center gap-2 text-[10px] uppercase tracking-widest text-muted-foreground/50">
          <Terminal className="h-3 w-3" />
          <span>
            {tools.length} {tools.length === 1 ? 'capability' : 'capabilities'} invoked
          </span>
          {running > 0 && <span className="text-cyan-400/80">{running} active</span>}
          {failed > 0 && <span className="text-red-400/80">{failed} failed</span>}
        </div>
      )}
      <div className="space-y-1.5">
        {tools.map((tool, index) => (
          <ToolCallCard key={`${tool.name}-${index}`} tool={tool} />
        ))}
      </div>
    </div>
  );
}

interface ToolActivityProps {
  tools: ToolCall[] | undefined;
  className?: string;
}

/** Compact inline status shown while the agent is still working. */
export function ToolActivity({ tools, className }: ToolActivityProps) {
  if (!tools?.length) return null;

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground/70',
        className
      )}
      aria-live="polite"
    >
      {tools.map((tool, index) => {
        const status = resolveStatus(tool);
        const meta = STATUS_META[status];
        const StatusIcon = meta.icon;
        return (
          <span
            key={`${tool.name}-${index}`}
            className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.03] px-2 py-0.5"
          >
            <StatusIcon
              className={cn('h-2.5 w-2.5', meta.tone, status === 'running' && 'animate-spin')}
            />
            {toolLabel(tool.name)}
          </span>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Result formatting
// ---------------------------------------------------------------------------

const MAX_RESULT_CHARS = 4000;

/**
 * Turn a tool's arguments and result into display strings.
 *
 * Strings are shown verbatim (they are already meant for humans), everything
 * else is pretty-printed as JSON. Long payloads are truncated with a visible
 * marker rather than silently cut.
 */
function describeTool(tool: ToolCall): {
  argsText: string | null;
  resultBody: string | null;
  resultLanguage: string | null;
} {
  const args = tool.arguments ?? {};
  const argsKeys = Object.keys(args);

  const argsText = argsKeys.length
    ? argsKeys
        .map((key) => `${key}: ${stringifyValue(args[key])}`)
        .join('\n')
    : null;

  if (tool.result === undefined || tool.result === null) {
    return { argsText, resultBody: null, resultLanguage: null };
  }

  if (typeof tool.result === 'string') {
    return {
      argsText,
      resultBody: truncate(tool.result),
      resultLanguage: looksLikeJson(tool.result) ? 'json' : null,
    };
  }

  return {
    argsText,
    resultBody: truncate(stringifyValue(tool.result)),
    resultLanguage: 'json',
  };
}

function stringifyValue(value: unknown): string {
  if (value === null) return 'null';
  if (value === undefined) return 'undefined';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2) ?? String(value);
  } catch {
    return String(value);
  }
}

function looksLikeJson(text: string): boolean {
  const trimmed = text.trim();
  return (
    (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
    (trimmed.startsWith('[') && trimmed.endsWith(']'))
  );
}

function truncate(text: string): string {
  if (text.length <= MAX_RESULT_CHARS) return text;
  const omitted = text.length - MAX_RESULT_CHARS;
  return `${text.slice(0, MAX_RESULT_CHARS)}\n... [${omitted.toLocaleString()} more characters truncated]`;
}