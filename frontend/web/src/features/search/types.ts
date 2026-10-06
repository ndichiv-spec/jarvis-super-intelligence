/**
 * JARVIS Global Search — type definitions (spec §26–31, §63).
 *
 * These types mirror the backend search router models.
 */

/** Searchable platform domains (spec §63). */
export type SearchDomain =
  | 'knowledge'
  | 'memory'
  | 'chat'
  | 'agents'
  | 'tasks'
  | 'browser'
  | 'notes'
  | 'reminders'
  | 'research'
  | 'missions'
  | 'evidence'
  | 'all';

/** Normalised search result from any domain (spec §27). */
export interface SearchResult {
  id: string;
  source: string;          // which domain the result came from
  title: string;
  snippet: string;
  url?: string;
  route?: string;
  type?: string;
  domain?: string;
  score: number;
  relevance: number;       // 0.0 – 1.0
  metadata: Record<string, any>;
  timestamp?: string;
  permissions: Record<string, any>;
}

/** Federated search response (spec §27). */
export interface SearchResponse {
  query: string;
  total_results: number;
  results: SearchResult[];
  domains_searched: string[];
  took_ms: number;
  highlights: Record<string, string[]>;
}

/** Search status per domain (spec §18). */
export interface SearchDomainStatus {
  available: boolean;
  item_count: number;
  include_web?: boolean;
  error?: string;
  reason?: string;
}

export interface SearchStatusResponse {
  domains: Record<string, SearchDomainStatus>;
  healthy: boolean;
}

export interface SearchSuggestion {
  query: string;
  suggestions: string[];
}

/** Search → Browser handoff response (spec §35). */
export interface SearchToBrowserResponse {
  query: string;
  navigated: boolean;
  target_url: string;
  navigation_context: {
    presentation: string;
    reason: string;
    confidence: number;
  };
  session_id: string;
  tab_id?: string;
  result?: SearchResult;
  reason?: string;
}

/** Search → Research handoff response (spec §36). */
export interface SearchToResearchResponse {
  research_session_id: string;
  query: string;
  seeded_results: number;
  took_ms: number;
  results: SearchResult[];
}

/** Search → Knowledge handoff response (spec §37). */
export interface SearchToKnowledgeResponse {
  promoted: boolean;
  knowledge_key?: string;
  entry?: Record<string, any>;
  reason?: string;
}

/** Search → platform inspect response (spec §17). */
export interface SearchInspectResponse {
  source: string;
  id: string;
  object: Record<string, any>;
}

/** Global search store state. */
export interface GlobalSearchState {
  query: string;
  results: SearchResult[];
  totalResults: number;
  isSearching: boolean;
  error: string | null;
  domains: string[];
  domainsSearched: string[];
  tookMs: number;
  highlights: Record<string, string[]>;
  suggestions: string[];
  isSuggesting: boolean;
  domainStatus: Record<string, SearchDomainStatus>;
  lastResponse: SearchResponse | null;
}

/** Global search store interface (methods). */
export interface GlobalSearchStore extends GlobalSearchState {
  setQuery: (query: string) => void;
  search: (params: {
    query: string;
    domain?: string;
    limit?: number;
    includeWeb?: boolean;
  }) => Promise<void>;
  suggest: (partial: string) => Promise<void>;
  getDomainStatus: () => Promise<void>;
  inspect: (source: string, itemId: string) => Promise<any>;
  toBrowser: (params: {
    query: string;
    sessionId?: string;
    tabId?: string;
    limit?: number;
  }) => Promise<SearchToBrowserResponse>;
  toResearch: (query: string) => Promise<SearchToResearchResponse>;
  toKnowledge: (params: { query: string; resultId?: string }) => Promise<SearchToKnowledgeResponse>;
  clear: () => void;
  clearError: () => void;
}
