import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const { mockState, setState } = vi.hoisted(() => ({
  mockState: {
    messages: [] as Array<{ id: string; role: string; content: string }>,
    sessions: [] as unknown[],
    currentSessionId: null as string | null,
    isLoading: false,
    isStreaming: false,
    streamingContent: '',
    activeModel: 'auto',
    modelCatalog: { providers: [] as unknown[] },
    connected: false,
    sendMessage: vi.fn(),
    sendStreamMessage: vi.fn(),
    loadSessions: vi.fn(),
    loadSession: vi.fn(),
    deleteSession: vi.fn(),
    newSession: vi.fn(),
    switchModel: vi.fn(),
    loadModelCatalog: vi.fn(),
    error: null as string | null,
    clearError: vi.fn(),
  },
  setState: vi.fn(),
}));

vi.mock('@/features/chat/api', () => ({
  newClientMessageId: () => 'generated-retry-id',
}));

vi.mock('@/features/chat/store', () => ({
  isCurrentLocationRequest: vi.fn(() => false),
  useChatStore: Object.assign(vi.fn(() => mockState), { setState }),
}));

vi.mock('@/lib/neural-theme-engine', () => ({
  detectAIMood: vi.fn(),
  useNeuralTheme: () => ({ autoThemeEnabled: false, setMood: vi.fn() }),
}));

vi.mock('@/components/ui/scroll-area', () => ({
  ScrollArea: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div className={className}>{children}</div>
  ),
}));

vi.mock('./chat-message', () => ({
  ChatMessageBubble: ({ message }: { message: { content: string } }) => <p>{message.content}</p>,
}));

vi.mock('./chat-input', () => ({
  ChatInput: () => <div aria-label="Chat composer" />,
}));

import { ChatWindow } from './chat-window';

describe('ChatWindow recovery state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(mockState, {
      messages: [
        { id: 'previous', role: 'assistant', content: 'Earlier reply' },
        { id: 'failed-prompt', role: 'user', content: 'Check the runtime', client_message_id: 'original-client-id' },
        { id: 'failed-reply', role: 'assistant', content: '' },
      ],
      sessions: [],
      currentSessionId: null,
      isLoading: false,
      isStreaming: false,
      streamingContent: '',
      activeModel: 'auto',
      modelCatalog: { providers: [] },
      connected: false,
      sendMessage: vi.fn(),
      sendStreamMessage: vi.fn(),
      loadSessions: vi.fn(),
      loadSession: vi.fn(),
      deleteSession: vi.fn(),
      newSession: vi.fn(),
      switchModel: vi.fn(),
      loadModelCatalog: vi.fn(),
      error: 'Failed to fetch',
      clearError: vi.fn(),
    });
    HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  it('explains an unreachable service and retries the failed prompt with its original id', () => {
    render(<ChatWindow showSidebar={false} />);

    expect(screen.getByRole('alert')).toHaveTextContent('Unable to reach the JARVIS chat service');
    expect(screen.getByRole('alert')).toHaveTextContent('Check your connection or backend status');
    expect(screen.queryByText('How can I help you today?')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Retry last message' }));

    expect(setState).toHaveBeenCalledWith({
      messages: [mockState.messages[0]],
      error: null,
    });
    expect(mockState.sendStreamMessage).toHaveBeenCalledWith('Check the runtime', 'original-client-id');
  });

  it('generates and uses an id when retrying a historical message without one', () => {
    mockState.messages[1] = { id: 'historical-prompt', role: 'user', content: 'Retry old prompt' };
    render(<ChatWindow showSidebar={false} />);

    fireEvent.click(screen.getByRole('button', { name: 'Retry last message' }));

    expect(mockState.sendStreamMessage).toHaveBeenCalledWith('Retry old prompt', 'generated-retry-id');
  });

  it('does not describe an HTTP service error as an offline client', () => {
    mockState.error = 'HTTP 503 Service Unavailable';
    render(<ChatWindow showSidebar={false} />);

    expect(screen.getByRole('alert')).toHaveTextContent('The JARVIS chat service returned an error');
    expect(screen.getByRole('alert')).toHaveTextContent('The service responded but did not complete the request');
    expect(screen.queryByText('Unable to reach the JARVIS chat service')).not.toBeInTheDocument();
  });
});
