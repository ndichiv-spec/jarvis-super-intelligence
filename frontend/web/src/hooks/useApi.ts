'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import type { AsyncStatus } from '@/types';

interface UseApiState<T> {
  data: T | null;
  status: AsyncStatus;
  error: string | null;
}

interface UseApiReturn<T> extends UseApiState<T> {
  execute: (...args: any[]) => Promise<T | undefined>;
  reset: () => void;
  setData: (data: T | null) => void;
}

export function useApi<T>(
  apiFunction: (...args: any[]) => Promise<T>,
  immediate = false,
  initialArgs: any[] = []
): UseApiReturn<T> {
  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    status: 'idle',
    error: null,
  });

  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const execute = useCallback(async (...args: any[]): Promise<T | undefined> => {
    setState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const result = await apiFunction(...args);
      if (mountedRef.current) {
        setState({ data: result, status: 'success', error: null });
      }
      return result;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'An error occurred';
      if (mountedRef.current) {
        setState((prev) => ({ ...prev, status: 'error', error: errorMessage }));
      }
      return undefined;
    }
  }, [apiFunction]);

  const reset = useCallback(() => {
    setState({ data: null, status: 'idle', error: null });
  }, []);

  const setData = useCallback((data: T | null) => {
    setState((prev) => ({ ...prev, data }));
  }, []);

  useEffect(() => {
    if (immediate) {
      execute(...initialArgs);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return { ...state, execute, reset, setData };
}

export function useApiLazy<T>(apiFunction: (...args: any[]) => Promise<T>) {
  return useApi<T>(apiFunction, false);
}

export default useApi;
