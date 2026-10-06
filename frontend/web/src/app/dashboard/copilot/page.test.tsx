import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const { mockGet, mockPost, mockPush } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPush: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('@/lib/api-client', () => ({
  default: { get: mockGet, post: mockPost },
}));

import CopilotPage from './page';
import { API_ENDPOINTS } from '@/config/api';

describe('Copilot email action', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockResolvedValue({
      connectors: [{
        kind: 'email',
        configured: true,
        enabled: true,
        capabilities: ['read', 'send'],
      }],
    });
    mockPost.mockResolvedValue({ ok: true });
    vi.spyOn(window, 'confirm');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  async function fillEmail() {
    await screen.findByLabelText('Recipient');
    fireEvent.change(screen.getByLabelText('Recipient'), {
      target: { value: 'recipient@example.com' },
    });
    fireEvent.change(screen.getByLabelText('Subject'), {
      target: { value: 'Connection update' },
    });
    fireEvent.change(screen.getByLabelText('Message'), {
      target: { value: 'The account was connected.' },
    });
  }

  it('does not call the connector when the user cancels confirmation', async () => {
    vi.mocked(window.confirm).mockReturnValue(false);
    render(<CopilotPage />);

    await fillEmail();
    fireEvent.click(screen.getByRole('button', { name: 'Review and send' }));

    await waitFor(() => expect(screen.getAllByText('Email cancelled. Nothing was sent.').length).toBeGreaterThan(0));
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('sends only after explicit confirmation and disables request retries', async () => {
    vi.mocked(window.confirm).mockReturnValue(true);
    render(<CopilotPage />);

    await fillEmail();
    fireEvent.click(screen.getByRole('button', { name: 'Review and send' }));

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      API_ENDPOINTS.connectors.action('email'),
      {
        action: 'email.send',
        params: {
          to: ['recipient@example.com'],
          subject: 'Connection update',
          body: 'The account was connected.',
          confirm: true,
        },
      },
      { retries: 0 },
    ));
    await waitFor(() => expect(screen.getAllByText('Email sent to recipient@example.com.').length).toBeGreaterThan(0));
  });
});
