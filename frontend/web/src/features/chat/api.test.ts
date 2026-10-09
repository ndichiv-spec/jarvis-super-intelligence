import { afterEach, describe, expect, it, vi } from 'vitest';
import { cancelStreamingMessage, chatApi } from './api';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('chat streaming cancellation', () => {
  it('preserves the structured backend error code on rejected stream requests', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        error: {
          code: 'AUTHENTICATION_ERROR',
          message: 'Authentication required.',
          status_code: 401,
          retryable: false,
        },
      }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ));
    const onError = vi.fn();

    await chatApi.sendStreamingMessage(
      { message: 'Protected request', session_id: 'session-1' },
      vi.fn(),
      onError,
      vi.fn(),
    );

    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'Authentication required.' }),
      expect.objectContaining({
        category: 'AUTHENTICATION_ERROR',
        status_code: 401,
        retryable: false,
      }),
    );
  });

  it('reports a truncated stream instead of treating EOF as completion', async () => {
    const response = new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode(
            'data: {"type":"meta","session_id":"session-1"}\n\n'
              + 'data: {"type":"chunk","text":"partial"}\n\n',
          ));
          controller.close();
        },
      }),
      { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
    );
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    const onError = vi.fn();
    const onChunk = vi.fn();
    const onComplete = vi.fn();

    await chatApi.sendStreamingMessage(
      { message: 'Request a response', session_id: 'session-1' },
      onChunk,
      onError,
      onComplete,
    );

    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: expect.stringContaining('before JARVIS reported') }),
      expect.objectContaining({ category: 'STREAM_INTERRUPTED', retryable: true }),
    );
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('aborts the active HTTP stream and reports cancellation truthfully', async () => {
    const fetchMock = vi.fn((_url: string, init: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init.signal?.addEventListener('abort', () => reject(new Error('aborted')));
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const onError = vi.fn();
    const onChunk = vi.fn();
    const onComplete = vi.fn();

    const pending = chatApi.sendStreamingMessage(
      { message: 'Stop this response', session_id: 'session-1' },
      onChunk,
      onError,
      onComplete,
    );
    cancelStreamingMessage();
    await pending;

    expect(fetchMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        credentials: 'include',
        signal: expect.any(AbortSignal),
      }),
    );
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: expect.stringContaining('Response stopped') }),
      expect.objectContaining({ category: 'CANCELLED', retryable: true }),
    );
    expect(onChunk).not.toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();
  });
});
