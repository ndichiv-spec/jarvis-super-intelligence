'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertTriangle, LoaderCircle, RefreshCw } from 'lucide-react';
import { onAuthError } from '@/lib/api-client';
import { clearAuthState, useAuthStore } from '@/stores/authStore';

interface AuthGuardProps {
  children: React.ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const router = useRouter();
  const authStatus = useAuthStore((state) => state.authStatus);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const user = useAuthStore((state) => state.user);
  const retrySessionCheck = useAuthStore((state) => state.retrySessionCheck);
  const handleConnectivityChange = useAuthStore((state) => state.handleConnectivityChange);
  const [persistHydrated, setPersistHydrated] = useState(false);

  const hasPersistedIdentity = isAuthenticated && Boolean(user);
  const shouldRedirect =
    authStatus === 'unauthenticated' ||
    (authStatus === 'authenticated' && !hasPersistedIdentity) ||
    (authStatus === 'unavailable' && !hasPersistedIdentity) ||
    (persistHydrated && !hasPersistedIdentity && (authStatus === 'idle' || authStatus === 'checking'));
  const canRender = hasPersistedIdentity && authStatus === 'authenticated';

  useEffect(() => {
    let hydrationTimer: number | undefined;
    const finishHydration = () => {
      setPersistHydrated(true);
      if (hydrationTimer !== undefined) window.clearTimeout(hydrationTimer);
    };
    const unsubscribe = useAuthStore.persist.onFinishHydration(finishHydration);

    if (useAuthStore.persist.hasHydrated()) {
      finishHydration();
    } else {
      hydrationTimer = window.setTimeout(() => {
        if (!useAuthStore.persist.hasHydrated()) {
          const state = useAuthStore.getState();
          if (state.isAuthenticated && state.user) {
            void state.retrySessionCheck();
          }
          finishHydration();
        }
      }, 1_000);
    }

    return () => {
      unsubscribe();
      if (hydrationTimer !== undefined) window.clearTimeout(hydrationTimer);
    };
  }, []);

  useEffect(() => {
    onAuthError(() => {
      clearAuthState();
      router.replace('/login');
    });
  }, [router]);

  useEffect(() => {
    if (shouldRedirect) {
      router.replace('/login');
    }
  }, [shouldRedirect, router]);

  useEffect(() => {
    const updateConnectivity = () => handleConnectivityChange(navigator.onLine);
    window.addEventListener('online', updateConnectivity);
    window.addEventListener('offline', updateConnectivity);
    if (!navigator.onLine) updateConnectivity();

    return () => {
      window.removeEventListener('online', updateConnectivity);
      window.removeEventListener('offline', updateConnectivity);
    };
  }, [handleConnectivityChange]);

  if (hasPersistedIdentity && (authStatus === 'checking' || authStatus === 'unavailable')) {
    const isRetrying = authStatus === 'checking';
    return (
      <main className="flex min-h-dvh items-center justify-center bg-background px-6 py-10">
        <section
          role={isRetrying ? 'status' : 'alert'}
          aria-live={isRetrying ? 'polite' : 'assertive'}
          className="w-full max-w-md border border-border/70 bg-card/70 p-6 shadow-xl shadow-black/10 sm:p-8"
        >
          <div className="mb-5 flex h-11 w-11 items-center justify-center border border-amber-400/25 bg-amber-400/10 text-amber-200">
            {isRetrying
              ? <LoaderCircle aria-hidden="true" className="h-5 w-5 animate-spin" />
              : <AlertTriangle aria-hidden="true" className="h-5 w-5" />}
          </div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Session verification
          </p>
          <h1 className="mt-2 text-xl font-semibold tracking-tight text-foreground">
            {isRetrying ? 'Checking your session' : 'We can’t verify your session'}
          </h1>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            {isRetrying
              ? 'Your workspace stays locked until the server confirms your sign-in.'
              : 'The session service is unavailable. Your workspace stays locked until your sign-in can be verified.'}
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void retrySessionCheck()}
              disabled={isRetrying}
              className="inline-flex min-h-10 items-center justify-center gap-2 border border-primary/40 bg-primary/10 px-4 text-sm font-medium text-foreground transition-colors hover:bg-primary/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-wait disabled:opacity-60"
            >
              <RefreshCw aria-hidden="true" className="h-4 w-4" />
              {isRetrying ? 'Verifying…' : 'Retry verification'}
            </button>
            <button
              type="button"
              onClick={() => {
                clearAuthState();
                router.replace('/login');
              }}
              className="inline-flex min-h-10 items-center justify-center border border-border px-4 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              Return to sign in
            </button>
          </div>
        </section>
      </main>
    );
  }

  if (!canRender) {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-background px-6">
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          {shouldRedirect ? 'Sign-in is required. Redirecting to login…' : 'Checking your session…'}
        </p>
      </main>
    );
  }

  return children;
}
