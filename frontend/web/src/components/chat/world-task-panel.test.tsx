import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { worldWorkspaceApi, type WorldCommand } from '@/features/commands/api';
import { WorldTaskPanel } from './world-task-panel';

vi.mock('@/features/commands/api', () => ({
  worldWorkspaceApi: {
    submit: vi.fn(),
    get: vi.fn(),
    authorize: vi.fn(),
  },
}));

const receivedCommand: WorldCommand = {
  command_id: 'cmd-123',
  conversation_id: 'session-1',
  goal: 'Research official documentation',
  status: 'RECEIVED',
};

describe('WorldTaskPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(worldWorkspaceApi.submit).mockResolvedValue(receivedCommand);
    vi.mocked(worldWorkspaceApi.get).mockResolvedValue(receivedCommand);
  });

  it('submits a natural language goal through the authenticated durable command API', async () => {
    render(<WorldTaskPanel conversationId="session-1" authenticated />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Describe the task for JARVIS' }), {
      target: { value: ' Research official documentation ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Start task' }));

    await waitFor(() => expect(worldWorkspaceApi.submit).toHaveBeenCalledWith(
      'Research official documentation',
      'session-1',
      expect.any(String),
    ));
    expect(await screen.findByText('Task cmd-123')).toBeInTheDocument();
    expect(screen.getByText('Received')).toBeInTheDocument();
  });

  it('does not submit for a visitor without an authenticated owner session', () => {
    render(<WorldTaskPanel conversationId="session-1" authenticated={false} />);

    expect(screen.getByText('Sign in with an authorized JARVIS account to submit or inspect tasks.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Start task' })).not.toBeInTheDocument();
    expect(worldWorkspaceApi.submit).not.toHaveBeenCalled();
  });

  it('requires an explicit owner decision before resuming a protected action', async () => {
    vi.mocked(worldWorkspaceApi.submit).mockResolvedValue({
      ...receivedCommand,
      status: 'AWAITING_AUTHORIZATION',
      authorization: {
        required: true,
        node_ids: ['send-email'],
        actions: [{ node_id: 'send-email', capability: 'email.send', risk_level: 'admin' }],
      },
    });
    vi.mocked(worldWorkspaceApi.authorize).mockResolvedValue({
      ...receivedCommand,
      status: 'READY',
    });
    render(<WorldTaskPanel conversationId="session-1" authenticated />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Describe the task for JARVIS' }), {
      target: { value: 'Prepare and send the project email' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Start task' }));

    expect(await screen.findByText(/email\.send/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Approve action' }));
    await waitFor(() => expect(worldWorkspaceApi.authorize).toHaveBeenCalledWith('cmd-123', true, 'send-email'));
    expect(await screen.findByText('Ready to execute')).toBeInTheDocument();
  });

  it('lets the owner approve each displayed action individually', async () => {
    const authorization = {
      required: true,
      node_ids: ['node-a', 'node-b'],
      actions: [
        { node_id: 'node-a', capability: 'github.inspect', risk_level: 'network' },
        { node_id: 'node-b', capability: 'cloud.inspect', risk_level: 'admin' },
      ],
    };
    vi.mocked(worldWorkspaceApi.submit).mockResolvedValue({
      ...receivedCommand,
      status: 'AWAITING_AUTHORIZATION',
      authorization,
    });
    vi.mocked(worldWorkspaceApi.authorize)
      .mockResolvedValueOnce({
        ...receivedCommand,
        status: 'AWAITING_AUTHORIZATION',
        authorization: { ...authorization, approved_node_ids: ['node-a'] },
      })
      .mockResolvedValueOnce({ ...receivedCommand, status: 'READY' });
    render(<WorldTaskPanel conversationId="session-1" authenticated />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Describe the task for JARVIS' }), {
      target: { value: 'Inspect both services' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Start task' }));

    const actionPicker = await screen.findByRole('combobox', { name: 'Action requiring approval' });
    fireEvent.change(actionPicker, { target: { value: 'node-a' } });
    fireEvent.click(screen.getByRole('button', { name: 'Approve action' }));
    await waitFor(() => expect(worldWorkspaceApi.authorize).toHaveBeenNthCalledWith(1, 'cmd-123', true, 'node-a'));

    fireEvent.change(actionPicker, { target: { value: 'node-b' } });
    fireEvent.click(screen.getByRole('button', { name: 'Approve action' }));
    await waitFor(() => expect(worldWorkspaceApi.authorize).toHaveBeenNthCalledWith(2, 'cmd-123', true, 'node-b'));
    expect(await screen.findByText('Ready to execute')).toBeInTheDocument();
  });
});
