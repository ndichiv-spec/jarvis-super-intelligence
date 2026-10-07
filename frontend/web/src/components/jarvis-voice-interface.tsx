'use client';

import { ChatWindow } from '@/components/chat/chat-window';

export default function JarvisVoiceInterface() {
  return (
    <section aria-label="Voice conversation" className="h-[min(72vh,56rem)] min-h-[32rem]">
      <ChatWindow showSidebar={false} />
    </section>
  );
}
