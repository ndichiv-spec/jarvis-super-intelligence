import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockGetDomainStatus } = vi.hoisted(() => ({
  mockGetDomainStatus: vi.fn(),
}));

vi.mock('@/features/search/store', () => ({
  useGlobalSearchStore: () => ({
    query: 'server',
    results: [{
      id: 'runbook-1',
      source: 'knowledge',
      title: 'Operations runbook',
      snippet: 'Internal guidance for service operations.',
      score: 0.92,
      relevance: 0.92,
      metadata: {},
      permissions: {},
    }],
    totalResults: 1,
    isSearching: false,
    error: null,
    domainsSearched: ['knowledge'],
    tookMs: 8,
    setQuery: vi.fn(),
    search: vi.fn(),
    suggest: vi.fn(),
    clear: vi.fn(),
    getDomainStatus: mockGetDomainStatus,
  }),
}));

import { GlobalSearch } from './GlobalSearch';

describe('GlobalSearch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('hands off internal results that have no URL', () => {
    const onNavigate = vi.fn();
    render(<GlobalSearch onNavigate={onNavigate} />);

    fireEvent.focus(screen.getByPlaceholderText('Search across JARVIS...'));
    fireEvent.click(screen.getByText('Operations runbook'));

    expect(onNavigate).toHaveBeenCalledWith(expect.objectContaining({
      id: 'runbook-1',
      source: 'knowledge',
    }));
  });
});
