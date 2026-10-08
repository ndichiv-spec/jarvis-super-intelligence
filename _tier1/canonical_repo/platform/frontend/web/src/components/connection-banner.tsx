'use client';

import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Wifi, WifiOff, AlertTriangle } from 'lucide-react';
import { getApiBaseUrl } from '@/lib/api';

export function ConnectionBanner() {
  const [connectionError, setConnectionError] = useState<string | null>(null);

  useEffect(() => {
    const checkConnection = async () => {
      try {
        const apiBase = getApiBaseUrl();
        const response = await fetch(`${apiBase}/health`, {
          method: 'GET',
          headers: { 'Cache-Control': 'no-cache' },
        });
        
        setConnectionError(
          response.ok
            ? null
            : `Backend health check returned HTTP ${response.status}. Retrying automatically every 10 seconds.`,
        );
      } catch {
        setConnectionError('Backend is unreachable. Retrying automatically every 10 seconds.');
      }
    };

    // Check immediately
    checkConnection();

    // Check every 10 seconds
    const interval = setInterval(checkConnection, 10000);

    return () => clearInterval(interval);
  }, []);

  return (
    <AnimatePresence>
      {connectionError && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          role="alert"
          aria-live="assertive"
          className="relative z-20 border-b border-rose-200/10 bg-rose-950/50"
        >
          <div className="mx-auto flex max-w-[1680px] items-center gap-2 px-4 py-2 sm:px-6">
            <AlertTriangle aria-hidden="true" className="h-4 w-4 shrink-0 text-rose-200" />
            <p className="text-xs leading-relaxed text-rose-100 sm:text-sm">
              {connectionError}
            </p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function ConnectionIndicator() {
  const [isConnected, setIsConnected] = useState<boolean | null>(null);

  useEffect(() => {
    const checkConnection = async () => {
      try {
        const apiBase = getApiBaseUrl();
        const response = await fetch(`${apiBase}/health`, {
          method: 'GET',
          headers: { 'Cache-Control': 'no-cache' },
        });
        setIsConnected(response.ok);
      } catch {
        setIsConnected(false);
      }
    };
    checkConnection();
    const interval = setInterval(checkConnection, 10000);
    return () => clearInterval(interval);
  }, []);

  return isConnected === null ? (
    <WifiOff aria-label="Backend connection status not verified" className="h-4 w-4 text-slate-500" />
  ) : isConnected ? (
    <Wifi className="h-4 w-4 text-emerald-500" />
  ) : (
    <WifiOff className="h-4 w-4 text-red-500" />
  );
}
