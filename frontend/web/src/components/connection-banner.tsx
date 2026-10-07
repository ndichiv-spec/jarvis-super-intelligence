'use client';

import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Wifi, WifiOff, AlertTriangle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { getApiBaseUrl } from '@/lib/api';

export function ConnectionBanner() {
  const [isConnected, setIsConnected] = useState(true);
  const [showBanner, setShowBanner] = useState(false);

  useEffect(() => {
    const checkConnection = async () => {
      try {
        const apiBase = getApiBaseUrl();
        const response = await fetch(`${apiBase}/health`, {
          method: 'GET',
          headers: { 'Cache-Control': 'no-cache' },
        });
        
        const connected = response.ok;
        setIsConnected(connected);
        
        if (!connected) {
          setShowBanner(true);
        } else {
          // Hide banner after successful reconnection
          setTimeout(() => setShowBanner(false), 3000);
        }
      } catch (error) {
        setIsConnected(false);
        setShowBanner(true);
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
      {showBanner && (
        <motion.div
          initial={{ opacity: 0, y: -50 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -50 }}
          className={`fixed top-0 left-0 right-0 z-50 p-3 ${
            isConnected 
              ? 'bg-gradient-to-r from-emerald-500/90 to-green-500/90' 
              : 'bg-gradient-to-r from-red-500/90 to-orange-500/90'
          } backdrop-blur-xl border-b border-white/20`}
        >
          <div className="container mx-auto flex items-center justify-center gap-3">
            {isConnected ? (
              <>
                <Wifi className="h-5 w-5 text-white" />
                <span className="text-sm font-semibold text-white">
                  Connection Restored - Backend API reachable
                </span>
              </>
            ) : (
              <>
                <AlertTriangle className="h-5 w-5 text-white" />
                <span className="text-sm font-semibold text-white">
                  Backend Connection Lost - Retrying automatically...
                </span>
                <Badge variant="outline" className="bg-white/20 text-white border-white/30">
                  Offline
                </Badge>
              </>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function ConnectionIndicator() {
  const [isConnected, setIsConnected] = useState(true);

  useEffect(() => {
    const checkConnection = async () => {
      try {
        const apiBase = getApiBaseUrl();
        const response = await fetch(`${apiBase}/health`, {
          method: 'GET',
          headers: { 'Cache-Control': 'no-cache' },
        });
        setIsConnected(response.ok);
      } catch (error) {
        setIsConnected(false);
      }
    };
    checkConnection();
    const interval = setInterval(checkConnection, 10000);
    return () => clearInterval(interval);
  }, []);

  return isConnected ? (
    <Wifi className="h-4 w-4 text-emerald-500" />
  ) : (
    <WifiOff className="h-4 w-4 text-red-500" />
  );
}
