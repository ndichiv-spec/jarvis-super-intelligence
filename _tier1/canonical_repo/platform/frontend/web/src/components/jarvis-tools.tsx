'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { motion } from 'framer-motion';
import {
  AlertCircle,
  ArrowUpRight,
  Boxes,
  Loader2,
  RefreshCw,
  Search,
  Wrench,
} from 'lucide-react';
import type { ResourceStatus } from '@/lib/types/platform';
import type { RuntimeCapability } from '@/lib/types/runtime';
import { usePlatformStore } from '@/stores/platform-store';

function availabilityClasses(value: string): string {
  const normalized = value.toUpperCase();
  if (normalized === 'AVAILABLE') {
    return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200';
  }
  if (normalized === 'UNAVAILABLE' || normalized === 'BLOCKED' || normalized === 'DENIED') {
    return 'border-rose-400/30 bg-rose-500/10 text-rose-200';
  }
  if (normalized === 'DEGRADED' || normalized === 'CONFIGURED' || normalized === 'PARTIAL') {
    return 'border-amber-400/30 bg-amber-500/10 text-amber-100';
  }
  return 'border-slate-600 bg-slate-800/80 text-slate-200';
}

function registryStatusCopy(status: ResourceStatus): string {
  switch (status) {
    case 'idle':
      return 'Waiting for the runtime registry to report in…';
    case 'loading':
      return 'Loading capability registry from the backend…';
    case 'unauthorized':
      return 'This session is not authorized to view the owner-scoped registry.';
    case 'offline':
      return 'The runtime registry is currently unreachable. Check backend health and retry.';
    case 'failed':
      return 'The capability registry request failed. Try refreshing or verify the backend connection.';
    case 'degraded':
      return 'The capability registry is degraded and may be incomplete.';
    case 'rate_limited':
      return 'The runtime registry is rate-limited. Please retry in a moment.';
    case 'cancelled':
      return 'The capability registry request was cancelled.';
    default:
      return 'Runtime registry status is being refreshed…';
  }
}

function deriveDescription(capability: RuntimeCapability): string {
  const record = capability as RuntimeCapability & Record<string, unknown>;
  const description = typeof record.description === 'string'
    ? record.description
    : typeof record.summary === 'string'
      ? record.summary
      : '';

  if (description) return description;
  return typeof capability.availability_reason === 'string' && capability.availability_reason.trim().length > 0
    ? capability.availability_reason
    : 'No additional capability description was reported by the backend.';
}

