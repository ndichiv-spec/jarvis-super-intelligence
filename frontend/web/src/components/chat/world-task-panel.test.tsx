import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

const { commandsApi } = vi.hoisted(() => ({
  commandsApi: {
    list: vi.fn(),
    submit: vi.fn(),
    authorize: vi.fn(),
  },
}));

vi.mock('@/features/runtime/commands-api', () => ({ commandsApi }));

import { WorldTaskPanel } from './world-task-panel';

function makeCommand(overrides: Record<string, unknown> = {}) {
  return {
    command_id: 'command-1',
    goal: 'Review the map',
    status: 'COMPLETED',
    task_id: 'task-1',
    plan: { nodes: ['inspect-map'] },
    result: { success: true, summary: 'Map reviewed' },
    errors: [],
    events: [{ event: 'command_completed', sequence: 1 }],
    request_id: 'request-1',
    conversation_id: 'conversation-1',
    ...overrides,
  };
}

describe('WorldTaskPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
    commandsApi.list.mockResolvedValue([]);
    commandsApi.submit.mockResolvedValue(makeCommand({ status: 'QUEUED', plan: null, result: null, events: [] }));
    commandsApi.authorize.mockImplementation(async (commandId: string, _nodeId: string, approved: boolean) =>
      makeCommand({ command_id: commandId, status: approved ? 'READY' : 'CANCELLED', authorization: { node_ids: [] } }),
    );
  });

  it('submits only through the explicit action and displays the durable command record', async () => {
    commandsApi.list.mockResolvedValueOnce([makeCommand()]);
    commandsApi.submit.mockResolvedValueOnce(makeCommand({
      command_id: 'command-new',
      goal: 'Summarize this region',
      status: 'QUEUED',
      task_id: null,
      plan: null,
      result: null,
      errors: [],
      events: [],
    }));

    render(<WorldTaskPanel conversationId="conversation-7" authenticated />);
    await screen.findByText('Review the map');
    expect(screen.getByText('COMPLETED')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Plan, result, errors & provenance'));
    expect(screen.getByText('Map reviewed')).toBeInTheDocument();
    expect(screen.getByText(/Task task-1/)).toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox', { name: 'What would you like JARVIS to do?' }), {
      target: { value: '  Summarize this region  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Submit task' }));

    await screen.findByText('QUEUED');
    expect(commandsApi.submit).toHaveBeenCalledWith(expect.objectContaining({
      goal: 'Summarize this region',
      conversation_id: 'conversation-7',
      request_id: expect.any(String),
    }));
    expect(screen.getByText('Summarize this region')).toBeInTheDocument();
  });

  it('offers decisions only for node IDs currently returned as pending', async () => {
    commandsApi.list.mockResolvedValueOnce([
      makeCommand({
        status: 'AWAITING_AUTHORIZATION',
        authorization: { required: true, node_ids: ['node-pending'] },
      }),
      makeCommand({
        command_id: 'command-ready',
        status: 'READY',
        authorization: { required: true, node_ids: ['node-not-pending'] },
      }),
    ]);
    render(<WorldTaskPanel authenticated />);

    await screen.findByText('node-pending');
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument();
    expect(screen.queryByText('node-not-pending')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(commandsApi.authorize).toHaveBeenCalledWith('command-1', 'node-pending', true));
  });

  it('sends rejection for the pending node and reports refresh failures', async () => {
    commandsApi.list
      .mockResolvedValueOnce([makeCommand({
        status: 'AWAITING_AUTHORIZATION',
        authorization: { required: true, node_ids: ['node-risky'] },
      })])
      .mockRejectedValueOnce(new Error('Command history unavailable'));
    render(<WorldTaskPanel authenticated />);

    await screen.findByText('node-risky');
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    await waitFor(() => expect(commandsApi.authorize).toHaveBeenCalledWith('command-1', 'node-risky', false));
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Command history unavailable');
  });

  it('restores history from the authenticated command API without local storage', async () => {
    commandsApi.list.mockResolvedValueOnce([makeCommand({
      status: 'FAILED',
      errors: ['Provider unavailable'],
      result: null,
    })]);
    const { container } = render(<WorldTaskPanel authenticated />);

    await screen.findByText('Review the map');
    fireEvent.click(screen.getByText('Plan, result, errors & provenance'));
    expect(screen.getByText('Provider unavailable')).toBeInTheDocument();
    expect(container.querySelectorAll('input')).toHaveLength(0);
    expect(commandsApi.list).toHaveBeenCalledWith();
  });

  it('stops automatic polling when the task workspace is unmounted', async () => {
    vi.useFakeTimers();
    commandsApi.list.mockResolvedValue([makeCommand({
      status: 'EXECUTING',
      plan: null,
      result: null,
      events: [],
    })]);
    const { unmount } = render(<WorldTaskPanel authenticated />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });

    expect(commandsApi.list).toHaveBeenCalledTimes(1);
  });
});
