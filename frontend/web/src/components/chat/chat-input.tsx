'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Mic, MicOff, Square, Paperclip } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useJarvisRuntime } from '@/features/runtime/store';

interface SpeechRecognitionResultLike {
  readonly isFinal: boolean;
  readonly [index: number]: { readonly transcript: string };
}

interface SpeechRecognitionEventLike {
  readonly resultIndex: number;
  readonly results: ArrayLike<SpeechRecognitionResultLike>;
}

interface SpeechRecognitionErrorLike {
  readonly error: string;
}

interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognitionLike;
}

interface ChatInputProps {
  onSend: (message: string) => void;
  onFileAttach?: (file: File) => void;
  disabled?: boolean;
  isStreaming?: boolean;
  onStopStreaming?: () => void;
  placeholder?: string;
}

export function ChatInput({
  onSend,
  onFileAttach,
  disabled = false,
  isStreaming = false,
  onStopStreaming,
  placeholder = 'Message JARVIS...',
}: ChatInputProps) {
  const [input, setInput] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const setVoiceState = useJarvisRuntime((state) => state.setVoiceState);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const voiceBaseRef = useRef('');

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
    }
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [input, adjustHeight]);

  useEffect(() => () => {
    recognitionRef.current?.abort();
    recognitionRef.current = null;
    if (useJarvisRuntime.getState().voiceState === 'listening') {
      useJarvisRuntime.getState().setVoiceState('idle');
    }
  }, []);

  const toggleVoiceInput = useCallback(() => {
    if (isListening) {
      recognitionRef.current?.stop();
      return;
    }

    const speechWindow = window as Window & {
      SpeechRecognition?: SpeechRecognitionConstructor;
      webkitSpeechRecognition?: SpeechRecognitionConstructor;
    };
    const SpeechRecognition = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setVoiceError('Voice input is not supported by this browser. You can still type your message.');
      setVoiceState('unavailable');
      return;
    }

    setVoiceError(null);
    voiceBaseRef.current = input.trim();
    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = navigator.language || 'en-US';
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0].transcript)
        .join(' ')
        .trim();
      const combined = [voiceBaseRef.current, transcript].filter(Boolean).join(' ');
      setInput(combined);
    };
    recognition.onerror = (event) => {
      setIsListening(false);
      setVoiceState('error');
      setVoiceError(
        event.error === 'not-allowed'
          ? 'Microphone permission was denied.'
          : `Browser voice recognition failed (${event.error}).`,
      );
    };
    recognition.onend = () => {
      setIsListening(false);
      if (useJarvisRuntime.getState().voiceState === 'listening') {
        useJarvisRuntime.getState().setVoiceState('idle');
      }
    };
    recognitionRef.current = recognition;

    try {
      recognition.start();
      setIsListening(true);
      setVoiceState('listening');
    } catch (error) {
      recognitionRef.current = null;
      setVoiceState('error');
      setVoiceError(error instanceof Error ? error.message : 'Unable to start browser voice recognition.');
    }
  }, [input, isListening, setVoiceState]);

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || disabled || isStreaming) return;
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      setVoiceState('processing');
    }
    onSend(trimmed);
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [input, disabled, isListening, isStreaming, onSend, setVoiceState]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onFileAttach) {
      onFileAttach(file);
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="space-y-1 rounded-xl border border-white/[0.1] bg-[#0c131f] p-2 transition-colors focus-within:border-indigo-300/30 focus-within:bg-[#0e1623]">
      <div className="flex items-end gap-2">
      {onFileAttach && (
        <>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Attach a file"
            className="h-10 w-10 shrink-0 rounded-lg text-slate-500 hover:bg-white/[0.05] hover:text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-300"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
          >
            <Paperclip className="h-4 w-4" />
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={handleFileSelect}
          />
        </>
      )}

      <Textarea
        ref={textareaRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        rows={1}
        className="min-h-10 flex-1 resize-none border-0 bg-transparent px-2 py-2 text-sm leading-5 text-slate-100 placeholder:text-slate-500 focus-visible:ring-0 focus-visible:ring-offset-0"
      />

      {isStreaming ? (
        <Button
          variant="ghost"
          size="icon"
          aria-label="Stop response"
          title="Stop response"
          className="h-10 w-10 shrink-0 rounded-lg bg-rose-400/10 text-rose-200 hover:bg-rose-400/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-rose-200"
          onClick={onStopStreaming}
        >
          <Square className="h-4 w-4" />
        </Button>
      ) : (
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={`h-10 w-10 shrink-0 rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-300 ${isListening ? 'text-rose-200 hover:bg-rose-400/10 hover:text-rose-100' : 'text-slate-500 hover:bg-white/[0.05] hover:text-slate-100'}`}
            onClick={toggleVoiceInput}
            disabled={disabled}
            aria-label={isListening ? 'Stop voice input' : 'Start voice input'}
            aria-pressed={isListening}
            title="Use browser speech recognition (not JARVIS transcription)"
          >
            {isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
          </Button>

          <Button
            size="icon"
            className="h-10 w-10 shrink-0 rounded-lg bg-indigo-400 text-[#0a0e16] hover:bg-indigo-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-200 disabled:bg-white/10 disabled:text-slate-500"
            onClick={handleSubmit}
            disabled={!input.trim() || disabled}
            aria-label="Send message"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      )}
      </div>
      {isListening && (
        <p role="status" className="px-2 pb-1 text-xs text-red-300">
          Listening with browser speech recognition. Select Stop, then Send to submit the transcript.
        </p>
      )}
      {voiceError && (
        <p role="alert" className="px-2 pb-1 text-xs text-amber-300">
          {voiceError}
        </p>
      )}
    </div>
  );
}
