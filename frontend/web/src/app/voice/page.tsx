import { ChatWindow } from '@/components/chat/chat-window';

export default function VoicePage() {
  return (
    <main className="flex h-[100svh] min-h-[32rem] flex-col bg-background">
      <header className="border-b border-white/5 px-5 py-3">
        <h1 className="text-sm font-semibold text-foreground">JARVIS Voice Conversation</h1>
        <p className="mt-1 text-xs text-muted-foreground">
          Voice input and spoken replies use your browser and share the authenticated chat history.
        </p>
      </header>
      <div className="min-h-0 flex-1">
        <ChatWindow showSidebar />
      </div>
    </main>
  );
}
