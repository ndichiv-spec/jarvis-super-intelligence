import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { ChatInput } from './chat-input';

type RecognitionEvent = {
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
};

interface MockRecognition {
  onresult: ((event: RecognitionEvent) => void) | null;
  onend: (() => void) | null;
  start: ReturnType<typeof vi.fn>;
  stop: ReturnType<typeof vi.fn>;
  abort: ReturnType<typeof vi.fn>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ChatInput voice capture', () => {
  it('inserts browser-recognized speech into the normal chat send flow', () => {
    let recognition: MockRecognition | undefined;
    class RecognitionMock {
      continuous = false;
      interimResults = false;
      lang = '';
      onresult: ((event: RecognitionEvent) => void) | null = null;
      onerror: ((event: { error: string }) => void) | null = null;
      onend: (() => void) | null = null;
      start = vi.fn();
      stop = vi.fn();
      abort = vi.fn();
      constructor() {
        recognition = this as MockRecognition;
      }
    }
    vi.stubGlobal('SpeechRecognition', RecognitionMock);
    const onSend = vi.fn();

    render(<ChatInput onSend={onSend} />);
    fireEvent.click(screen.getByRole('button', { name: 'Start voice input' }));
    expect(screen.getByRole('status')).toHaveTextContent('Listening with browser speech recognition');
    expect(recognition?.start).toHaveBeenCalledOnce();

    act(() => {
      recognition?.onresult?.({
        results: [{ 0: { transcript: 'Check my schedule' }, isFinal: true }],
      });
    });
    expect(screen.getByPlaceholderText('Message JARVIS...')).toHaveValue('Check my schedule');

    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
    expect(onSend).toHaveBeenCalledWith('Check my schedule');
  });

  it('reports when browser speech recognition is unavailable', () => {
    render(<ChatInput onSend={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Start voice input' }));

    expect(screen.getByRole('alert')).toHaveTextContent('not supported by this browser');
  });
});
