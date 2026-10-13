'use client';

import { ChatWindow } from '@/components/chat/chat-window';

export default function ChatPage() {
  return (
    <section
      aria-label="JARVIS conversation"
      className="mx-auto h-[calc(100dvh-4rem)] min-h-[32rem] w-full max-w-6xl px-3 py-3 sm:px-5 sm:py-4"
    >
      <ChatWindow className="overflow-hidden rounded-xl border border-white/[0.09] bg-[#0b111b]" />
    </section>
  );
}
