/**
 * JARVIS Global Search — Universal Information Discovery (spec §26–31, §63).
 *
 * A global search bar that federates across all platform domains.
 * Shows results grouped by source domain, with inline handoffs to Browser,
 * Research, and Knowledge.
 */
'use client';

import * as React from 'react';
import { Search, Loader2, Globe, BookOpen, MessageSquare, Bot, FileText, Folder, Bell, Brain, ExternalLink } from 'lucide-react';
import { useGlobalSearchStore } from '@/features/search/store';
import { SearchResult } from '@/features/search/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';

const DOMAIN_ICONS: Record<string, React.ReactNode> = {
  knowledge: <BookOpen className="h-3 w-3" />,
  memory: <Brain className="h-3 w-3" />,
  chat: <MessageSquare className="h-3 w-3" />,
  agents: <Bot className="h-3 w-3" />,
  tasks: <FileText className="h-3 w-3" />,
  browser: <Globe className="h-3 w-3" />,
  notes: <Folder className="h-3 w-3" />,
  reminders: <Bell className="h-3 w-3" />,
  research: <Brain className="h-3 w-3" />,
  missions: <Globe className="h-3 w-3" />,
  evidence: <FileText className="h-3 w-3" />,
};

const DOMAIN_LABELS: Record<string, string> = {
  knowledge: 'Knowledge',
  memory: 'Memory',
  chat: 'Chat',
  agents: 'Agents',
  tasks: 'Tasks',
  browser: 'Browser',
  notes: 'Notes',
  reminders: 'Reminders',
  research: 'Research',
  missions: 'Missions',
  evidence: 'Evidence',
};

interface GlobalSearchProps {
  onNavigate?: (result: SearchResult) => void;
  placeholder?: string;
  compact?: boolean;
}

export function GlobalSearch({ onNavigate, placeholder = 'Search across JARVIS...', compact = false }: GlobalSearchProps) {
  const {
    query,
    results,
    totalResults,
    isSearching,
    error,
    domainsSearched,
    tookMs,
    setQuery,
    search,
    suggest,
    clear,
    getDomainStatus,
  } = useGlobalSearchStore();

  const [expanded, setExpanded] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // Debounced search trigger
  const debounceRef = React.useRef<NodeJS.Timeout | null>(null);
  const handleQueryChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(e.target.value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (e.target.value.trim().length >= 2) {
      debounceRef.current = setTimeout(() => {
        search({ query: e.target.value, includeWeb: true });
      }, 300);
    } else {
      clear();
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim().length >= 1) {
      search({ query, includeWeb: true });
    }
  };

  const handleResultClick = (result: SearchResult) => {
    onNavigate?.(result);
    setExpanded(false);
  };

  // Load domain status on mount
  React.useEffect(() => {
    if (inputRef.current) {
      inputRef.current.focus();
    }
    getDomainStatus();
  }, []);

  if (compact) {
    return (
      <Button
        variant="ghost"
        size="sm"
        className="h-8 w-8 px-2"
        onClick={() => setExpanded(!expanded)}
      >
        <Search className="h-4 w-4" />
      </Button>
    );
  }

  return (
    <div className="relative w-full">
      <form onSubmit={handleSubmit} className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/50" />
        <Input
          ref={inputRef}
          value={query}
          onChange={handleQueryChange}
          onFocus={() => setExpanded(true)}
          onBlur={() => setTimeout(() => setExpanded(false), 200)}
          placeholder={placeholder}
          className="pl-10 pr-4 h-9 bg-white/[0.02] border-white/5 focus:border-white/10"
        />
        {isSearching && (
          <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground/50" />
        )}
      </form>

      {expanded && (query.length >= 2 || results.length > 0) && (
        <div className="absolute top-12 z-50 w-full rounded-md border border-white/10 bg-popover shadow-lg max-h-96 overflow-hidden">
          <ScrollArea className="max-h-80">
            {error && (
              <div className="p-3 text-sm text-destructive">{error}</div>
            )}

            {!isSearching && results.length === 0 && query.length >= 2 && (
              <div className="p-4 text-center text-sm text-muted-foreground/60">
                No results found for "{query}"
              </div>
            )}

            {!isSearching && results.length > 0 && (
              <div className="p-1">
                {results.map((result) => (
                  <SearchResultItem
                    key={`${result.source}-${result.id}`}
                    result={result}
                    onClick={() => handleResultClick(result)}
                  />
                ))}
                <div className="px-3 py-2 text-xs text-muted-foreground/60 border-t border-white/5">
                  {totalResults} results in {tookMs}ms
                  {domainsSearched.length > 0 && ` across ${domainsSearched.join(', ')}`}
                </div>
              </div>
            )}

            {!isSearching && results.length === 0 && query.length < 2 && (
              <div className="p-4 text-center text-sm text-muted-foreground/60">
                Type 2+ characters to search across Knowledge, Memory, Chat, Agents, Browser, Notes, Research...
              </div>
            )}
          </ScrollArea>
        </div>
      )}
    </div>
  );
}

export function GlobalSearchCompact({ onNavigate }: { onNavigate?: (result: SearchResult) => void }) {
  return <GlobalSearch onNavigate={onNavigate} compact={true} />;
}

function SearchResultItem({ result, onClick }: { result: SearchResult; onClick: () => void }) {
  const icon = DOMAIN_ICONS[result.source] || <FileText className="h-3 w-3" />;
  const label = DOMAIN_LABELS[result.source] || result.source;

  return (
    <button
      onClick={onClick}
      className="w-full text-left p-3 hover:bg-accent/50 rounded-md transition-colors group"
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 mt-0.5">{icon}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="text-xs">
              {label}
            </Badge>
            {result.url && (
              <ExternalLink className="h-3 w-3 opacity-0 group-hover:opacity-100 text-muted-foreground/40 transition-opacity" />
            )}
          </div>
          <p className="text-sm font-medium mt-1 line-clamp-1">
            {result.title || <span className="italic text-muted-foreground/60">Untitled</span>}
          </p>
          {result.snippet && (
            <p className="text-sm text-muted-foreground/70 mt-1 line-clamp-2">
              {result.snippet}
            </p>
          )}
          {result.timestamp && (
            <p className="text-xs text-muted-foreground/50 mt-1">
              {new Date(result.timestamp).toLocaleDateString()}
            </p>
          )}
        </div>
        {result.score > 0 && (
          <div className="flex-shrink-0">
            <Badge variant="outline" className="text-xs">
              {(result.score * 100).toFixed(0)}
            </Badge>
          </div>
        )}
      </div>
    </button>
  );
}
