'use client';

import { useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Search, BookOpen, Brain, Library, Bot, BarChart3, Loader2 } from 'lucide-react';
import apiClient from '@/lib/api-client';
import API_ENDPOINTS from '@/config/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useRouter } from 'next/navigation';
import { usePlatformStore } from '@/stores/platform-store';
import type { InspectorObject } from '@/components/shell/universal-inspector';

interface SearchResult {
  id: string;
  title: string;
  snippet: string;
  type: 'knowledge' | 'agent' | 'memory' | 'model' | 'provider';
  url?: string;
}

export default function GlobalSearchPage() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [inspectorObject, setInspectorObject] = useState<InspectorObject | null>(null);
  const router = useRouter();
  const addActivity = usePlatformStore((s) => s.addActivity);

  const handleSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResults([]);
      return;
    }
    setIsSearching(true);
    const allResults: SearchResult[] = [];

    try {
      // 1. Knowledge search (global)
      const knowledgeRes = await apiClient.get(`${API_ENDPOINTS.knowledge.search}?q=${encodeURIComponent(q)}`).catch(() => []);
      if (Array.isArray(knowledgeRes)) {
        knowledgeRes.forEach((item: any, idx: number) => {
          allResults.push({
            id: `kw-${idx}`,
            title: item.title || item.source || 'Knowledge Entry',
            snippet: item.snippet || item.content?.substring(0, 200) || '',
            type: 'knowledge',
            url: '/dashboard/knowledge',
          });
        });
      }
    } catch { /* best-effort */ }

    try {
      // 2. Global knowledge search (from global_knowledge router)
      const globalRes = await apiClient.get(`${API_ENDPOINTS.global.knowledgeSearch}?query=${encodeURIComponent(q)}`).catch(() => []);
      if (Array.isArray(globalRes)) {
        globalRes.forEach((item: any, idx: number) => {
          allResults.push({
            id: `gk-${idx}`,
            title: item.title || item.source || 'Global Knowledge',
            snippet: item.snippet || item.description || '',
            type: 'knowledge',
            url: '/dashboard/knowledge',
          });
        });
      }
    } catch { /* best-effort */ }

    try {
      // 3. Agents search
      const agentsRes = await apiClient.get(`${API_ENDPOINTS.agents.list}?q=${encodeURIComponent(q)}`).catch(() => []);
      if (Array.isArray(agentsRes)) {
        agentsRes.forEach((item: any, idx: number) => {
          allResults.push({
            id: `ag-${idx}`,
            title: item.name || item.agent_name || 'Agent',
            snippet: item.description || item.role || '',
            type: 'agent',
            url: '/dashboard/agents',
          });
        });
      }
    } catch { /* best-effort */ }

    try {
      // 4. Memory recall search
      const memRes = await apiClient.get(`${API_ENDPOINTS.memory.knowledgeGraph}?q=${encodeURIComponent(q)}`).catch(() => []);
      if (Array.isArray(memRes)) {
        memRes.forEach((item: any, idx: number) => {
          allResults.push({
            id: `mem-${idx}`,
            title: item.title || item.key || 'Memory',
            snippet: item.snippet || item.content?.substring(0, 200) || '',
            type: 'memory',
            url: '/dashboard/memory',
          });
        });
      }
    } catch { /* best-effort */ }

    setResults(allResults);
    setIsSearching(false);

    if (allResults.length > 0) {
      addActivity({
        domain: 'system',
        operation: 'search',
        title: 'Global search performed',
        detail: `"${q}" → ${allResults.length} results across ${new Set(allResults.map(r => r.type)).size} domains`,
        severity: 'info',
      });
    }
  }, [addActivity]);

  const getTypeIcon = (type: SearchResult['type']) => {
    switch (type) {
      case 'knowledge': return <BookOpen className="h-4 w-4 text-blue-400" />;
      case 'agent': return <Bot className="h-4 w-4 text-purple-400" />;
      case 'memory': return <Library className="h-4 w-4 text-emerald-400" />;
      case 'model': return <Brain className="h-4 w-4 text-amber-400" />;
      case 'provider': return <BarChart3 className="h-4 w-4 text-cyan-400" />;
    }
  };

  const getTypeBadge = (type: SearchResult['type']) => {
    const variants = {
      knowledge: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
      agent: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
      memory: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
      model: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
      provider: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
    };
    return <Badge variant="outline" className={`text-[10px] ${variants[type]}`}>{type}</Badge>;
  };

  const handleResultClick = (result: SearchResult) => {
    if (result.url) {
      router.push(result.url);
    }
  };

  return (
    <div className="flex-1 space-y-6 p-6 pt-6 h-[calc(100vh-4rem)]">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
          <Search className="h-8 w-8 text-blue-500" />
          Global Search
        </h1>
        <p className="text-muted-foreground mt-1">Search across Knowledge, Agents, Memory, Models, and Providers</p>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
        <div className="flex gap-2">
          <Input
            type="search"
            placeholder="Type to search across JARVIS..."
            value={query}
            onChange={(e) => { setQuery(e.target.value); handleSearch(e.target.value); }}
            className="flex-1 bg-white/[0.02] border-white/5 focus:border-blue-500/30"
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleSearch(query)}
            disabled={isSearching || !query.trim()}
          >
            {isSearching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          </Button>
        </div>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
        {results.length === 0 && !isSearching && query && (
          <Card>
            <CardContent className="pt-6 text-center">
              <Search className="h-12 w-12 mx-auto mb-3 text-muted-foreground/30" />
              <p className="text-muted-foreground">No results found for "{query}"</p>
            </CardContent>
          </Card>
        )}

        {results.length === 0 && !isSearching && !query && (
          <Card>
            <CardContent className="pt-6 text-center">
              <Search className="h-12 w-12 mx-auto mb-3 text-muted-foreground/30" />
              <p className="text-muted-foreground">Enter a search term to begin</p>
            </CardContent>
          </Card>
        )}

        {results.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm flex items-center justify-between">
                <span>{results.length} results for "{query}"</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="divide-y divide-white/5">
                {results.map((result) => (
                  <motion.div
                    key={result.id}
                    whileHover={{ backgroundColor: 'rgba(255,255,255,0.02)' }}
                    className="p-4 cursor-pointer transition-colors"
                    onClick={() => handleResultClick(result)}
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5">{getTypeIcon(result.type)}</div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-medium text-sm">{result.title}</span>
                          {getTypeBadge(result.type)}
                        </div>
                        <p className="text-xs text-muted-foreground/60 line-clamp-2">{result.snippet}</p>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </motion.div>
    </div>
  );
}
