import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const { api, toast } = vi.hoisted(() => ({
  api: {
    getAgents: vi.fn(),
    getAgentTasks: vi.fn(),
    getSchedulerStatus: vi.fn(),
    getTaskExecutions: vi.fn(),
    getServiceTailoringStatus: vi.fn(),
    getCollaborationAgents: vi.fn(),
    getCollaborationTasks: vi.fn(),
    executeCollaborationTask: vi.fn(),
    registerCustomTask: vi.fn(),
    toggleAgentTask: vi.fn(),
    runAgentTask: vi.fn(),
    deleteAgentTask: vi.fn(),
    toggleScheduler: vi.fn(),
  },
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/lib/api', () => ({ jarvisAPI: api }));
vi.mock('sonner', () => ({ toast }));

import AgentsPage from './page';

describe('AgentsPage data contracts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getAgents.mockResolvedValue({
      agents: [{ id: 'agent-1', name: 'Planner', role: 'coordinator', status: 'active', capabilities: ['plan'] }],
    });
    api.getAgentTasks.mockResolvedValue({ tasks: [], total: 0 });
    api.getSchedulerStatus.mockResolvedValue({ running: false, status: 'NOT_CONFIGURED', next_run: null });
    api.getTaskExecutions.mockResolvedValue({ executions: [] });
    api.getServiceTailoringStatus.mockResolvedValue({ enabled: false, status: 'NOT_CONFIGURED', services: [] });
    api.getCollaborationAgents.mockResolvedValue({ agents: [] });
    api.getCollaborationTasks.mockResolvedValue({ tasks: [], total: 0 });
  });

  it('keeps registry inventory separate from a real empty task response', async () => {
    render(<AgentsPage />);

    expect(await screen.findByText('Planner')).toBeInTheDocument();
    expect(screen.getByText('No tasks yet')).toBeInTheDocument();
    expect(screen.getByText('Registered agents')).toBeInTheDocument();
    expect(screen.getByText('Tasks returned')).toBeInTheDocument();
    expect(screen.queryByText('Success Rate')).not.toBeInTheDocument();
    expect(screen.queryByText('Planner automation task')).not.toBeInTheDocument();
    expect(screen.getByText(/Not configured by the backend/)).toBeInTheDocument();
    expect(api.getAgentTasks).toHaveBeenCalledWith(50);
  });

  it('shows a retryable permission error instead of presenting an unavailable task feed as empty', async () => {
    api.getAgentTasks.mockRejectedValue(Object.assign(new Error('Permission denied'), { status: 403 }));

    render(<AgentsPage />);

    expect(await screen.findByText('Permission denied')).toBeInTheDocument();
    expect(screen.queryByText('No tasks yet')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    expect(screen.getByText('Scheduler not configured')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Unavailable' })).toBeDisabled();
  });

  it('labels server failures separately from permission denial and keeps a retry action', async () => {
    api.getAgentTasks.mockRejectedValue(Object.assign(new Error('Upstream unavailable'), { status: 503 }));

    render(<AgentsPage />);

    expect(await screen.findByText('Server error (503)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    expect(screen.queryByText('No tasks yet')).not.toBeInTheDocument();
  });

  it('never offers enabled scheduling or self-organize controls when the backend reports them unavailable', async () => {
    const user = userEvent.setup();
    render(<AgentsPage />);

    expect(await screen.findByText('Scheduler not configured')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Unavailable' })).toBeDisabled();
    expect(screen.getByRole('tab', { name: /Agent Collaboration/ })).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: /Agent Collaboration/ }));
    expect(await screen.findByRole('tab', { name: /Self-Organize/ })).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: /Self-Organize/ }));
    expect(await screen.findByRole('button', { name: 'Self-Organize' })).toBeDisabled();
    expect(screen.getByText(/Automatic planning is not configured/)).toBeInTheDocument();
  });
});
