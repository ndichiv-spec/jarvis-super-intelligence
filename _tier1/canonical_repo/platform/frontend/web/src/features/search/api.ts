/**
 * JARVIS Global Search — API client methods (spec §26–31, §63).
 *
 * Uses the shared ApiClient with auth token handling.
 */
import apiClient from '@/lib/api-client';
import { API_ENDPOINTS } from '@/config/api';
import {
  SearchResponse,
  SearchStatusResponse,
  SearchSuggestion,
  SearchToBrowserResponse,
  SearchToResearchResponse,
  SearchToKnowledgeResponse,
  SearchInspectResponse,
  SearchResult,
} from './types';

export const searchApi = {
  /**
   * Federated global search across all platform domains (spec §26).
   */
  async search(
    query: string,
    domain: string = 'all',
    limit: number = 20,
    includeWeb: boolean = true,
    highlight: boolean = true,
    semantic: boolean = false,
  ): Promise<SearchResponse> {
    return await apiClient.get<SearchResponse>(API_ENDPOINTS.search.global, {
      params: { q: query, domain, limit, include_web: includeWeb, highlight, semantic },
    });
  },

  /** POST variant of search — for structured queries. */
  async searchPost(
    query: string,
    domain: string = 'all',
    limit: number = 20,
    includeWeb: boolean = true,
    highlight: boolean = true,
  ): Promise<SearchResponse> {
    return await apiClient.post<SearchResponse>(API_ENDPOINTS.search.global, {
      query,
      domain,
      limit,
      include_web: includeWeb,
      highlight,
      semantic: false,
    });
  },

  /** List available search domains (spec §26). */
  async listDomains(): Promise<string[]> {
    return await apiClient.get<string[]>(API_ENDPOINTS.search.domains);
  },

  /** Get search suggestions (autocomplete). */
  async suggest(q: string): Promise<SearchSuggestion> {
    return await apiClient.get<SearchSuggestion>(API_ENDPOINTS.search.suggest, {
      params: { q },
    });
  },

  /** Get per-domain search status (spec §18). */
  async getStatus(): Promise<SearchStatusResponse> {
    return await apiClient.get<SearchStatusResponse>(API_ENDPOINTS.search.status);
  },

  /** Cross-system object inspection (spec §17). */
  async inspect(source: string, itemId: string): Promise<SearchInspectResponse> {
    return await apiClient.get<SearchInspectResponse>(API_ENDPOINTS.search.inspect(source, itemId));
  },

  /** Search → Browser handoff (spec §35). */
  async toBrowser(
    query: string,
    sessionId?: string,
    tabId?: string,
    limit?: number,
  ): Promise<SearchToBrowserResponse> {
    return await apiClient.post<SearchToBrowserResponse>(API_ENDPOINTS.search.toBrowser, {
      query,
      session_id: sessionId,
      tab_id: tabId,
      limit: limit || 10,
    });
  },

  /** Search → Research handoff (spec §36). */
  async toResearch(query: string): Promise<SearchToResearchResponse> {
    return await apiClient.post<SearchToResearchResponse>(API_ENDPOINTS.search.toResearch, {
      query,
    });
  },

  /** Search → Knowledge handoff (spec §37). */
  async toKnowledge(
    query: string,
    resultId?: string,
  ): Promise<SearchToKnowledgeResponse> {
    return await apiClient.post<SearchToKnowledgeResponse>(API_ENDPOINTS.search.toKnowledge, {
      query,
      result_id: resultId,
    });
  },

  /** Classify navigation context for a URL (spec §7). */
  async classifyNavigationContext(url: string, headers?: Record<string, string>) {
    return await apiClient.post(API_ENDPOINTS.browser.navigateContext, {
      url,
      headers,
    });
  },

  /** Classify a navigation failure (spec §8). */
  async classifyNavigationFailure(params: {
    url: string;
    error_category?: string;
    status_code?: number;
    headers?: Record<string, string>;
    error_detail?: string;
  }) {
    return await apiClient.post(API_ENDPOINTS.browser.classifyFailure, params);
  },

  /** Generate 'Open in Browser Context' target (spec §8). */
  async openInBrowserContext(
    url: string,
    presentation?: string,
    query?: string,
  ) {
    return await apiClient.post(API_ENDPOINTS.browser.openContext, {
      url,
      presentation,
      query,
    });
  },

  /** Enhanced page understanding (spec §5). */
  async understandPage(url: string) {
    return await apiClient.post(API_ENDPOINTS.browser.pageUnderstand, { url });
  },

  /** Get browser profile configuration (spec §12). */
  async getBrowserProfiles() {
    return await apiClient.get(API_ENDPOINTS.browser.profiles);
  },

  async getBrowserProfile(name: string) {
    return await apiClient.get(API_ENDPOINTS.browser.profilesByName(name));
  },

  /** Get browser engine info (spec §4). */
  async getBrowserEngine() {
    return await apiClient.get(API_ENDPOINTS.browser.engine);
  },
};

export default searchApi;
