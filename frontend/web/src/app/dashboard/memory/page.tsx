'use client';

import { MemoryInspector } from '@/components/memory/memory-inspector';

export default function MemoryPage() {
  return (
    <div className="h-full overflow-auto p-6">
      <div className="mx-auto max-w-6xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Memory Inspector</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Inspect, search, and manage JARVIS memory layers
          </p>
        </div>
        <MemoryInspector />
      </div>
    </div>
  );
}
