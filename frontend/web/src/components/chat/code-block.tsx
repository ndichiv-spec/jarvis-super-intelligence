'use client';

import { useCallback, useMemo, useState } from 'react';
import { Check, Copy, WrapText } from 'lucide-react';

import { cn } from '@/lib/utils';
import { tokenize, type TokenType } from '@/lib/highlight';

/**
 * Token colours.
 *
 * Mapped onto the existing holographic palette (cyan primary, teal accent) so
 * highlighted code sits inside the current design language instead of importing
 * a foreign theme. Uses the CSS variables that `globals.css` already defines,
 * which means it follows theme changes for free.
 */
const TOKEN_CLASS: Record<TokenType, string> = {
  plain: 'text-foreground/80',
  keyword: 'text-violet-300',
  string: 'text-emerald-300',
  comment: 'text-muted-foreground/50 italic',
  number: 'text-amber-300',
  function: 'text-cyan-300',
  punctuation: 'text-muted-foreground/60',
  operator: 'text-pink-300',
  type: 'text-teal-300',
  tag: 'text-rose-300',
  attribute: 'text-orange-300',
  property: 'text-sky-300',
  constant: 'text-amber-200',
};

interface CodeBlockProps {
  code: string;
  language?: string | null;
  /** Show the language label in the header. */
  showLanguage?: boolean;
  /** Allow long lines to wrap instead of scrolling horizontally. */
  wrap?: boolean;
  className?: string;
  /** Maximum height in pixels before the body scrolls. */
  maxHeight?: number;
}

export function CodeBlock({
  code,
  language,
  showLanguage = true,
  wrap = false,
  className,
  maxHeight,
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const [wrapLines, setWrapLines] = useState(wrap);

  const tokens = useMemo(() => tokenize(code, language), [code, language]);

  const copy = useCallback(() => {
    const write = navigator.clipboard?.writeText(code);
    if (!write) return;
    void write.then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    });
  }, [code]);

  const label = language?.trim();

  return (
    <figure
      className={cn(
        'group/code relative my-3 overflow-hidden rounded-lg border border-white/10 bg-black/40',
        'shadow-[0_0_20px_rgba(0,212,255,0.06)]',
        className
      )}
    >
      <figcaption className="flex items-center justify-between gap-2 border-b border-white/5 bg-white/[0.03] px-3 py-1.5">
        <span className="font-mono text-[10px] uppercase tracking-widest text-cyan-400/70">
          {showLanguage && label ? label : 'code'}
        </span>

        <div className="flex items-center gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover/code:opacity-100">
          <button
            type="button"
            onClick={() => setWrapLines((v) => !v)}
            aria-label={wrapLines ? 'Disable line wrapping' : 'Enable line wrapping'}
            title={wrapLines ? 'Disable wrap' : 'Wrap lines'}
            className={cn(
              'rounded p-1 text-muted-foreground/50 transition-colors hover:bg-white/5 hover:text-foreground/80',
              wrapLines && 'text-cyan-400/80'
            )}
          >
            <WrapText className="h-3 w-3" />
          </button>
          <button
            type="button"
            onClick={copy}
            aria-label="Copy code to clipboard"
            title="Copy"
            className="rounded p-1 text-muted-foreground/50 transition-colors hover:bg-white/5 hover:text-foreground/80"
          >
            {copied ? (
              <Check className="h-3 w-3 text-emerald-400" />
            ) : (
              <Copy className="h-3 w-3" />
            )}
          </button>
        </div>
      </figcaption>

      <pre
        className={cn(
          'overflow-x-auto p-3 font-mono text-[12.5px] leading-relaxed',
          wrapLines && 'whitespace-pre-wrap break-words'
        )}
        style={maxHeight ? { maxHeight, overflowY: 'auto' } : undefined}
      >
        <code>
          {tokens.map((token, index) => (
            <span key={index} className={TOKEN_CLASS[token.type]}>
              {token.value}
            </span>
          ))}
        </code>
      </pre>

      <span aria-live="polite" className="sr-only">
        {copied ? 'Code copied to clipboard' : ''}
      </span>
    </figure>
  );
}