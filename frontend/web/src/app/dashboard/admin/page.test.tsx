import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const { api, toast } = vi.hoisted(() => ({
  api: {
    rbac: {
      getUsers: vi.fn(),
      getRoles: vi.fn(),
      createUser: vi.fn(),
      updateUser: vi.fn(),
      deleteUser: vi.fn(),
      getPermissions: vi.fn(),
      createRole: vi.fn(),
      updateRole: vi.fn(),
      deleteRole: vi.fn(),
      getAuditLogs: vi.fn(),
      exportAuditLogs: vi.fn(),
      getTenantSettings: vi.fn(),
      updateTenantSettings: vi.fn(),
    },
  },
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/lib/api', () => ({ jarvisAPI: api }));
vi.mock('sonner', () => ({ toast }));

import { useAuthStore } from '@/stores/authStore';
import AdminPage from './page';

const owner = {
  id: 'owner-1',
  email: 'owner@example.test',
  username: 'owner',
  status: 'active',
  tenant_id: null,
  roles: ['owner', 'admin'],
};

describe('AdminPage backend contracts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: owner, isAuthenticated: true, authStatus: 'authenticated' });
    api.rbac.getUsers.mockImplementation((_page: number, _perPage: number, search?: string) => Promise.resolve({
      users: search
        ? [{ ...owner, roles: ['owner', 'admin'] }]
        : [],
      total: search ? 1 : 0,
      page: 1,
      per_page: 10,
    }));
    api.rbac.getRoles.mockResolvedValue({ roles: [{ id: 'user-role', name: 'user', permissions: [], is_system: true }] });
    api.rbac.getPermissions.mockResolvedValue({ permissions: [] });
  });

  it('keeps a denied users request distinct from a genuinely empty user list', async () => {
    api.rbac.getUsers.mockRejectedValue(Object.assign(new Error('Permission denied'), { status: 403 }));

    render(<AdminPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Permission denied');
    expect(screen.queryByText('No users found')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('submits only the accepted create-user schema and explains the backend defaults', async () => {
    api.rbac.createUser.mockResolvedValue({
      id: 'new-user',
      email: 'new@example.test',
      username: 'newuser',
      roles: ['user'],
      status: 'pending_authorization',
    });
    render(<AdminPage />);

    fireEvent.click(await screen.findByRole('button', { name: /add user/i }));
    expect(screen.getByText(/default user role and remain pending/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Email *'), { target: { value: 'new@example.test' } });
    fireEvent.change(screen.getByLabelText('Username *'), { target: { value: 'newuser' } });
    fireEvent.change(screen.getByLabelText('Password *'), { target: { value: 'long-enough-password' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create User' }));

    await waitFor(() => {
      expect(api.rbac.createUser).toHaveBeenCalledWith({
        email: 'new@example.test',
        username: 'newuser',
        password: 'long-enough-password',
      });
    });
    expect(api.rbac.createUser.mock.calls[0][0]).not.toHaveProperty('roles');
  });

  it('does not expose owner-only user mutation actions to a non-owner identity', async () => {
    useAuthStore.setState({
      user: { ...owner, email: 'admin@example.test', roles: ['admin'] },
      isAuthenticated: true,
      authStatus: 'authenticated',
    });
    api.rbac.getUsers.mockImplementation((_page: number, _perPage: number, search?: string) => Promise.resolve({
      users: search
        ? [{ ...owner, email: 'admin@example.test', roles: ['admin'] }]
        : [{ id: 'u-1', email: 'person@example.test', username: 'person', roles: ['user'], status: 'active' }],
      total: 1,
      page: 1,
      per_page: 10,
    }));

    render(<AdminPage />);

    expect(await screen.findByText('Read-only view. Creating, editing, and deleting users is restricted to the configured tenant owner.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add user/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /edit user/i })).not.toBeInTheDocument();
  });

  it('renders only tenant settings returned by the API and keeps omitted identity fields absent', async () => {
    const user = userEvent.setup();
    api.rbac.getTenantSettings.mockResolvedValue({
      max_users: 24,
      settings: { feature_flags: { reports: true } },
    });
    render(<AdminPage />);

    await user.click(screen.getByRole('tab', { name: 'Settings' }));

    expect(await screen.findByText('24')).toBeInTheDocument();
    expect(screen.getByText('Advanced Configuration')).toBeInTheDocument();
    expect(screen.queryByText('JARVIS Enterprise')).not.toBeInTheDocument();
    expect(screen.queryByText('Tenant ID')).not.toBeInTheDocument();
    expect(screen.queryByText('Plan')).not.toBeInTheDocument();
  });

  it('shows tenant settings permission denial without substituting default tenant data', async () => {
    const user = userEvent.setup();
    api.rbac.getTenantSettings.mockRejectedValue(Object.assign(new Error('Permission denied'), { status: 403 }));
    render(<AdminPage />);

    await user.click(screen.getByRole('tab', { name: 'Settings' }));

    expect(await screen.findByText('Permission denied')).toBeInTheDocument();
    expect(screen.queryByText('JARVIS Enterprise')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });
});
