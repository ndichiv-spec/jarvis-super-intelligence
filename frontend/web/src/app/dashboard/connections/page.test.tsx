import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const {
  apiGet,
  apiPost,
  apiPatch,
  apiDelete,
  toastError,
  toastSuccess,
  toastWarning,
  confirmDialog,
} = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
  toastWarning: vi.fn(),
  confirmDialog: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  ApiClientError: class ApiClientError extends Error {},
  apiClient: {
    get: apiGet,
    post: apiPost,
    patch: apiPatch,
    delete: apiDelete,
  },
}));

vi.mock('@/config/api', () => ({
  API_ENDPOINTS: {
    connectors: {
      oauthAuthorize: (kind: string) => `/api/v1/connectors/${kind}/oauth/authorize`,
      oauthDisconnect: (kind: string) => `/api/v1/connectors/${kind}/oauth`,
    },
  },
}));

vi.mock('sonner', () => ({
  toast: { error: toastError, success: toastSuccess, warning: toastWarning },
}));

import ConnectionsPage from './page';

describe('ConnectionsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState({}, '', '/dashboard/connections');
    vi.stubGlobal('confirm', confirmDialog);
    confirmDialog.mockReturnValue(true);
    apiGet.mockImplementation((endpoint: string) => {
      if (endpoint === '/api/v1/connectors/activity') return Promise.resolve({ entries: [] });
      if (endpoint === '/api/v1/extensions/connections') return Promise.resolve({ connections: [] });
      return Promise.resolve({ connectors: [] });
    });
  });

  it('derives readiness and sender details from the connector response only', async () => {
    apiGet.mockImplementation((endpoint: string) => {
      if (endpoint === '/api/v1/connectors/activity') return Promise.resolve({ entries: [] });
      if (endpoint === '/api/v1/extensions/connections') return Promise.resolve({ connections: [] });
      return Promise.resolve({
        connectors: [
          {
            kind: 'email',
            configured: true,
            enabled: true,
            config: {
              send_from: 'alerts@example.test',
              imap_user: 'not-the-sender@example.test',
              password_set: true,
              capabilities: ['read', 'send'],
              last_test_ok: false,
            },
          },
          {
            kind: 'gmail',
            configured: true,
            connection_status: 'Connected',
            account: 'person@example.test',
            capabilities: ['read'],
          },
          { kind: 'outlook', configured: false },
        ],
      });
    });

    render(<ConnectionsPage />);

    expect(await screen.findByText('2 / 3')).toBeInTheDocument();
    expect(screen.getByText('1 / 2 authorized')).toBeInTheDocument();
    expect(screen.getByText('2 connections')).toBeInTheDocument();
    expect(screen.getByText('Last test failed')).toBeInTheDocument();
    expect(screen.getByText('alerts@example.test')).toBeInTheDocument();
    expect(screen.getByText('Reported capabilities: read')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Read / Search capability' })).toBeChecked();
    expect(screen.getByRole('switch', { name: 'Send / Reply capability' })).toBeChecked();
    expect(screen.getByRole('switch', { name: 'Draft capability' })).not.toBeChecked();
    expect(screen.queryByText('not-the-sender@example.test')).not.toBeInTheDocument();
    expect(screen.getByText('No activity yet.')).toBeInTheDocument();
  });

  it('keeps initial email setup accessible when no connector is configured', async () => {
    render(<ConnectionsPage />);

    const configureButton = await screen.findByRole('button', { name: 'Configure' });
    expect(configureButton).toBeEnabled();
    expect(screen.getByText('The API reports no configured connectors yet. Set up a provider below to begin.')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'IMAP Host' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Username (email address)' })).toBeInTheDocument();
    expect(screen.getByLabelText('App Password')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'SMTP Host' })).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: 'IMAP port' })).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: 'SMTP port' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Use SSL/TLS (port 993)' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Use STARTTLS (port 587)' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Send From' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Email actions active' })).not.toBeChecked();
    expect(screen.getByRole('switch', { name: 'Read / Search capability' })).not.toBeChecked();
    expect(screen.getByRole('switch', { name: 'Summarize capability' })).not.toBeChecked();
    expect(screen.getByRole('switch', { name: 'Draft capability' })).not.toBeChecked();
    expect(screen.getByRole('switch', { name: 'Send / Reply capability' })).not.toBeChecked();
  });

  it('requires an explicit capability choice and never sends default-on capabilities on create', async () => {
    render(<ConnectionsPage />);

    fireEvent.change(await screen.findByRole('textbox', { name: 'IMAP Host' }), {
      target: { value: 'imap.example.test' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: 'Username (email address)' }), {
      target: { value: 'person@example.test' },
    });
    fireEvent.change(screen.getByLabelText('App Password'), {
      target: { value: 'fresh-app-password' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Connection' }));

    expect(toastError).toHaveBeenCalledWith(expect.stringContaining('Choose at least one email capability'));
    expect(apiPost).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('switch', { name: 'Read / Search capability' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save Connection' }));

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/v1/connectors/email', expect.objectContaining({
        capabilities: ['read'],
        enabled: false,
      }));
    });
  });

  it('does not start an OAuth redirect until the user explicitly confirms', async () => {
    confirmDialog.mockReturnValue(false);
    render(<ConnectionsPage />);

    fireEvent.click((await screen.findAllByRole('button', { name: 'Connect account' }))[0]);

    expect(confirmDialog).toHaveBeenCalledWith(expect.stringContaining('review and approve'));
    expect(apiPost).not.toHaveBeenCalled();
  });

  it('does not display an untrusted OAuth callback error value', async () => {
    window.history.replaceState({}, '', '/dashboard/connections?oauth_error=private-provider-detail');
    render(<ConnectionsPage />);

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith(
        'Provider authorization could not be completed. Please try again or contact an administrator.',
      );
    });
    expect(toastError).not.toHaveBeenCalledWith(expect.stringContaining('private-provider-detail'));
    expect(window.location.search).toBe('');
  });

  it('shows a non-success warning when authorization succeeds but verification fails', async () => {
    window.history.replaceState(
      {},
      '',
      '/dashboard/connections?connected=gmail&verification=failed&keep=visible',
    );
    render(<ConnectionsPage />);

    await waitFor(() => {
      expect(toastWarning).toHaveBeenCalledWith(
        'Google authorization completed, but the read-only verification probe failed. The account may be authorized; check its connection status and retry verification.',
      );
    });
    expect(toastSuccess).not.toHaveBeenCalledWith('Google account connected');
    expect(window.location.search).toBe('?keep=visible');
  });

  it('uses safe provider-aware messages for known OAuth failures', async () => {
    window.history.replaceState(
      {},
      '',
      '/dashboard/connections?oauth_error=exchange_failed&provider=outlook',
    );
    render(<ConnectionsPage />);

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith(
        'Microsoft authorization could not be completed. Please try again or contact an administrator.',
      );
    });
    expect(toastError).not.toHaveBeenCalledWith(expect.stringContaining('exchange_failed'));
    expect(window.location.search).toBe('');
  });

  it('does not echo an unrecognized OAuth provider into the warning', async () => {
    window.history.replaceState(
      {},
      '',
      '/dashboard/connections?oauth_error=access_denied&provider=%3Cscript%3Ealert(1)%3C%2Fscript%3E',
    );
    render(<ConnectionsPage />);

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith(
        'Provider authorization was declined. No provider connection was added.',
      );
    });
    expect(toastError).not.toHaveBeenCalledWith(expect.stringContaining('<script>'));
  });

  it('marks connector status unavailable and disables actions when the API denies access', async () => {
    apiGet.mockRejectedValue(new Error('Forbidden'));
    render(<ConnectionsPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Connector configuration is unavailable.');
    expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: 'Connect account' }).every((button) => (button as HTMLButtonElement).disabled)).toBe(true);
    expect(screen.getByText('Activity is unavailable because connector status could not be refreshed.')).toBeInTheDocument();
  });
});
