'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Library, Search, Layers, Brain, RefreshCw, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useMemoryStore } from '@/features/memory/store';

const LAYER_COLORS: Record<string, string> = {
  short_term: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  long_term: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  working: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  episodic: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
};

export function MemoryInspector() {
  const { entries, stats, recall, loadStats, consolidate } = useMemoryStore();
  const [query, setQuery] = useState('');

  useEffect(() => {
    recall();
    loadStats();
  }, [recall, loadStats]);

  const handleSearch = () => {
    recall(query || undefined);
  };

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="border-white/10 bg-white/[0.03]">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10">
                <Library className="h-5 w-5 text-blue-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{stats?.total_entries || 0}</p>
                <p className="text-xs text-muted-foreground/50">Total Memories</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-white/10 bg-white/[0.03]">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10">
                <Layers className="h-5 w-5 text-amber-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{stats?.short_term_count || 0}</p>
                <p className="text-xs text-muted-foreground/50">Short-term</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-white/10 bg-white/[0.03]">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10">
                <Brain className="h-5 w-5 text-emerald-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{stats?.long_term_count || 0}</p>
                <p className="text-xs text-muted-foreground/50">Long-term</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-white/10 bg-white/[0.03]">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-500/10">
                <RefreshCw className="h-5 w-5 text-purple-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{stats?.avg_importance?.toFixed(1) || '0'}</p>
                <p className="text-xs text-muted-foreground/50">Avg Importance</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Search & Consolidate */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/40" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search memories..."
            className="border-white/10 bg-white/[0.02] pl-9 text-sm"
          />
        </div>
        <Button
          variant="outline"
          size="sm"
          className="border-white/10"
          onClick={handleSearch}
        >
          <Search className="mr-2 h-4 w-4" />
          Search
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="border-white/10"
          onClick={() => consolidate()}
        >
          <RefreshCw className="mr-2 h-4 w-4" />
          Consolidate
        </Button>
      </div>

      {/* Memory Entries */}
      <Card className="border-white/10 bg-white/[0.03]">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <Library className="h-4 w-4 text-cyan-400" />
            Memory Entries
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[400px]">
            <div className="space-y-2">
              {entries.map((entry) => (
                <motion.div
                  key={entry.id}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="rounded-lg border border-white/5 bg-white/[0.01] p-3"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <p className="text-sm text-foreground/80">{entry.content}</p>
                      <div className="mt-2 flex items-center gap-2">
                        <Badge className={`text-[9px] ${LAYER_COLORS[entry.layer] || 'bg-gray-500/10 text-gray-400'}`}>
                          {entry.layer}
                        </Badge>
                        <span className="text-[10px] text-muted-foreground/40">
                          Importance: {entry.importance?.toFixed(1) || 'N/A'}
                        </span>
                        <span className="text-[10px] text-muted-foreground/40">
                          {new Date(entry.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))}
              {entries.length === 0 && (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <Library className="mb-2 h-8 w-8 text-muted-foreground/20" />
                  <p className="text-sm text-muted-foreground/40">No memory entries found</p>
                </div>
              )}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
