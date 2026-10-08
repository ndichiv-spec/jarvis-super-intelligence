'use client';

import { useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { usePlatformStore } from '@/stores/platform-store';

/**
 * Navigation context manager — enables context-preserving navigation.
 *
 * Usage (at the top of any dashboard page):
 *   useNavigationContext('research', {
 *     sessionId: activeSession?.id,
 *     query: searchQuery,
 *     selectedEvidence: evidence?.id,
 *   });
 *
 * When the user navigates away and returns, the previously saved context
 * is restored so they don't lose their working state.
 */
export function useNavigationContext(
  resourceType: string,
  context: Record<string, unknown>
) {
  const pathname = usePathname();
  const saveContext = usePlatformStore((s) => s.saveNavigationContext);
  const getContext = usePlatformStore((s) => s.getNavigationContext);

  // Save context on unmount (when navigating away from this page)
  useEffect(() => {
    return () => {
      saveContext(pathname, { resourceType, ...context });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]); // eslint-disable-line

  // Allow pages to read the previously saved context on mount
  const savedContext = getContext(pathname);
  const prevRef = useRef<Record<string, unknown> | null>(savedContext);
  if (savedContext && prevRef.current !== savedContext) {
    prevRef.current = savedContext;
  }
  return prevRef.current;
}

/**
 * Convenience: save the current path + context and restore it on return.
 * Returns the previously saved context (if any) and a setter to update it.
 */
export function usePageContext<T extends Record<string, unknown>>(
  key: string,
  defaultValue: T
): [T, (update: Partial<T>) => void] {
  const pathname = usePathname();
  const saveContext = usePlatformStore((s) => s.saveNavigationContext);
  const getContext = usePlatformStore((s) => s.getNavigationContext);

  const saved = getContext(pathname);
  const merged: T = { ...defaultValue, ...((saved?.[key] as T) ?? {}) };

  // Save on unmount
  useEffect(() => {
    return () => {
      const current: Record<string, unknown> = {};
      for (const k of Object.keys(merged)) {
        current[k] = (merged as any)[k];
      }
      saveContext(pathname, { [key]: current });
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  const update = (patch: Partial<T>) => {
    Object.assign(merged, patch);
  };

  return [merged, update];
}
