import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import FileStructureDisplay from './FileStructureDisplay';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('FileStructureDisplay', () => {
  it('reports backend failure instead of rendering a fabricated tree', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('Network unavailable'));
    vi.stubGlobal('fetch', fetchMock);

    render(<FileStructureDisplay />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Network unavailable');
    expect(screen.queryByText('slack_integration.py')).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/system/file-structure'),
      expect.objectContaining({ credentials: 'include' }),
    );
  });

  it('renders only the structure returned by the backend', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            success: true,
            structure: [{ name: 'actual', type: 'directory', path: '/actual', status: 'active' }],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    );

    render(<FileStructureDisplay />);

    await waitFor(() => expect(screen.getByText('actual')).toBeInTheDocument());
    expect(screen.queryByText('slack_integration.py')).not.toBeInTheDocument();
  });
});
