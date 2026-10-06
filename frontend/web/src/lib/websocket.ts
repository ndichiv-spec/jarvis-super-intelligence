import { useEffect, useRef, useCallback } from 'react';
import { toast } from 'sonner';
import { getWsUrl } from './runtime-url';
import { jarvisAPI } from './api';

interface WebSocketMessage {
  type: string;
  data: any;
  timestamp?: string;
}

interface UseWebSocketOptions {
  onMessage?: (message: WebSocketMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
  reconnectAttempts?: number;
  reconnectInterval?: number;
  autoReconnect?: boolean;
}

export function useWebSocket(url: string, options: UseWebSocketOptions = {}) {
  const {
    onMessage,
    onConnect,
    onDisconnect,
    onError,
    reconnectAttempts = 5,
    reconnectInterval = 3000,
    autoReconnect = true,
  } = options;

  const ws = useRef<WebSocket | null>(null);
  const reconnectCount = useRef(0);
  const reconnectTimer = useRef<NodeJS.Timeout | null>(null);
  const isConnected = useRef(false);
  const connectionAttempt = useRef(0);

  const connect = useCallback(() => {
    const attemptId = ++connectionAttempt.current;
    ws.current?.close();

    const fullUrl = getWsUrl(url);

    void jarvisAPI.openAuthenticatedWebSocket(fullUrl).then((socket) => {
      if (attemptId !== connectionAttempt.current) {
        socket.close();
        return;
      }
      ws.current = socket;

      socket.onopen = () => {
        if (attemptId !== connectionAttempt.current) return;
        console.log('WebSocket connected');
        isConnected.current = true;
        reconnectCount.current = 0;
        onConnect?.();
        toast.success('Real-time updates connected', {
          description: 'Live monitoring active',
        });
      };

      socket.onmessage = (event) => {
        if (attemptId !== connectionAttempt.current) return;
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          onMessage?.(message);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      socket.onclose = (event) => {
        if (attemptId !== connectionAttempt.current) return;
        console.log('WebSocket disconnected', event.code, event.reason);
        isConnected.current = false;
        onDisconnect?.();

        // Auto-reconnect
        if (autoReconnect && reconnectCount.current < reconnectAttempts) {
          reconnectCount.current++;
          console.log(`Reconnecting... (${reconnectCount.current}/${reconnectAttempts})`);
          
          reconnectTimer.current = setTimeout(() => {
            connect();
          }, reconnectInterval);
        } else if (reconnectCount.current >= reconnectAttempts) {
          toast.error('Connection lost', {
            description: 'Failed to reconnect after multiple attempts',
          });
        }
      };

      socket.onerror = (error) => {
        if (attemptId !== connectionAttempt.current) return;
        console.error('WebSocket error:', error);
        onError?.(error);
      };
    }).catch((error) => {
      if (attemptId !== connectionAttempt.current) return;
      console.error('Failed to create authenticated WebSocket connection:', error);
      onError?.(new Event('error'));
      if (autoReconnect && reconnectCount.current < reconnectAttempts) {
        reconnectCount.current++;
        reconnectTimer.current = setTimeout(connect, reconnectInterval);
      }
    });
  }, [url, onMessage, onConnect, onDisconnect, onError, autoReconnect, reconnectAttempts, reconnectInterval]);

  const disconnect = useCallback(() => {
    connectionAttempt.current++;
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    
    if (ws.current) {
      ws.current.close();
      ws.current = null;
    }
    
    isConnected.current = false;
  }, []);

  const send = useCallback((data: any) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(data));
    } else {
      console.warn('WebSocket is not connected');
    }
  }, []);

  useEffect(() => {
    connect();

    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    isConnected: isConnected.current,
    send,
    disconnect,
    reconnect: connect,
  };
}

// Health-specific WebSocket hook
export function useHealthWebSocket(onHealthUpdate: (health: any) => void) {
  return useWebSocket('/ws/health', {
    onMessage: (message) => {
      if (message.type === 'health_update') {
        onHealthUpdate(message.data);
      }
    },
    onConnect: () => {
      console.log('Health monitoring WebSocket connected');
    },
    reconnectAttempts: 10,
    reconnectInterval: 5000,
  });
}

// Agent status WebSocket hook
export function useAgentWebSocket(onAgentUpdate: (agents: any) => void) {
  return useWebSocket('/ws/agents', {
    onMessage: (message) => {
      if (message.type === 'agent_status') {
        onAgentUpdate(message.data);
      }
    },
    reconnectAttempts: 5,
    reconnectInterval: 3000,
  });
}
