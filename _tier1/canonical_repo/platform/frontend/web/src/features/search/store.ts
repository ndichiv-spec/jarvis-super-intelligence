/**
 * JARVIS Global Search — Zustand store (spec §26–31, §63).
 *
 * Federated search across all platform domains.  Results are normalised
 * into a common schema with a ``source`` field so the frontend can group
 * by domain without duplicating search logic per subsystem.
 */
import { create } from 'zustand';
import type {
  SearchResult,
  SearchResponse,
  SearchDomainStatus,
  SearchSuggestion,
  SearchToBrowserResponse,
  SearchToResearchResponse,
  SearchToKnowledgeResponse,
  SearchInspectResponse,
  GlobalSearchState,
  GlobalSearchStore,
} from './types';
import searchApi from './api';
import { usePlatformStore } from '@/stores/platform-store';

export const useGlobalSearchStore = create<GlobalSearchStore>()(
  (set, get) => ({
    query: '',
    results: [],
    totalResults: 0,
    isSearching: false,
    error: null,
    domains: [],
    domainsSearched: [],
    tookMs: 0,
    highlights: {},
    suggestions: [],
    isSuggesting: false,
    domainStatus: {},
    lastResponse: null,

    setQuery: (query: string) => set({ query }),

    search: async (params) => {
      const { query, domain = 'all', limit = 20, includeWeb = true } = params;
      set({ isSearching: true, error: null, query });
      const start = Date.now();
      try {
        // Use POST for structured search (handles longer queries)
        const resp = await searchApi.searchPost(query, domain, limit, includeWeb);
        const tookMs = Date.now() - start;
        set({
          results: resp.results,
          totalResults: resp.total_results,
          domainsSearched: resp.domains_searched,
          tookMs,
          highlights: resp.highlights,
          lastResponse: resp,
          isSearching: false,
        });

        usePlatformStore.getState().addActivity({
          domain: 'system',
          operation: 'federated_search',
          title: `Global search: "${query}"`,
          detail: `${resp.total_results} results across ${resp.domains_searched.length} domains in ${tookMs}ms`,
          severity: 'info',
        });
      } catch (e) {
        set({
          error: e instanceof Error ? e.message : 'Search failed',
          isSearching: false,
        });
        usePlatformStore.getState().addActivity({
          domain: 'system',
          operation: 'federated_search_error',
          title: 'Global search failed',
          detail: e instanceof Error ? e.message : 'Unknown error',
          severity: 'medium',
        });
      }
    },

    suggest: async (partial: string) => {
      if (!partial.trim()) {
        set({ suggestions: [] });
        return;
      }
      set({ isSuggesting: true });
      try {
        const resp = await searchApi.suggest(partial);
        set({ suggestions: resp.suggestions, isSuggesting: false });
      } catch {
        set({ isSuggesting: false, suggestions: [] });
      }
    },

    getDomainStatus: async () => {
      try {
        const resp = await searchApi.getStatus();
        set({ domainStatus: resp.domains });
      } catch (e) {
        set({ domainStatus: {} });
      }
    },

    inspect: async (source: string, itemId: string): Promise<SearchInspectResponse> => {
      return await searchApi.inspect(source, itemId);
    },

    toBrowser: async (params): Promise<SearchToBrowserResponse> => {
      const resp = await searchApi.toBrowser(
        params.query,
        params.sessionId,
        params.tabId,
        params.limit,
      );
      usePlatformStore.getState().addActivity({
        domain: 'browser',
        operation: 'search_handoff',
        title: 'Search → Browser',
        detail: resp.navigated
          ? `Navigated to ${resp.target_url}`
          : resp.reason || 'No navigable results',
        severity: resp.navigated ? 'info' : 'medium',
      });
      return resp;
    },

    toResearch: async (query: string): Promise<SearchToResearchResponse> => {
      const resp = await searchApi.toResearch(query);
      usePlatformStore.getState().addActivity({
        domain: 'research',
        operation: 'search_handoff',
        title: 'Search → Research',
        detail: `Created research session with ${resp.seeded_results} seeded results`,
        severity: 'info',
      });
      return resp;
    },

    toKnowledge: async (params): Promise<SearchToKnowledgeResponse> => {
      const resp = await searchApi.toKnowledge(params.query, params.resultId);
      if (resp.promoted) {
        usePlatformStore.getState().addActivity({
          domain: 'system',
          operation: 'search_handoff',
          title: 'Search → Knowledge',
          detail: `Promoted result to knowledge entry: ${resp.knowledge_key}`,
          severity: 'info',
        });
      }
      return resp;
    },

    clear: () => set({
      query: '',
      results: [],
      totalResults: 0,
      error: null,
      domainsSearched: [],
      tookMs: 0,
      highlights: {},
      lastResponse: null,
    }),

    clearError: () => set({ error: null }),
  }),
);
