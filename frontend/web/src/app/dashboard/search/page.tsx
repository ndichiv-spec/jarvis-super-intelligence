'use client';

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import {
  AlertCircle, ArrowUpRight, BookOpen, Clock3, Globe2, Loader2,
  Search, ShieldCheck, Sparkles,
} from 'lucide-react';
import { AuthError } from '@/lib/api-client';
import { searchApi } from '@/features/search/api';
import type { SearchResponse, SearchResult, SearchStatusResponse } from '@/features/search/types';

const DEFAULT_DOMAINS = [
  'all', 'knowledge', 'memory', 'chat', 'agents', 'tasks', 'browser', 'notes',
  'reminders', 'research', 'missions', 'evidence',
] as const;
const DOMAIN_ROUTES: Record<string, string> = {
  knowledge: '/dashboard/knowledge',
  memory: '/dashboard/memory',
  chat: '/dashboard',
  agents: '/dashboard/agents',
  tasks: '/dashboard/agents',
  browser: '/dashboard/embedded-browser',
  notes: '/dashboard/knowledge',
  reminders: '/dashboard',
  research: '/dashboard/search',
  missions: '/dashboard/agents',
  evidence: '/dashboard/embedded-browser',
};

function resultTitle(result: SearchResult) {
  return result.title?.trim() || 'Untitled result';
}

function resultSnippet(result: SearchResult) {
  return result.snippet?.trim() || 'No preview is available for this result.';
}

function internalDestination(result: SearchResult) {
  if (result.url) {
    return result.url.startsWith('/') && !result.url.startsWith('//') ? result.url : undefined;
  }
  return DOMAIN_ROUTES[result.source?.toLowerCase()];
}

function externalDestination(url?: string) {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null;
  } catch {
    return null;
  }
}

