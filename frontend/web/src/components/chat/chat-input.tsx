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
            variant="ghost"
            size="icon"
            className="h-9 w-9 shrink-0 rounded-xl text-muted-foreground/50 hover:text-foreground"
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
        className="min-h-[36px] flex-1 resize-none border-0 bg-transparent px-1 py-1.5 text-sm text-foreground placeholder:text-muted-foreground/40 focus-visible:ring-0 focus-visible:ring-offset-0"
      />

      {isStreaming ? (
        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9 shrink-0 rounded-xl bg-red-500/10 text-red-400 hover:bg-red-500/20 hover:text-red-300"
          onClick={onStopStreaming}
        >
          <Square className="h-4 w-4" />
        </Button>
      ) : (
        <div className="flex items-center gap-1">
          {onStartVoice && (
            <Button
              variant="ghost"
              size="icon"
              className="h-9 w-9 shrink-0 rounded-xl text-muted-foreground/50 hover:text-foreground"
              onClick={onStartVoice}
              disabled={disabled}
            >
              <Mic className="h-4 w-4" />
            </Button>
          )}

          <Button
            size="icon"
            className="h-9 w-9 shrink-0 rounded-xl bg-gradient-to-r from-blue-500 to-cyan-500 text-white hover:from-blue-600 hover:to-cyan-600 disabled:opacity-40"
            onClick={handleSubmit}
            disabled={!input.trim() || disabled}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
