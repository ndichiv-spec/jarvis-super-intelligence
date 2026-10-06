'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Activity, BookOpen, FlaskConical, Globe, Layers3, RefreshCw, Search, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api-client';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

type ApiResult = {
  success?: boolean;
  data?: unknown;
  status?: string;
  [key: string]: unknown;
};

type ResultEntry = {
  title: string;
  value: unknown;
};

async function fetchStatuses(): Promise<Record<string, unknown>> {
  const entries = await Promise.all(STATUS_ENDPOINTS.map(async ([name, endpoint]) => {
    try {
      return [name, await apiClient.get<unknown>(endpoint)] as const;
    } catch (error) {
      return [name, { error: errorMessage(error) }] as const;
    }
  }));
  return Object.fromEntries(entries);
}

const STATUS_ENDPOINTS = [
  ['Research Cortex', '/api/v1/research/status'],
  ['Bio Learner', '/api/v1/learning/status'],
  ['Science Engine', '/api/v1/science/status'],
  ['Technology Radar', '/api/v1/tech/status'],
] as const;

function formatResult(value: unknown): string {
  if (value === undefined) return 'No data returned.';
  const formatted = JSON.stringify(value, null, 2);
  return formatted ?? String(value);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'The request failed.';
}

export default function BioGrowthPage() {
  const [statuses, setStatuses] = useState<Record<string, unknown>>({});
  const [results, setResults] = useState<ResultEntry[]>([]);
  const [working, setWorking] = useState(false);

  const loadStatuses = useCallback(async () => {
    setStatuses(await fetchStatuses());
  }, []);

  useEffect(() => {
    let active = true;
    void fetchStatuses().then((status) => {
      if (active) setStatuses(status);
    });
    return () => {
      active = false;
    };
  }, []);

  const run = async (title: string, request: () => Promise<unknown>) => {
    setWorking(true);
    try {
      const value = await request();
      setResults((current) => [{ title, value }, ...current].slice(0, 8));
      toast.success(`${title} completed`);
    } catch (error) {
      toast.error(`${title} failed: ${errorMessage(error)}`);
    } finally {
      setWorking(false);
    }
  };

  const submit = (
    title: string,
    handler: (form: FormData) => Promise<unknown>,
  ) => async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await run(title, () => handler(form));
  };

  const formFieldClass =
    'w-full rounded-md border border-white/10 bg-slate-950/70 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-cyan-400/60 focus:outline-none';
  const resultPanel = (title: string, request: () => Promise<unknown>) => (
    <Button type="button" variant="outline" disabled={working} onClick={() => void run(title, request)}>
      {title}
    </Button>
  );

  return (
    <div className="flex-1 space-y-6 bg-grid p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500 to-cyan-500 shadow-lg shadow-cyan-500/20">
            <FlaskConical className="h-7 w-7 text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-black text-foreground">Bio-Growth Lab</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Research, learning, mathematical reasoning, and technology discovery through live JARVIS services.
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={() => void loadStatuses()} disabled={working}>
          <RefreshCw className={`mr-2 h-4 w-4 ${working ? 'animate-spin' : ''}`} />
          Refresh status
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {STATUS_ENDPOINTS.map(([name]) => (
          <Card key={name} className="border-white/10 bg-slate-900/70">
            <CardHeader className="pb-2">
              <CardDescription>{name}</CardDescription>
              <CardTitle className="text-base">
                {statuses[name] ? (
                  <Badge
                    variant="outline"
                    className={
                      typeof statuses[name] === 'object' &&
                      statuses[name] !== null &&
                      'error' in statuses[name]
                        ? 'border-rose-400/30 text-rose-200'
                        : 'border-cyan-400/30 text-cyan-200'
                    }
                  >
                    {typeof statuses[name] === 'object' &&
                    statuses[name] !== null &&
                    'error' in statuses[name]
                      ? 'Unavailable'
                      : 'API reachable'}
                  </Badge>
                ) : (
                  <Badge variant="outline">Loading</Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="max-h-24 overflow-auto whitespace-pre-wrap break-words text-xs text-muted-foreground">
                {statuses[name] ? formatResult(statuses[name]) : 'Checking service status…'}
              </pre>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card className="border-white/10 bg-slate-900/70">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg"><Globe className="h-5 w-5 text-cyan-300" /> Research Cortex</CardTitle>
            <CardDescription>Ingest sources and search the knowledge graph using authenticated JARVIS APIs.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form className="space-y-3" onSubmit={submit('Ingest source', (form) =>
              apiClient.post<ApiResult>('/api/v1/research/ingest', {
                url: String(form.get('url') ?? ''),
                title: String(form.get('title') ?? '') || undefined,
              }))}>
              <input className={formFieldClass} name="url" type="url" required placeholder="https://source.example/article" />
              <input className={formFieldClass} name="title" placeholder="Optional source title" />
              <Button type="submit" disabled={working}>Ingest URL</Button>
            </form>
            <form className="space-y-3 border-t border-white/10 pt-4" onSubmit={submit('Ingest research notes', (form) =>
              apiClient.post<ApiResult>('/api/v1/research/ingest-content', {
                title: String(form.get('title') ?? ''),
                content: String(form.get('content') ?? ''),
                source: 'jarvis-bio-growth-lab',
              }))}>
              <input className={formFieldClass} name="title" required placeholder="Research note title" />
              <textarea className={formFieldClass} name="content" required rows={3} placeholder="Paste notes or source text to add to the knowledge graph" />
              <Button type="submit" variant="secondary" disabled={working}>Ingest notes</Button>
            </form>
            <form className="flex gap-2 border-t border-white/10 pt-4" onSubmit={submit('Search research', (form) =>
              apiClient.get<ApiResult>(`/api/v1/research/search/${encodeURIComponent(String(form.get('query') ?? ''))}`))}>
              <input className={formFieldClass} name="query" required placeholder="Search ingested knowledge" />
              <Button type="submit" variant="outline" disabled={working} aria-label="Search research"><Search className="h-4 w-4" /></Button>
            </form>
            <div className="flex flex-wrap gap-2">
              {resultPanel('Load knowledge graph', () => apiClient.get<ApiResult>('/api/v1/research/knowledge-graph'))}
              {resultPanel('Discover technologies', () => apiClient.post<ApiResult>('/api/v1/tech/discover', undefined))}
            </div>
          </CardContent>
        </Card>

        <Card className="border-white/10 bg-slate-900/70">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg"><BookOpen className="h-5 w-5 text-emerald-300" /> Lifelong Learning</CardTitle>
            <CardDescription>Study concepts, inspect domain paths, and review spaced-repetition items.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form className="space-y-3" onSubmit={submit('Study concept', (form) =>
              apiClient.post<ApiResult>('/api/v1/learning/study', {
                domain: String(form.get('domain') ?? ''),
                concept: String(form.get('concept') ?? ''),
              }))}>
              <input className={formFieldClass} name="domain" required placeholder="Domain (e.g. biology, mathematics)" />
              <input className={formFieldClass} name="concept" required placeholder="Concept to study" />
              <Button type="submit" disabled={working}>Study concept</Button>
            </form>
            <form className="flex gap-2 border-t border-white/10 pt-4" onSubmit={submit('Load learning path', (form) =>
              apiClient.get<ApiResult>(`/api/v1/learning/path/${encodeURIComponent(String(form.get('domain') ?? ''))}`))}>
              <input className={formFieldClass} name="domain" required placeholder="Learning domain" />
              <Button type="submit" variant="outline" disabled={working}>Path</Button>
            </form>
            <form className="grid gap-2 border-t border-white/10 pt-4 sm:grid-cols-[1fr_7rem_auto]" onSubmit={submit('Review learning item', (form) =>
              apiClient.post<ApiResult>('/api/v1/learning/review', {
                item_key: String(form.get('item_key') ?? ''),
                quality: Number(form.get('quality') ?? 3),
              }))}>
              <input className={formFieldClass} name="item_key" required placeholder="Review item key" />
              <input className={formFieldClass} name="quality" type="number" min="0" max="5" defaultValue="3" aria-label="Review quality from 0 to 5" />
              <Button type="submit" variant="secondary" disabled={working}>Review</Button>
            </form>
            <div className="flex flex-wrap gap-2">
              {resultPanel('Show reviews due', () => apiClient.get<ApiResult>('/api/v1/learning/due'))}
              {resultPanel('Consolidate learning', () => apiClient.post<ApiResult>('/api/v1/learning/consolidate', undefined))}
            </div>
          </CardContent>
        </Card>

        <Card className="border-white/10 bg-slate-900/70">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg"><FlaskConical className="h-5 w-5 text-violet-300" /> Science Engine</CardTitle>
            <CardDescription>Run symbolic and numerical operations through the backend science capability.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-3" onSubmit={submit('Solve science problem', (form) =>
              apiClient.post<ApiResult>('/api/v1/science/solve', {
                operation: String(form.get('operation') ?? 'solve'),
                problem: String(form.get('problem') ?? ''),
                variable: String(form.get('variable') ?? 'x'),
              }))}>
              <select className={formFieldClass} name="operation" defaultValue="solve">
                <option value="solve">Solve equation</option>
                <option value="derivative">Differentiate</option>
                <option value="integral">Integrate</option>
              </select>
              <input className={formFieldClass} name="problem" required placeholder="Example: x^2 - 4 = 0" />
              <input className={formFieldClass} name="variable" defaultValue="x" aria-label="Variable" />
              <Button type="submit" disabled={working}>Compute with JARVIS</Button>
            </form>
          </CardContent>
        </Card>

        <Card className="border-white/10 bg-slate-900/70">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg"><Layers3 className="h-5 w-5 text-amber-300" /> Technology Evolution</CardTitle>
            <CardDescription>Inspect frontier research and the technology radar built from ingested sources.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2">
              {resultPanel('Load technology radar', () => apiClient.get<ApiResult>('/api/v1/tech/radar'))}
              {resultPanel('Explore research frontiers', () => apiClient.get<ApiResult>('/api/v1/tech/frontiers'))}
            </div>
            <form className="flex gap-2 border-t border-white/10 pt-4" onSubmit={submit('Model technology lifecycle', (form) =>
              apiClient.post<ApiResult>('/api/v1/tech/lifecycle', { tech_id: String(form.get('tech_id') ?? '') }))}>
              <input className={formFieldClass} name="tech_id" required placeholder="Technology identifier" />
              <Button type="submit" variant="secondary" disabled={working}>Model lifecycle</Button>
            </form>
          </CardContent>
        </Card>
      </div>

      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-cyan-300" />
          <h2 className="text-xl font-semibold">Live operation results</h2>
          <Sparkles className="h-4 w-4 text-cyan-300" />
        </div>
        {results.length === 0 ? (
          <p className="text-sm text-muted-foreground">Run an operation above to view its actual backend response here.</p>
        ) : (
          <div className="space-y-3">
            {results.map((result, index) => (
              <Card key={`${result.title}-${index}`} className="border-white/10 bg-slate-900/70">
                <CardHeader className="pb-2"><CardTitle className="text-base">{result.title}</CardTitle></CardHeader>
                <CardContent>
                  <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md bg-black/30 p-3 text-xs text-emerald-100">
                    {formatResult(result.value)}
                  </pre>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
