'use client';

import { ChatWorkspace } from '@/components/chat/chat-workspace';
import { AuthGuard } from '@/components/auth/auth-guard';

export default function Home() {
  return (
    <AuthGuard>
      <div className="h-dvh min-h-0 overflow-hidden">
        <ChatWorkspace />
      </div>
    </AuthGuard>
  );
}
