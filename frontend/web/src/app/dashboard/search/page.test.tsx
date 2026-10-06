import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const { mockSearch, mockListDomains, mockGetStatus, mockToKnowledge } = vi.hoisted(() => ({
  mockSearch: vi.fn(),
  mockListDomains: vi.fn(),
  mockGetStatus: vi.fn(),
  mockToKnowledge: vi.fn(),
}));

vi.mock('@/features/search/api', () => ({
  searchApi: {
    search: mockSearch,
    listDomains: mockListDomains,
    getStatus: mockGetStatus,
    toKnowledge: mockToKnowledge,
    toResearch: vi.fn(),
  },
}));

import GlobalSearchPage from './page';

function searchResponse(results: Array<Record<string, unknown>>) {
  return {
    query: 'engine health',
    total_results: results.length,
    results,
    domains_searched: ['knowledge', 'memory'],
    took_ms: 14,
    highlights: {},
  };
}

describe('GlobalSearchPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListDomains.mockResolvedValue(['knowledge', 'memory', 'chat']);
    mockGetStatus.mockResolvedValue({ domains: {}, healthy: true });
  });

  it('uses the federated response and shows its reported coverage', async () => {
    mockSearch.mockResolvedValue(searchResponse([{
      id: 'entry-1',
      source: 'knowledge',
      title: 'Engine health procedure',
      snippet: 'Check the service health endpoint before retrying.',
      url: '/dashboard/knowledge',
      score: 0.91,
      relevance: 0.91,
      metadata: { category: 'operations' },
      permissions: {},
    }]));
    render(<GlobalSearchPage />);

    fireEvent.change(screen.getByRole('searchbox', { name: 'Search JARVIS' }), { target: { value: 'engine health' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    expect(await screen.findByRole('heading', { name: 'Engine health procedure' })).toBeInTheDocument();
    expect(screen.getByText('2 domains searched')).toBeInTheDocument();
    expect(screen.getByText('Check the service health endpoint before retrying.')).toBeInTheDocument();
    expect(mockSearch).toHaveBeenCalledWith('engine health', 'all', 30, false);
  });

  it('shows the backend empty result state without inventing content', async () => {
    mockSearch.mockResolvedValue(searchResponse([]));
    render(<GlobalSearchPage />);

    fireEvent.change(screen.getByRole('searchbox', { name: 'Search JARVIS' }), { target: { value: 'engine health' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    expect(await screen.findByText('No matches for “engine health”')).toBeInTheDocument();
  });

  it('opens external result URLs through the embedded JARVIS browser route', async () => {
    mockSearch.mockResolvedValue(searchResponse([{
      id: 'web-1',
      source: 'web',
      title: 'Reference page',
      snippet: 'A page from a connected web search.',
      url: 'https://example.com/reference',
      score: 0.72,
      relevance: 0.72,
      metadata: {},
      permissions: {},
    }]));
    render(<GlobalSearchPage />);

    fireEvent.change(screen.getByRole('searchbox', { name: 'Search JARVIS' }), { target: { value: 'engine health' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    const browserLink = await screen.findByRole('link', { name: 'Open Reference page in JARVIS Browser' });
    expect(browserLink).toHaveAttribute(
      'href',
      '/dashboard/embedded-browser?url=https%3A%2F%2Fexample.com%2Freference',
    );
  });

  it('surfaces request failures accessibly', async () => {
    mockSearch.mockRejectedValue(new Error('Service unavailable'));
    render(<GlobalSearchPage />);

    fireEvent.change(screen.getByRole('searchbox', { name: 'Search JARVIS' }), { target: { value: 'engine health' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Service unavailable'));
  });
});