function SearchResultRow({
  result,
  index,
  onPromote,
  pending,
}: {
  result: SearchResult;
  index: number;
  onPromote: (result: SearchResult) => void;
  pending: boolean;
}) {
  const source = result.source || 'platform';
  const internalUrl = internalDestination(result);
  const externalUrl = internalUrl ? null : externalDestination(result.url);
  const detail = result.metadata && typeof result.metadata === 'object'
    ? Object.entries(result.metadata).filter(([, value]) => ['string', 'number', 'boolean'].includes(typeof value)).slice(0, 3)
    : [];

  return (
    <article className="group grid gap-3 border-t border-white/10 py-5 first:border-t-0 sm:grid-cols-[2.5rem_minmax(0,1fr)_auto] sm:gap-5">
      <span aria-hidden="true" className="pt-0.5 font-mono text-xs tabular-nums text-slate-500">
        {String(index + 1).padStart(2, '0')}
      </span>
      <div className="min-w-0">
        <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan-300">{source}</span>
          {typeof result.relevance === 'number' && (
            <span className="font-mono text-[10px] text-slate-400">relevance {(result.relevance * 100).toFixed(0)}%</span>
          )}
          {typeof result.score === 'number' && (
            <span className="font-mono text-[10px] text-slate-500">score {result.score.toFixed(2)}</span>
          )}
          {result.timestamp && (
            <time className="font-mono text-[10px] text-slate-500" dateTime={result.timestamp}>
              {new Date(result.timestamp).toLocaleString()}
            </time>
          )}
        </div>
        <h2 className="text-base font-medium leading-snug text-slate-100">{resultTitle(result)}</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">{resultSnippet(result)}</p>
        {detail.length > 0 && (
          <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1">
            {detail.map(([key, value]) => (
              <div key={key} className="flex gap-1.5 text-xs">
                <dt className="text-slate-500">{key.replaceAll('_', ' ')}:</dt>
                <dd className="max-w-[16rem] truncate text-slate-300">{String(value)}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
      <div className="flex flex-wrap items-start gap-3 sm:justify-end">
        {internalUrl && (
          <Link
            className="inline-flex min-h-10 items-center gap-2 text-xs text-slate-300 transition-colors hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
            href={internalUrl}
            aria-label={`Open ${resultTitle(result)} in JARVIS`}
          >
            Open in JARVIS <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        )}
        {externalUrl && (
          <Link
            className="inline-flex min-h-10 items-center gap-2 border border-cyan-400/30 px-3 text-xs text-cyan-200 transition-colors hover:bg-cyan-400/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
            href={`/dashboard/embedded-browser?url=${encodeURIComponent(externalUrl)}`}
            aria-label={`Open ${resultTitle(result)} in JARVIS Browser`}
          >
            <Globe2 className="h-3.5 w-3.5" aria-hidden="true" />
            Open in JARVIS Browser
          </Link>
        )}
        <button
          type="button"
          disabled={pending}
          className="inline-flex min-h-10 items-center gap-2 text-xs text-slate-400 transition-colors hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 disabled:cursor-wait disabled:opacity-50"
          onClick={() => onPromote(result)}
        >
          {pending ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />}
          {pending ? 'Saving' : 'Save to Knowledge'}
        </button>
        {!internalUrl && !externalUrl && (
          <span className="self-center font-mono text-[10px] uppercase tracking-wider text-slate-600">
            No destination
          </span>
        )}
      </div>
    </article>
  );
}

export default function GlobalSearchPage() {
  const [query, setQuery] = useState('');
  const [domain, setDomain] = useState('all');
  const [domains, setDomains] = useState<string[]>([...DEFAULT_DOMAINS]);
  const [domainStatus, setDomainStatus] = useState<SearchStatusResponse | null>(null);
  const [coverageUnavailable, setCoverageUnavailable] = useState(false);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [searchedQuery, setSearchedQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [isPromoting, setIsPromoting] = useState<string | null>(null);
  const [includeWeb, setIncludeWeb] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const requestId = useRef(0);

  useEffect(() => {
    let active = true;
    void Promise.allSettled([searchApi.listDomains(), searchApi.getStatus()]).then(([domainResult, statusResult]) => {
      if (!active) return;
      if (domainResult.status === 'fulfilled' && Array.isArray(domainResult.value)) {
        const values = [...new Set(['all', ...domainResult.value.map((value) => value.toLowerCase())])];
        setDomains(values);
        setDomain((current) => values.includes(current) ? current : 'all');
      }
      if (statusResult.status === 'fulfilled') setDomainStatus(statusResult.value);
      else setCoverageUnavailable(true);
    });
    return () => { active = false; };
  }, []);

  const handleSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedQuery = query.trim();
    if (!normalizedQuery || isSearching) return;

    const currentRequest = ++requestId.current;
    setIsSearching(true);
    setError(null);
    setActionMessage(null);
    try {
      const result = await searchApi.search(normalizedQuery, domain, 30, includeWeb);
      if (currentRequest !== requestId.current) return;
      setResponse(result);
      setSearchedQuery(normalizedQuery);
    } catch (cause) {
      if (currentRequest !== requestId.current) return;
      if (!(cause instanceof AuthError)) {
        setError(cause instanceof Error ? cause.message : 'Search is temporarily unavailable.');
      }
    } finally {
      if (currentRequest === requestId.current) setIsSearching(false);
    }
  };

  const promoteToKnowledge = async (result: SearchResult) => {
    setIsPromoting(result.id);
    setActionMessage(null);
    try {
      const promotion = await searchApi.toKnowledge(searchedQuery, result.id);
      setActionMessage(promotion.promoted
        ? `Saved to Knowledge${promotion.knowledge_key ? ` as ${promotion.knowledge_key}` : ''}.`
        : promotion.reason || 'This result could not be promoted.');
    } catch (cause) {
      setActionMessage(cause instanceof Error ? cause.message : 'Could not save this result to Knowledge.');
    } finally {
      setIsPromoting(null);
    }
  };

  const runResearch = async () => {
    if (!searchedQuery) return;
    setIsPromoting('research');
    setActionMessage(null);
    try {
      const research = await searchApi.toResearch(searchedQuery);
      setActionMessage(`Research session created with ${research.seeded_results} seeded results.`);
    } catch (cause) {
      setActionMessage(cause instanceof Error ? cause.message : 'Could not start a research session.');
    } finally {
      setIsPromoting(null);
    }
  };

  const hasStaleResults = Boolean(response && searchedQuery !== query.trim());
  const results = response?.results ?? [];
  const coverage = useMemo(() => {
    const status = domainStatus?.domains ?? {};
    const available = Object.entries(status).filter(([, value]) => value.available).length;
    return { available, total: Object.keys(status).length };
  }, [domainStatus]);

  return (
    <main className="min-h-full bg-[#080d12] px-4 py-8 text-slate-100 sm:px-7 lg:px-10">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 border-b border-white/10 pb-6">
          <div className="mb-4 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.22em] text-cyan-300">
            <span className="h-1.5 w-1.5 rounded-full bg-cyan-300" aria-hidden="true" />
            JARVIS / Retrieval
          </div>
          <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Search the system</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
                Search connected JARVIS domains. Results and coverage reflect the sources the service actually queried.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 font-mono text-[10px] uppercase tracking-wider text-slate-400">
              <span className="inline-flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-emerald-400" aria-hidden="true" />
                Authenticated search
              </span>
              <span className="inline-flex items-center gap-2" role="status" aria-label="Search source availability">
                <span className={`h-1.5 w-1.5 rounded-full ${domainStatus?.healthy ? 'bg-emerald-400' : domainStatus ? 'bg-amber-300' : 'bg-slate-500'}`} />
                {domainStatus
                  ? `${coverage.available}/${coverage.total} domains available`
                  : coverageUnavailable ? 'Coverage unavailable' : 'Checking coverage'}
              </span>
            </div>
          </div>
        </header>

        <form onSubmit={handleSearch} className="border border-white/10 bg-[#0d151c] p-3 sm:p-4">
          <label htmlFor="global-search-query" className="sr-only">Search JARVIS</label>
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_12rem_auto]">
            <div className="relative">
              <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-cyan-300" aria-hidden="true" />
              <input
                id="global-search-query"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search knowledge, memory, conversations…"
                className="h-12 w-full border border-white/10 bg-[#080d12] pl-11 pr-4 text-sm text-slate-100 placeholder:text-slate-600 focus:border-cyan-400/70 focus:outline-none focus:ring-2 focus:ring-cyan-400/20"
              />
            </div>
            <label className="sr-only" htmlFor="search-domain">Search domain</label>
            <select
              id="search-domain"
              value={domain}
              onChange={(event) => setDomain(event.target.value)}
              className="h-12 border border-white/10 bg-[#080d12] px-3 text-sm capitalize text-slate-300 focus:border-cyan-400/70 focus:outline-none focus:ring-2 focus:ring-cyan-400/20"
            >
              {domains.map((item) => <option key={item} value={item}>{item === 'all' ? 'All domains' : item}</option>)}
            </select>
            <button
              type="submit"
              disabled={!query.trim() || isSearching}
              className="inline-flex h-12 items-center justify-center gap-2 bg-cyan-300 px-5 text-sm font-semibold text-slate-950 transition-colors hover:bg-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-100 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0d151c] disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
            >
              {isSearching ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Search className="h-4 w-4" aria-hidden="true" />}
              {isSearching ? 'Searching' : 'Search'}
            </button>
          </div>
          <label className="mt-3 inline-flex cursor-pointer items-center gap-2 px-1 text-xs text-slate-400">
            <input
              type="checkbox"
              checked={includeWeb}
              onChange={(event) => setIncludeWeb(event.target.checked)}
              className="h-4 w-4 accent-cyan-300"
            />
            Include web results
          </label>
          <p className="mt-1 px-1 text-xs text-slate-500">
            Off by default. Web availability depends on connected sources and service policy. Browser handoffs may be blocked by navigation policy.
          </p>
        </form>

        <section className="mt-8" aria-labelledby="results-heading" aria-live="polite" aria-busy={isSearching}>
          <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 id="results-heading" className="font-mono text-xs uppercase tracking-[0.18em] text-slate-300">Results</h2>
              {response && (
                <p className="mt-1 text-xs text-slate-500">
                  {response.total_results} {response.total_results === 1 ? 'match' : 'matches'} for “{searchedQuery}”
                </p>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-wider text-slate-500">
              {response && <span className="inline-flex items-center gap-1.5"><Clock3 className="h-3.5 w-3.5" aria-hidden="true" />{response.took_ms} ms</span>}
              {response && <span>{response.domains_searched.length} domains searched</span>}
              {searchedQuery && (
                <button
                  type="button"
                  onClick={() => void runResearch()}
                  disabled={isPromoting !== null}
                  className="inline-flex items-center gap-1.5 text-cyan-200 hover:text-cyan-100 disabled:opacity-50"
                >
                  {isPromoting === 'research' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                  Send query to Research
                </button>
              )}
            </div>
          </div>

          {error && (
            <div role="alert" className="mb-4 flex items-start gap-3 border border-rose-400/30 bg-rose-950/20 p-4 text-sm text-rose-200">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <div>
                <p className="font-medium">Search could not be completed</p>
                <p className="mt-1 text-rose-200/75">{error}</p>
                {response && <p className="mt-2 text-xs text-rose-200/60">Showing the last successful results below.</p>}
              </div>
            </div>
          )}

          {actionMessage && <p role="status" className="mb-4 border-l-2 border-cyan-300/60 pl-3 text-sm text-cyan-100">{actionMessage}</p>}

          {isSearching && (
            <p className="mb-3 flex items-center gap-2 text-xs text-cyan-200" role="status">
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              Searching connected domains…
            </p>
          )}

          {hasStaleResults && response && (
            <p className="mb-3 border-l-2 border-amber-300/60 pl-3 text-xs text-amber-200/80" role="status">
              Showing results for “{searchedQuery}” while you prepare a new search.
            </p>
          )}

          {response && results.length > 0 && (
            <div className="border-y border-white/10 bg-[#0b1218] px-4 sm:px-6">
              {results.map((result, index) => (
                <SearchResultRow
                  key={`${result.source}:${result.id}:${index}`}
                  result={result}
                  index={index}
                  onPromote={(item) => void promoteToKnowledge(item)}
                  pending={isPromoting === result.id}
                />
              ))}
            </div>
          )}

          {!response && !isSearching && !error && (
            <div className="border border-dashed border-white/10 px-6 py-14 text-center">
              <Search className="mx-auto h-6 w-6 text-slate-600" aria-hidden="true" />
              <p className="mt-4 text-sm text-slate-300">Search across your connected JARVIS workspace</p>
              <p className="mt-1 text-xs text-slate-500">Choose a domain or search everything available to your account.</p>
            </div>
          )}

          {response && results.length === 0 && (
            <div className="border border-white/10 bg-[#0b1218] px-6 py-12 text-center">
              <p className="text-sm text-slate-200">No matches for “{searchedQuery}”</p>
              <p className="mt-2 text-xs text-slate-500">Try a broader phrase or select a different domain.</p>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
