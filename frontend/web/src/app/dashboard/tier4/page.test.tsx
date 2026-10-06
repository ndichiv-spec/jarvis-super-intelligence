import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));

vi.mock('@/lib/api-client', () => ({
  AuthError: class AuthError extends Error {},
  ApiClientError: class ApiClientError extends Error {},
  apiClient: { get: apiGet },
}));

import Tier4Page from './page';

describe('Runtime overview', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders backend runtime state and labels unimplemented enterprise controls unavailable', async () => {
    apiGet.mockImplementation((endpoint: string) => {
      if (endpoint.startsWith('/api/v1/commands?')) {
        return Promise.resolve({
          commands: [{
            command_id: 'cmd-1',
            goal: 'Inspect a repository',
            status: 'EXECUTING',
            created_at: 1_700_000_000,
          }],
        });
      }
      if (endpoint === '/api/v1/commands/metrics') {
        return Promise.resolve({ generated_at: '2025-01-01T00:00:00Z', total_commands: 1, by_status: { EXECUTING: 1 } });
      }
      if (endpoint === '/api/v1/monitoring/metrics') {
        return Promise.resolve({
          timestamp: '2025-01-01T00:00:00Z',
          cpu_percent: 12.5,
          memory: { percent: 48.2 },
          disk: 62,
          processes: 4,
        });
      }
      if (endpoint === '/api/v1/extensions/connections') return Promise.resolve({ connections: [] });
      return Promise.reject(new Error(`Unexpected endpoint: ${endpoint}`));
    });

    render(<Tier4Page />);

    expect(await screen.findByText('Inspect a repository')).toBeInTheDocument();
    expect(screen.getByText('12.5%')).toBeInTheDocument();
    expect(screen.getByText('Organizations & workspaces')).toBeInTheDocument();
    expect(screen.getByText('Security audit & policy')).toBeInTheDocument();
    expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0);
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(4));
  });
});
