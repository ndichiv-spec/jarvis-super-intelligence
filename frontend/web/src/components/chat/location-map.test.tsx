import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { apiClient } from '@/lib/api-client';
import type { PresentationIntent } from '@/features/runtime/presentation-contract';
import { LocationMap } from './location-map';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('LocationMap presentation renderer', () => {
  it('renders only the authenticated semantic location reference and reports real interactions', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      latitude: 42.3,
      longitude: -71.1,
      accuracyMeters: 9,
      timestamp: '2026-10-08T08:00:00.000Z',
      source: 'browser_geolocation',
      freshness: { capturedAt: '2026-10-08T08:00:00.000Z', ageSeconds: 1 },
    });
    vi.mocked(apiClient.post).mockResolvedValue({ created: true });
    const intent = {
      id: 'presentation-1',
      sessionId: 'conversation-1',
      sequence: 3,
      environment: { id: 'geospatial', type: 'geospatial' },
      visualizations: [{
        id: 'current-location-map',
        type: 'map',
        data: {
          source: 'runtime',
          resource: '/api/v1/presentation/location/presentation-1',
          freshness: { required: true, maxAgeMs: 120000 },
        },
      }],
    } as PresentationIntent;

    render(<LocationMap intent={intent} />);

    expect(await screen.findByRole('img', {
      name: 'Authorized browser location view, zoom level 1.0',
    })).toBeInTheDocument();
    expect(screen.getByText('Estimated accuracy ±9 m')).toBeInTheDocument();
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/presentation/location/presentation-1');
    expect(JSON.stringify(vi.mocked(apiClient.get).mock.calls)).not.toContain('42.3');
    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        '/api/v1/presentation/location/presentation-1/rendered',
        {},
      );
    });

    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }));
    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        '/api/v1/presentation/location/presentation-1/interactions',
        { action: 'zoom' },
      );
    });
  });
});