export default function JarvisTools() {
  const capabilities = usePlatformStore((state) => state.commandCapabilities);
  const capabilityAvailability = usePlatformStore((state) => state.commandCapabilitiesAvailability);
  const refreshCommands = usePlatformStore((state) => state.refreshCommands);

  const [searchTerm, setSearchTerm] = useState('');
  const [availabilityFilter, setAvailabilityFilter] = useState<'all' | string>('all');
  const [domainFilter, setDomainFilter] = useState<'all' | string>('all');
  const [riskFilter, setRiskFilter] = useState<'all' | string>('all');

  useEffect(() => {
    void refreshCommands();
  }, [refreshCommands]);

  const availabilityOptions = useMemo(
    () => Array.from(new Set(capabilities.map((capability) => capability.availability).filter(Boolean))).sort(),
    [capabilities],
  );
  const domainOptions = useMemo(
    () => Array.from(new Set(capabilities.map((capability) => capability.domain).filter(Boolean))).sort(),
    [capabilities],
  );
  const riskOptions = useMemo(
    () => Array.from(new Set(capabilities.map((capability) => capability.risk_level).filter(Boolean))).sort(),
    [capabilities],
  );

  const filteredCapabilities = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();

    return capabilities.filter((capability) => {
      const record = capability as RuntimeCapability & Record<string, unknown>;
      const identifier = typeof record.identifier === 'string' ? record.identifier : capability.id;
      const description = deriveDescription(capability);
      const searchable = [
        capability.id,
        identifier,
        capability.name,
        capability.domain,
        capability.availability,
        capability.risk_level,
        capability.availability_reason ?? '',
        description,
      ].join(' ').toLowerCase();

      const matchesQuery = query.length === 0 || searchable.includes(query);
      const matchesAvailability = availabilityFilter === 'all' || capability.availability === availabilityFilter;
      const matchesDomain = domainFilter === 'all' || capability.domain === domainFilter;
      const matchesRisk = riskFilter === 'all' || capability.risk_level === riskFilter;

      return matchesQuery && matchesAvailability && matchesDomain && matchesRisk;
    });
  }, [availabilityFilter, capabilities, domainFilter, riskFilter, searchTerm]);

  const totals = useMemo(() => {
    const all = capabilities.length;
    const available = capabilities.filter((capability) => capability.availability === 'AVAILABLE').length;
    const unavailable = capabilities.filter((capability) => ['UNAVAILABLE', 'BLOCKED', 'DENIED'].includes(capability.availability.toUpperCase())).length;
    const domains = new Set(capabilities.map((capability) => capability.domain).filter(Boolean)).size;
    return { all, available, unavailable, domains };
  }, [capabilities]);

  const loading = capabilityAvailability === 'idle' || capabilityAvailability === 'loading';
  const failure = ['offline', 'failed', 'degraded', 'rate_limited', 'cancelled', 'unauthorized'].includes(capabilityAvailability);

  return (
    <section className="rounded-2xl border border-white/10 bg-slate-950/70 shadow-2xl shadow-cyan-950/10">
      <div className="flex flex-col gap-4 border-b border-white/10 px-4 py-4 md:px-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-cyan-400/20 bg-cyan-500/10 text-cyan-200">
              <Wrench className="h-5 w-5" />
            </div>
            <div>
              <p className="text-[10px] font-medium uppercase tracking-[0.24em] text-cyan-300/80">Runtime inventory</p>
              <h2 className="mt-1 text-xl font-semibold text-white">Capability explorer</h2>
            </div>
          </div>

          <button
            type="button"
            aria-label="Refresh capability registry"
            onClick={() => void refreshCommands()}
            className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-slate-900/80 px-3 py-2 text-xs font-medium text-slate-200 transition-colors hover:border-cyan-400/30 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
          >
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Refresh
          </button>
        </div>

        <p className="text-sm leading-relaxed text-slate-400">
          Live registry data from the backend. Sensitive actions remain authorization-gated and are routed through the supervised command center.
        </p>
      </div>

      <div className="grid gap-3 p-4 md:grid-cols-4">
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
          <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Registered</p>
          <p className="mt-2 text-2xl font-semibold text-white">{totals.all}</p>
        </div>
        <div className="rounded-xl border border-emerald-400/20 bg-emerald-500/5 p-3">
          <p className="text-[10px] uppercase tracking-[0.2em] text-emerald-200/70">Available</p>
          <p className="mt-2 text-2xl font-semibold text-emerald-100">{totals.available}</p>
        </div>
        <div className="rounded-xl border border-rose-400/20 bg-rose-500/5 p-3">
          <p className="text-[10px] uppercase tracking-[0.2em] text-rose-200/70">Unavailable</p>
          <p className="mt-2 text-2xl font-semibold text-rose-100">{totals.unavailable}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
          <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Domains</p>
          <p className="mt-2 text-2xl font-semibold text-white">{totals.domains}</p>
        </div>
      </div>

      <div className="space-y-4 p-4 pt-0">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.7fr)]">
          <div className="min-w-0">
            <label htmlFor="capability-search" className="mb-1.5 block text-xs font-medium text-slate-300">
              Search capabilities
            </label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
              <input
                id="capability-search"
                aria-label="Search runtime capabilities"
                type="text"
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Search name, domain, description, id, or reason…"
                className="w-full rounded-xl border border-white/10 bg-slate-900/80 py-2.5 pl-10 pr-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-400/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
              />
            </div>
          </div>

          <fieldset className="min-w-0">
            <legend className="mb-1.5 text-xs font-medium text-slate-300">Filter by registry fields</legend>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <label className="min-w-0">
                <span className="mb-1.5 block text-xs text-slate-400">Availability</span>
                <select
                  aria-label="Filter capabilities by availability"
                  value={availabilityFilter}
                  onChange={(event) => setAvailabilityFilter(event.target.value)}
                  className="w-full min-w-0 rounded-xl border border-white/10 bg-slate-900/80 px-3 py-2.5 text-sm text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
                >
                  <option value="all">All availability</option>
                  {availabilityOptions.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </label>

              <label className="min-w-0">
                <span className="mb-1.5 block text-xs text-slate-400">Domain</span>
                <select
                  aria-label="Filter capabilities by domain"
                  value={domainFilter}
                  onChange={(event) => setDomainFilter(event.target.value)}
                  className="w-full min-w-0 rounded-xl border border-white/10 bg-slate-900/80 px-3 py-2.5 text-sm text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
                >
                  <option value="all">All domains</option>
                  {domainOptions.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </label>

              <label className="min-w-0">
                <span className="mb-1.5 block text-xs text-slate-400">Risk level</span>
                <select
                  aria-label="Filter capabilities by risk"
                  value={riskFilter}
                  onChange={(event) => setRiskFilter(event.target.value)}
                  className="w-full min-w-0 rounded-xl border border-white/10 bg-slate-900/80 px-3 py-2.5 text-sm text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
                >
                  <option value="all">All risk levels</option>
                  {riskOptions.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </label>
            </div>
          </fieldset>
        </div>

        {loading && (
          <div className="rounded-xl border border-dashed border-cyan-400/20 bg-cyan-500/5 p-6 text-center" role="status">
            <Loader2 className="mx-auto h-5 w-5 animate-spin text-cyan-200" />
            <p className="mt-3 text-sm text-cyan-100">{registryStatusCopy(capabilityAvailability)}</p>
          </div>
        )}

        {failure && !loading && (
          <div className="rounded-xl border border-rose-400/20 bg-rose-500/5 p-5" role="alert">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 text-rose-200" />
              <div>
                <p className="text-sm font-medium text-rose-100">Capability registry unavailable</p>
                <p className="mt-1 text-sm text-rose-100/80">{registryStatusCopy(capabilityAvailability)}</p>
              </div>
            </div>
          </div>
        )}

        {!loading && !failure && filteredCapabilities.length === 0 && capabilities.length === 0 && (
          <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-6 text-center" role="status">
            <Boxes className="mx-auto h-5 w-5 text-slate-500" />
            <p className="mt-3 text-sm font-medium text-slate-200">No capabilities registered</p>
            <p className="mt-1 text-sm text-slate-400">The backend returned an empty capability registry for this session.</p>
          </div>
        )}

        {!loading && !failure && filteredCapabilities.length === 0 && capabilities.length > 0 && (
          <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-6 text-center" role="status">
            <Search className="mx-auto h-5 w-5 text-slate-500" />
            <p className="mt-3 text-sm font-medium text-slate-200">No matching capabilities</p>
            <p className="mt-1 text-sm text-slate-400">Try clearing filters or broadening the search term.</p>
          </div>
        )}

        {!loading && !failure && filteredCapabilities.length > 0 && (
          <div className="space-y-3">
            {filteredCapabilities.map((capability) => {
              const description = deriveDescription(capability);

              return (
                <motion.article
                  key={capability.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="rounded-xl border border-white/10 bg-slate-900/70 p-4"
                >
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="truncate text-base font-semibold text-white">{capability.name}</h3>
                        <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.14em] ${availabilityClasses(capability.availability)}`}>
                          {capability.availability}
                        </span>
                      </div>

                      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                        <span>{capability.domain}</span>
                        <span aria-hidden="true" className="text-slate-600">•</span>
                        <span>ID: {capability.id}</span>
                        <span aria-hidden="true" className="text-slate-600">•</span>
                        <span>Risk: {capability.risk_level}</span>
                      </div>
                    </div>

                  </div>

                  <p className="mt-3 text-sm leading-relaxed text-slate-300">{description}</p>

                  {capability.availability_reason && (
                    <p className="mt-2 rounded-lg border border-white/10 bg-black/10 px-3 py-2 text-xs leading-relaxed text-slate-400">
                      Availability reason: {capability.availability_reason}
                    </p>
                  )}

                  <div className="mt-4 flex flex-wrap gap-2">
                    <Link
                      href="/dashboard/commands"
                      className="inline-flex items-center gap-2 rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-3 py-2 text-xs font-medium text-cyan-100 transition-colors hover:border-cyan-300/60 hover:bg-cyan-500/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
                    >
                      Open command center
                      <ArrowUpRight className="h-3.5 w-3.5" />
                    </Link>
                    <Link
                      href="/dashboard/developer/capabilities"
                      className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-slate-800/80 px-3 py-2 text-xs font-medium text-slate-200 transition-colors hover:border-white/20 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
                    >
                      Review permissions
                    </Link>
                  </div>
                </motion.article>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
