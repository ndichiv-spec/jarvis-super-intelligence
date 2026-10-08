'use client';

import { useEffect, useCallback, useState } from 'react';
import wsClient, { type WsEvent, type WsEventType } from '@/lib/websocket-client';
import { getWsBaseUrl } from '@/lib/api';

export function useWebSocketSubscription(
  endpoint: string,
  eventTypes?: WsEventType[],
  handler?: (event: WsEvent) => void,
  deps: unknown[] = []
) {
  const eventSet = new Set(eventTypes ?? []);
  const [lastMessage, setLastMessage] = useState<WsEvent | null>(null);

  const listener = useCallback((event: WsEvent) => {
    setLastMessage(event);
    if (eventSet.has(event.type)) {
      handler?.(event);
    }
  }, [eventSet, ...deps]);

  useEffect(() => {
    const unsubscribe = wsClient.subscribe(endpoint, listener);
    return unsubscribe;
  }, [endpoint, listener]);

  return {
    send: (data: unknown) => wsClient.send(endpoint, data),
    isConnected: wsClient.isConnected(endpoint),
    connectionState: wsClient.connectionState(endpoint),
    lastMessage,
  };
}

/**
 * Get the WebSocket URL for an endpoint, using the configured base URL
 */
function getWsEndpoint(endpoint: string): string {
  const wsBase = getWsBaseUrl();
  return `${wsBase}${endpoint}`;
}

export function useHealthWebSocket(onHealthUpdate: (data: any) => void) {
  return useWebSocketSubscription(
    getWsEndpoint('/ws/health'),
    ['health_update'],
    (event) => onHealthUpdate(event.data),
    [onHealthUpdate]
  );
}

export function useAgentWebSocket(onAgentUpdate: (data: any) => void) {
  return useWebSocketSubscription(
    getWsEndpoint('/ws/agents'),
    ['agent_status', 'agent_update'],
    (event) => onAgentUpdate(event.data),
    [onAgentUpdate]
  );
}

export function useMonitoringWebSocket(onMonitoringUpdate: (data: any) => void) {
  return useWebSocketSubscription(
    getWsEndpoint('/ws/monitoring'),
    ['monitoring_update', 'health_update', 'system_alert'],
    (event) => onMonitoringUpdate(event.data),
    [onMonitoringUpdate]
  );
}

export { wsClient } from '@/lib/websocket-client';
