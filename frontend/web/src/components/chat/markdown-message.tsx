'use client';

import { memo, useMemo, type ComponentPropsWithoutRef, type ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { cn } from '@/lib/utils';
import { CodeBlock } from '@/components/chat/code-block';

/**
 * Markdown rendering for chat.
 *
 * Two problems this addresses beyond plain `react-markdown`:
 *
 *  1. Streaming. Assistant output arrives token by token, so fenced code blocks,
 *     emphasis and lists are routinely half-written. `react-markdown` handles
 *     most of that, but inline code fences with no closing backticks fall back
 *     to a paragraph of literal backticks. {@link closeDanglingFence} closes
 *     them before parsing so a partial block renders as a code block instead of
 *     jumping to prose mid-stream.
 *
 *  2. Presentation. Every element is restyled onto the existing holographic
 *     tokens so markdown inherits the app's surface, border and accent colours
 *     rather than browser defaults.
 */

interface MarkdownMessageProps {
  children: string;
  className?: string;
  /** Animate the caret while tokens are still arriving. */
  streaming?: boolean;
}

const CARET = (
  <span
    aria-hidden="true"
    className="ml-0.5 inline-block h-[1em] w-[2px] translate-y-[2px] animate-pulse bg-cyan-400/80"
  />
);

/**
 * Close an unterminated fenced code block at the end of the text.
 *
 * ```ts
 * closeDanglingFence("intro\n\n```py\nprint(1)")  // -> "intro\n\n```py\nprint(1)\n```"
 * ```
 *
 * Only fires for an odd number of fence markers, so complete blocks are left
 * untouched and text that merely contains backticks inline is unaffected.
 */
export function closeDanglingFence(text: string): string {
  const fencePattern = /^([ \t]*)(`{3,}|~{3,})[^\n]*$/gm;
  let open = false;
  let marker = '';

  fencePattern.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = fencePattern.exec(text)) !== null) {
    if (!open) {
      open = true;
      marker = match[2][0];
    } else if (match[2][0] === marker) {
      open = false;
      marker = '';
    }
  }

  if (!open) return text;
  const closing = /[ \t]*$/.test(text) ? '\n' : '\n';
  return `${text}${closing}${marker.repeat(3)}`;
}

/** Fenced-code plugin: keeps the raw text and info string out of the tree. */
function FencedCode({ className: classNameProp, children, ...props }: ComponentPropsWithoutRef<'code'>) {
  const className = classNameProp ?? '';
  const languageMatch = /language-([\w+#-]+)/.exec(className);
  const language = languageMatch?.[1] ?? null;

  // Only handle block-level code here; inline code has no language class and no
  // newlines, and is rendered by the `code` mapping below.
  const isBlock = className.includes('language-') || String(children).includes('\n');

  if (!isBlock) {
    return (
      <code
        className="rounded border border-white/10 bg-white/[0.05] px-1 py-0.5 font-mono text-[0.9em] text-cyan-200/90"
        {...props}
      >
        {children}
      </code>
    );
  }

  const code = String(children).replace(/\n$/, '');

  return (
    <CodeBlock
      code={code}
      language={language}
      showLanguage={Boolean(language)}
    />
  );
}

const components: Components = {
  code: FencedCode,

  p: ({ className, ...props }) => (
    <p className={cn('whitespace-pre-wrap leading-relaxed [&:not(:first-child)]:mt-3', className)} {...props} />
  ),

  h1: ({ className, children, ...props }) => (
    <h1 className={cn('mt-5 text-lg font-semibold tracking-tight text-foreground', className)} {...props}>
      {children}
    </h1>
  ),
  h2: ({ className, children, ...props }) => (
    <h2 className={cn('mt-5 border-b border-white/5 pb-1.5 text-base font-semibold text-foreground', className)} {...props}>
      {children}
    </h2>
  ),
  h3: ({ className, children, ...props }) => (
    <h3 className={cn('mt-4 text-sm font-semibold text-foreground/95', className)} {...props}>
      {children}
    </h3>
  ),
  h4: ({ className, children, ...props }) => (
    <h4 className={cn('mt-4 text-sm font-medium text-foreground/90', className)} {...props}>
      {children}
    </h4>
  ),
  h5: ({ className, children, ...props }) => (
    <h5 className={cn('mt-3 text-[13px] font-medium text-foreground/85', className)} {...props}>
      {children}
    </h5>
  ),
  h6: ({ className, children, ...props }) => (
    <h6 className={cn('mt-3 text-xs font-medium uppercase tracking-wide text-muted-foreground/70', className)} {...props}>
      {children}
    </h6>
  ),

  ul: ({ className, ...props }) => (
    <ul className={cn('my-2 list-disc space-y-1 pl-5 marker:text-cyan-400/50', className)} {...props} />
  ),
  ol: ({ className, ...props }) => (
    <ol className={cn('my-2 list-decimal space-y-1 pl-5 marker:text-cyan-400/60 marker:font-mono', className)} {...props} />
  ),

  a: ({ className, href, children, ...props }) => (
    <a
      href={href}
      className={cn(
        'font-medium text-cyan-400 underline decoration-cyan-400/30 underline-offset-2 transition-colors hover:decoration-cyan-400/70',
        className
      )}
      {...props}
    >
      {children}
    </a>
  ),

  strong: ({ className, ...props }) => (
    <strong className={cn('font-semibold text-foreground', className)} {...props} />
  ),
  em: ({ className, ...props }) => <em className={cn('italic text-foreground/90', className)} {...props} />,
  del: ({ className, ...props }) => (
    <del className={cn('text-muted-foreground/60 line-through', className)} {...props} />
  ),

  blockquote: ({ className, ...props }) => (
    <blockquote
      className={cn(
        'my-3 border-l-2 border-cyan-400/40 bg-cyan-400/[0.04] py-1 pl-3 text-foreground/80',
        className
      )}
      {...props}
    />
  ),

  hr: ({ className, ...props }) => (
    <hr className={cn('my-5 border-white/10', className)} {...props} />
  ),

  table: ({ className, ...props }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-white/10">
      <table className={cn('w-full border-collapse text-[13px]', className)} {...props} />
    </div>
  ),
  thead: ({ className, ...props }) => (
    <thead className={cn('bg-white/[0.04]', className)} {...props} />
  ),
  th: ({ className, ...props }) => (
    <th
      className={cn(
        'border-b border-white/10 px-3 py-2 text-left font-medium text-foreground/90',
        className
      )}
      {...props}
    />
  ),
  td: ({ className, ...props }) => (
    <td className={cn('border-b border-white/5 px-3 py-2 align-top text-foreground/80', className)} {...props} />
  ),

  input: ({ className, ...props }) => (
    <input
      type="checkbox"
      checked={props.checked ?? false}
      readOnly
      className={cn(
        'mr-1.5 h-3 w-3 accent-cyan-400',
        // GFM task-list checkboxes are decorative here: the list itself is the
        // record, and the user is not editing it.
        'pointer-events-none',
        className
      )}
      {...props}
    />
  ),

  img: ({ className, alt, ...props }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      alt={alt ?? ''}
      loading="lazy"
      className={cn('my-3 max-w-full rounded-lg border border-white/10', className)}
      {...props}
    />
  ),
};

function MarkdownMessageImpl({ children, className, streaming = false }: MarkdownMessageProps) {
  const prepared = useMemo(() => closeDanglingFence(children), [children]);

  return (
    <div className={cn('text-[13.5px] text-foreground/85', className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {prepared}
      </ReactMarkdown>
      {streaming && CARET}
    </div>
  );
}

/**
 * Memoised so a streaming update only re-parses the message that actually
 * changed, rather than every message in the transcript.
 */
export const MarkdownMessage = memo(MarkdownMessageImpl);

function MarkdownFallback({ children }: { children?: ReactNode }) {
  return <>{children}</>;
}

export { MarkdownFallback };