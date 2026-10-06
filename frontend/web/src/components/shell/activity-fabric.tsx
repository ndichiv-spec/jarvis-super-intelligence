'use client';

import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Activity, Shield, Brain, Bot, Cloud, Database, GitBranch,
  Key, Lock, Search, Settings, Terminal, Timer,
  Users, Workflow, Zap, CheckCircle, XCircle, AlertCircle,
  Clock, Filter, X,
} from 'lucide-react';
import { useActivity } from '@/stores/platform-store';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { severityToColorClass } from '@/lib/design-system';
import type { ActivityEvent, SeverityLevel } from '@/lib/types/platform';

const DOMAIN_ICONS: Record<string, React.ElementType> = {
  agent: Bot,
  tool: Workflow,
  model: Brain,
  provider: Cloud,
  security: Shield,
  training: Zap,
  learning: GitBranch,
  mission: Workflow,
  research: Search,
  system: Terminal,
  chat: Activity,
};

const SEVERITY_ORDER: Record<SeverityLevel, number> = {
  info: 0, low: 1, medium: 2, high: 3, critical: 4,
};

const SEVERITY_FILTERS: Array<{ value: string; label: string }> = [
  { value: 'all', label: 'All Events' },
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium/Low' },
  { value: 'info', label: 'Info' },
];

const DOMAIN_FILTERS: Array<{ value: string; label: string }> = [
  { value: 'all', label: 'All Domains' },
  { value: 'agent', label: 'Agents' },
  { value: 'security', label: 'Security' },
  { value: 'training', label: 'Training' },
  { value: 'system', label: 'System' },
  { value: 'model', label: 'Models' },
  { value: 'provider', label: 'Providers' },
];

interface ActivityFabricProps {
  maxItems?: number;
  compact?: boolean;
  showFilters?: boolean;
}

export function ActivityFabric({ maxItems = 50, compact = false, showFilters = true }: ActivityFabricProps) {
  const activity = useActivity();
  const [severityFilter, setSeverityFilter] = useState('all');
  const [domainFilter, setDomainFilter] = useState('all');

  const filtered = useMemo(() => {
    const items = (activity || []).slice(0, maxItems);
    return items.filter((event: ActivityEvent) => {
      if (severityFilter !== 'all') {
        if (severityFilter === 'critical' && event.severity !== 'critical') return false;
        if (severityFilter === 'high' && event.severity !== 'high' && event.severity !== 'critical') return false;
        if (severityFilter === 'medium' && (event.severity !== 'medium' && event.severity !== 'low')) return false;
        if (severityFilter === 'info' && event.severity !== 'info') return false;
      }
      if (domainFilter !== 'all' && event.domain !== domainFilter) return false;
      return true;
    });
  }, [activity, severityFilter, domainFilter, maxItems]);

  const now = Date.now();
  const timeLabel = (ts: number): string => {
    const diff = now - ts;
    if (diff < 60000) return `${Math.floor(diff / 1000)}s ago`;
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="flex h-full flex-col">
      {showFilters && (
        <div className="flex items-center gap-2 p-3 border-b border-white/5">
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="text-xs bg-[hsl(222,47%,8%)] border border-white/10 rounded-lg px-2 py-1 text-muted-foreground/70 focus:outline-none focus:border-blue-500/50"
          >
            {SEVERITY_FILTERS.map((f) => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
          <select
            value={domainFilter}
            onChange={(e) => setDomainFilter(e.target.value)}
            className="text-xs bg-[hsl(222,47%,8%)] border border-white/10 rounded-lg px-2 py-1 text-muted-foreground/70 focus:outline-none focus:border-blue-500/50"
          >
            {DOMAIN_FILTERS.map((f) => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
          <div className="ml-auto text-[10px] text-muted-foreground/40">
            {filtered.length} {filtered.length === 1 ? 'event' : 'events'}
          </div>
        </div>
      )}

      <ScrollArea className="flex-1 px-2">
        <AnimatePresence>
          {filtered.length === 0 ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col items-center justify-center h-32 text-muted-foreground/40"
            >
              <Clock className="h-6 w-6 mb-2" />
              <span className="text-xs">No activity events</span>
            </motion.div>
          ) : (
            filtered.map((event: ActivityEvent) => {
              const Icon = DOMAIN_ICONS[event.domain] || Activity;
              const colorClass = severityToColorClass(event.severity);
              return (
                <motion.div
                  key={event.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }}
                  className={`mb-1 rounded-lg px-3 py-2.5 transition-colors ${
                    compact ? 'text-xs' : 'text-sm'
                  } hover:bg-white/[0.03]`}
                >
                  <div className="flex items-start gap-3">
                    <div className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500/10 to-cyan-500/10 border border-white/5`}>
                      <Icon className={`h-3 w-3 ${colorClass}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-foreground">{event.title}</span>
                        <Badge
                          variant="outline"
                          className={`text-[9px] font-medium border-0 ${colorClass}`}
                        >
                          {event.domain}
                        </Badge>
                      </div>
                      {event.detail && (
                        <p className="mt-0.5 text-xs text-muted-foreground/60 line-clamp-2">
                          {event.detail}
                        </p>
                      )}
                      <div className="mt-1 flex items-center gap-3 text-[10px] text-muted-foreground/40">
                        <span>{timeLabel(event.timestamp)}</span>
                        {event.user && <span>by {event.user}</span>}
                        {event.resourceId && <span>#{event.resourceId.slice(0, 8)}</span>}
                      </div>
                    </div>
                  </div>
                </motion.div>
              );
            })
          )}
        </AnimatePresence>
      </ScrollArea>
    </div>
  );
}
