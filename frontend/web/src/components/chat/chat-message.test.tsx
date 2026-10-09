import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { ChatMessageBubble } from './chat-message';
import type { ChatMessage } from '@/features/chat/types';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('ChatMessageBubble speech playback', () => {
  it('keeps provider and model attribution in opt-in technical details', () => {
    render(
      <ChatMessageBubble
        message={{
          id: 'assistant-technical',
          role: 'assistant',
          content: 'Here is the answer.',
          provider: 'provider-internal',
          model: 'model-internal',
        }}
      />,
    );

    const disclosure = screen.getByText('Technical details');
    expect(disclosure.closest('details')).not.toHaveAttribute('open');
    fireEvent.click(disclosure);
    expect(disclosure.closest('details')).toHaveAttribute('open');
    expect(screen.getByText('provider-internal')).toBeInTheDocument();
    expect(screen.getByText('model-internal')).toBeInTheDocument();
  });

  it('uses browser speech synthesis and lets the user interrupt playback', () => {
    class UtteranceMock {
      onstart: (() => void) | null = null;
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(public text: string) {}
    }
    const speak = vi.fn((utterance: UtteranceMock) => utterance.onstart?.());
    const cancel = vi.fn();
    vi.stubGlobal('SpeechSynthesisUtterance', UtteranceMock);
    vi.stubGlobal('speechSynthesis', { speak, cancel });
    const message: ChatMessage = {
      id: 'assistant-1',
      role: 'assistant',
      content: 'Your schedule is clear.',
      timestamp: new Date().toISOString(),
      status: 'COMPLETED',
    };

    render(<ChatMessageBubble message={message} />);
    fireEvent.click(screen.getByRole('button', { name: 'Speak response' }));
    expect(speak).toHaveBeenCalledOnce();
    expect(speak.mock.calls[0][0].text).toBe('Your schedule is clear.');

    fireEvent.click(screen.getByRole('button', { name: 'Stop spoken response' }));
    expect(cancel).toHaveBeenCalledOnce();
  });

  it('loads generated image attachments through the authenticated artifact endpoint', async () => {
    const createObjectURL = vi.fn().mockReturnValue('blob:generated-image');
    const revokeObjectURL = vi.fn();
    class URLWithObjectUrls extends URL {
      static createObjectURL(blob: Blob) {
        return createObjectURL(blob);
      }
      static revokeObjectURL(url: string) {
        revokeObjectURL(url);
      }
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['image-bytes'], { type: 'image/png' }),
    });
    vi.stubGlobal('URL', URLWithObjectUrls);
    vi.stubGlobal('fetch', fetchMock);

    const message: ChatMessage = {
      id: 'assistant-image',
      role: 'assistant',
      content: 'Generated 1 image.',
      timestamp: new Date().toISOString(),
      status: 'COMPLETED',
      metadata: {
        artifacts: [{
          artifact_id: 'artifact-1',
          url: '/api/v1/image/artifacts/artifact-1',
          prompt: 'a red cube',
          width: 1024,
          height: 1024,
        }],
      },
    };

    render(<ChatMessageBubble message={message} />);

    expect(await screen.findByRole('img', { name: 'Generated image' })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/image/artifacts/artifact-1',
      expect.objectContaining({ credentials: 'include', cache: 'no-store' }),
    );
  });
});
