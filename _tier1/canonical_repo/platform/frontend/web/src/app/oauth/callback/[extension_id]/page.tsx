'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { toast } from 'sonner';

// Hit by the browser after a service redirects back to JARVIS's OAuth callback
// (which exchanges the code server-side and then 302-redirects here). This page
// shows the validation result and returns you to the extensions dashboard.
export default function OAuthCallbackPage({
  params,
}: {
  params: { extension_id: string };
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const connected = searchParams?.get('connected');
  const extId = params?.extension_id ?? 'extension';

  useEffect(() => {
    if (connected === '1') {
      toast.success(
        `JARVIS connected to ${extId} — capabilities are now active across the platform`,
      );
    } else {
      toast.error(`Connection to ${extId} was not completed — check that you granted access.`);
    }
    const t = setTimeout(() => router.replace('/dashboard/extensions'), 1500);
    return () => clearTimeout(t);
  }, [connected, extId, router]);

  return (
    <div className="flex-1 flex items-center justify-center min-h-[60vh]">
      <p className="text-muted-foreground">
        {connected === '1'
          ? `Connecting JARVIS to ${extId}…`
          : `Connecting JARVIS to ${extId} failed — check that you granted access.`}
      </p>
    </div>
  );
}
