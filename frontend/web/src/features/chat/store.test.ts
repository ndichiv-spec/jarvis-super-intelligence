import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockGetSessionHistory,
  mockGetModelCatalog,
  mockIsTransient,
  mockSendMessage,
  mockSendStreamingMessage,
  mockNewClientMessageId,
} = vi.hoisted(() => ({
  mockGetSessionHistory: vi.fn(),
  mockGetModelCatalog: vi.fn(),
  mockNewClientMessageId: vi.fn(() => 'generated-client-id'),
  mockSendMessage: vi.fn(),
  mockIsTransient: vi.fn((category?: string) =>
    Boolean(category && ['RATE_LIMITED', 'PROVIDER_UNAVAILABLE', 'STREAM_INTERRUPTED', 'INTERNAL_ERROR', 'UNKNOWN_ERROR'].includes(category)),
  ),
  mockSendStreamingMessage: vi.fn(),
}));

vi.mock('./api', () => ({
  default: {
    getSessionHistory: (...args: unknown[]) => mockGetSessionHistory(...args),
    getModelCatalog: (...args: unknown[]) => mockGetModelCatalog(...args),
    sendMessage: (...args: unknown[]) => mockSendMessage(...args),
    sendStreamingMessage: (...args: unknown[]) => mockSendStreamingMessage(...args),
    isTransient: (category?: string) => mockIsTransient(category),
  },
  newClientMessageId: () => mockNewClientMessageId(),
}));

import { useChatStore } from './store';

describe('chat streaming error handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockGetSessionHistory.mockReset();
    mockGetModelCatalog.mockReset();
    useChatStore.setState({
      messages: [],
      currentSessionId: 'session-1',
      isLoading: false,
      isStreaming: false,
      streamingContent: '',
      error: null,
      connected: true,
      _drafts: {},
    });
    mockSendMessage.mockResolvedValue({ message: 'ok' });
  });

  it('uses the error category, keeps connectivity for retryable request errors, and preserves the draft', async () => {
    mockSendStreamingMessage.mockImplementationOnce(
      async (
        _request: unknown,
        _onChunk: unknown,
        onError: (error: Error, info?: {
          category: string;
          message: string;
          request_id: string;
          retryable: boolean;
        }) => void,
      ) => {
        onError(new Error('Invalid request'), {
          category: 'INVALID_REQUEST',
          message: 'Invalid request',
          request_id: 'req-1',
          retryable: true,
        });
      },
    );

    await useChatStore.getState().sendStreamMessage('Keep this prompt');

    expect(mockSendStreamingMessage.mock.calls[0][0]).toMatchObject({
      client_message_id: 'generated-client-id',
    });
    expect(useChatStore.getState().messages[0].client_message_id).toBe('generated-client-id');
    expect(mockIsTransient).toHaveBeenCalledWith('INVALID_REQUEST');
    expect(useChatStore.getState().connected).toBe(true);
    expect(useChatStore.getState().error).toBe('Invalid request');
    expect(useChatStore.getState().loadDraft('session-1')).toBe('Keep this prompt');
  });

  it('marks the connection unavailable for transient streaming failures and preserves the draft', async () => {
    mockSendStreamingMessage.mockImplementationOnce(
      async (
        _request: unknown,
        _onChunk: unknown,
        onError: (error: Error, info?: {
          category: string;
          message: string;
          request_id: string;
          retryable: boolean;
        }) => void,
      ) => {
        onError(new Error('Connection lost'), {
          category: 'STREAM_INTERRUPTED',
          message: 'Connection lost',
          request_id: 'req-2',
          retryable: true,
        });
      },
    );

    await useChatStore.getState().sendStreamMessage('Retry this prompt');

    expect(mockSendStreamingMessage.mock.calls[0][0]).toMatchObject({
      client_message_id: 'generated-client-id',
    });
    expect(mockIsTransient).toHaveBeenCalledWith('STREAM_INTERRUPTED');
    expect(useChatStore.getState().connected).toBe(false);
    expect(useChatStore.getState().loadDraft('session-1')).toBe('Retry this prompt');
  });

  it('marks the assistant turn failed when streaming fails before a terminal frame', async () => {
    mockSendStreamingMessage.mockImplementationOnce(
      async (
        _request: unknown,
        _onChunk: unknown,
        onError: (error: Error, info?: {
          category: string;
          message: string;
          request_id: string;
          retryable: boolean;
        }) => void,
      ) => {
        onError(new Error('Authentication required.'), {
          category: 'AUTHENTICATION_ERROR',
          message: 'Authentication required.',
          request_id: 'req-auth',
          retryable: false,
        });
      },
    );

    await useChatStore.getState().sendStreamMessage('Protected prompt');

    const assistant = useChatStore.getState().messages.at(-1);
    expect(assistant).toMatchObject({
      role: 'assistant',
      status: 'FAILED',
      error: {
        category: 'AUTHENTICATION_ERROR',
        message: 'Authentication required.',
        request_id: 'req-auth',
      },
    });
    expect(useChatStore.getState().isStreaming).toBe(false);
  });

  it('passes a stable client message id through the buffered send path', async () => {
    await useChatStore.getState().sendMessage('Buffered message', 'buffered-client-id');

    expect(mockSendMessage).toHaveBeenCalledWith(expect.objectContaining({
      message: 'Buffered message',
      client_message_id: 'buffered-client-id',
    }));
    expect(useChatStore.getState().messages[0].client_message_id).toBe('buffered-client-id');
  });

  it('adds a failed assistant turn when the buffered request is rejected', async () => {
    mockSendMessage.mockRejectedValueOnce(new Error('Authentication required.'));

    await useChatStore.getState().sendMessage('Protected buffered request');

    expect(useChatStore.getState().messages.at(-1)).toMatchObject({
      role: 'assistant',
      status: 'FAILED',
      error: 'Authentication required.',
    });
    expect(useChatStore.getState().connected).toBe(true);
  });

  it('preserves client message ids when loading session history', async () => {
    mockGetSessionHistory.mockResolvedValueOnce({
      session: {},
      total: 1,
      messages: [{
        id: 'persisted-user',
        role: 'user',
        content: 'Original prompt',
        client_message_id: 'persisted-client-id',
      }],
    });

    await useChatStore.getState().loadSession('session-1');

    expect(useChatStore.getState().messages[0].client_message_id).toBe('persisted-client-id');
  });

  it('does not select a non-operational default model from the catalog', async () => {
    mockGetModelCatalog.mockResolvedValueOnce({
      providers: [],
      default_provider: 'local',
      default_model: 'local-rule',
    });

    await useChatStore.getState().loadModelCatalog();

    expect(useChatStore.getState().activeModel).toBe('auto');
  });

  it('selects the catalog default only when its provider is available and authorized', async () => {
    mockGetModelCatalog.mockResolvedValueOnce({
      providers: [{
        provider: 'openai',
        available: true,
        authorized: true,
        configured: true,
        model: 'gpt-test',
        models: ['gpt-test'],
      }],
      default_provider: 'openai',
      default_model: 'gpt-test',
    });

    await useChatStore.getState().loadModelCatalog();

    expect(useChatStore.getState().activeModel).toBe('openai:gpt-test');
  });
});
