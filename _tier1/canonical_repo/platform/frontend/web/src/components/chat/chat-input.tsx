'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Mic, Square, Paperclip } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

interface ChatInputProps {
  onSend: (message: string) => void;
  onStartVoice?: () => void;
  onFileAttach?: (file: File) => void;
  disabled?: boolean;
  isStreaming?: boolean;
  onStopStreaming?: () => void;
  placeholder?: string;
}

export function ChatInput({
  onSend,
  onStartVoice,
  onFileAttach,
  disabled = false,
  isStreaming = false,
  onStopStreaming,
  placeholder = 'Message JARVIS...',
}: ChatInputProps) {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || disabled || isStreaming) return;
    onSend(trimmed);
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [input, disabled, isStreaming, onSend]);

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
    <div className="flex items-end gap-2 rounded-2xl border border-white/10 bg-white/[0.03] p-2 transition-all focus-within:border-blue-500/40 focus-within:bg-white/[0.05]">
      {onFileAttach && (
        <>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Attach a file"
            className="h-9 w-9 shrink-0 rounded-xl text-slate-400 hover:text-foreground"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
          >
            <Paperclip aria-hidden="true" className="h-4 w-4" />
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
        aria-label="Message JARVIS"
        disabled={disabled}
        rows={1}
        className="min-h-[36px] min-w-0 flex-1 resize-none border-0 bg-transparent px-1 py-1.5 text-sm text-foreground placeholder:text-slate-400 focus-visible:ring-0 focus-visible:ring-offset-0"
      />

      {isStreaming ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Stop generating response"
          className="h-9 w-9 shrink-0 rounded-xl bg-rose-300/10 text-rose-200 hover:bg-rose-300/20 hover:text-rose-100"
          onClick={onStopStreaming}
        >
          <Square aria-hidden="true" className="h-4 w-4" />
        </Button>
      ) : (
        <div className="flex items-center gap-1">
          {onStartVoice && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Start voice input"
              className="h-9 w-9 shrink-0 rounded-xl text-slate-400 hover:text-foreground"
              onClick={onStartVoice}
              disabled={disabled}
            >
              <Mic aria-hidden="true" className="h-4 w-4" />
            </Button>
          )}

          <Button
            type="button"
            size="icon"
            aria-label="Send message"
            className="h-9 w-9 shrink-0 rounded-xl bg-cyan-200 text-slate-950 hover:bg-cyan-100 disabled:opacity-40"
            onClick={handleSubmit}
            disabled={!input.trim() || disabled}
          >
            <Send aria-hidden="true" className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
