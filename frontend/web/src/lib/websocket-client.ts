import env from '@/config/env';
import { jarvisAPI } from '@/lib/api';

export type WsEventType =
  | 'chat_message'
  | 'chat_chunk'
  | 'chat_complete'
  | 'chat_typing'
  | 'health_update'
  | 'agent_status'
  | 'agent_update'
  | 'monitoring_update'
  | 'system_alert'
  | 'memory_update'
  | 'status_update'
  | 'components_update'
  | 'voice_transcript'
  | 'voice_command'
  | 'automation_event'
  | 'notification'
  | 'activity'
  | 'error'
  | 'connected'
  | 'disconnected'
  | 'reconnecting';

export interface WsEvent {
  type: WsEventType;
  data: unknown;
  timestamp: string;
  id?: string;
}

export type WsEventListener = (event: WsEvent) => void;

interface WsChannel {
  url: string;
  socket: WebSocket | null;
  listeners: Set<WsEventListener>;
  isConnected: boolean;
  connecting: boolean;
  reconnectAttempts: number;
  reconnectTimer: ReturnType<typeof setTimeout> | null;
  intentionalClose: boolean;
}

const CHANNELS = new Map<string, WsChannel>();

const DEFAULT_OPTIONS = {
  reconnectAttempts: env.WS_RECONNECT_ATTEMPTS,
  reconnectInterval: env.WS_RECONNECT_INTERVAL,
};

function createChannel(channelId: string, url: string): WsChannel {
  return {
    url,
    socket: null,
    listeners: new Set(),
    isConnected: false,
    connecting: false,
    reconnectAttempts: 0,
    reconnectTimer: null,
    intentionalClose: false,
  };
}

function getChannelId(endpoint: string): string {
  return endpoint;
}

function notifyChannel(channel: WsChannel, event: WsEvent) {
  channel.listeners.forEach((listener) => {
    try {
      listener(event);
    } catch (error) {
      console.error(`[WS] Listener error for ${channel.url}:`, error);
    }
  });
}

async function connectChannel(channel: WsChannel, channelId: string) {
  if (channel.socket && (channel.socket.readyState === WebSocket.OPEN || channel.socket.readyState === WebSocket.CONNECTING)) {
    return;
  }
  if (channel.connecting || channel.intentionalClose) return;

  channel.connecting = true;
  try {
    const socket = await jarvisAPI.openAuthenticatedWebSocket(channel.url);
    channel.connecting = false;
    if (channel.intentionalClose) {
      socket.close();
      return;
    }
    channel.socket = socket;

    socket.onopen = () => {
      channel.isConnected = true;
      channel.reconnectAttempts = 0;
      notifyChannel(channel, {
        type: 'connected',
        data: { url: channel.url },
        timestamp: new Date().toISOString(),
      });
    };

    socket.onmessage = (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data);
        const wsEvent: WsEvent = {
          type: parsed.type || 'chat_message',
          data: parsed.data || parsed,
          timestamp: parsed.timestamp || new Date().toISOString(),
          id: parsed.id,
        };
        notifyChannel(channel, wsEvent);
      } catch {
        notifyChannel(channel, {
          type: 'chat_message',
          data: event.data,
          timestamp: new Date().toISOString(),
        });
      }
    };

    socket.onclose = () => {
      channel.isConnected = false;
      if (!channel.intentionalClose) {
        notifyChannel(channel, {
          type: 'disconnected',
          data: { url: channel.url },
          timestamp: new Date().toISOString(),
        });
        attemptReconnect(channel, channelId);
      }
    };

    socket.onerror = (error: Event) => {
      notifyChannel(channel, {
        type: 'error',
        data: { message: 'WebSocket error', url: channel.url },
        timestamp: new Date().toISOString(),
      });
    };
  } catch (error) {
    channel.connecting = false;
    console.error(`[WS] Failed to create connection to ${channel.url}:`, error);
    attemptReconnect(channel, channelId);
  }
}

function attemptReconnect(channel: WsChannel, channelId: string) {
  if (channel.intentionalClose) return;

  if (channel.reconnectAttempts >= DEFAULT_OPTIONS.reconnectAttempts) {
    notifyChannel(channel, {
      type: 'error',
      data: { message: `Max reconnection attempts reached for ${channel.url}` },
      timestamp: new Date().toISOString(),
    });
    return;
  }

  channel.reconnectAttempts++;
  const delay = DEFAULT_OPTIONS.reconnectInterval * Math.pow(1.5, channel.reconnectAttempts - 1);

  notifyChannel(channel, {
    type: 'reconnecting',
    data: { attempt: channel.reconnectAttempts, maxAttempts: DEFAULT_OPTIONS.reconnectAttempts, delay },
    timestamp: new Date().toISOString(),
  });

  channel.reconnectTimer = setTimeout(() => {
    void connectChannel(channel, channelId);
  }, delay);
}

export const wsClient = {
  subscribe(channelEndpoint: string, listener: WsEventListener): () => void {
    const channelId = getChannelId(channelEndpoint);

    if (!CHANNELS.has(channelId)) {
      const channel = createChannel(channelId, channelEndpoint);
      CHANNELS.set(channelId, channel);
      void connectChannel(channel, channelId);
    }

    const channel = CHANNELS.get(channelId)!;
    channel.listeners.add(listener);

    return () => {
      channel.listeners.delete(listener);
      if (channel.listeners.size === 0) {
        channel.intentionalClose = true;
        if (channel.socket) {
          channel.socket.close();
        }
        if (channel.reconnectTimer) {
          clearTimeout(channel.reconnectTimer);
        }
        CHANNELS.delete(channelId);
      }
    };
  },

  send(channelEndpoint: string, data: unknown) {
    const channelId = getChannelId(channelEndpoint);
    const channel = CHANNELS.get(channelId);
    if (channel?.socket?.readyState === WebSocket.OPEN) {
      channel.socket.send(JSON.stringify(data));
    }
  },

  disconnect(channelEndpoint: string) {
    const channelId = getChannelId(channelEndpoint);
    const channel = CHANNELS.get(channelId);
    if (channel) {
      channel.intentionalClose = true;
      if (channel.reconnectTimer) clearTimeout(channel.reconnectTimer);
      if (channel.socket) channel.socket.close();
      CHANNELS.delete(channelId);
    }
  },

  disconnectAll() {
    CHANNELS.forEach((channel, channelId) => {
      channel.intentionalClose = true;
      if (channel.reconnectTimer) clearTimeout(channel.reconnectTimer);
      if (channel.socket) channel.socket.close();
    });
    CHANNELS.clear();
  },

  isConnected(channelEndpoint: string): boolean {
    const channelId = getChannelId(channelEndpoint);
    return CHANNELS.get(channelId)?.isConnected ?? false;
  },

  connectionState(channelEndpoint: string): 'connected' | 'disconnected' | 'reconnecting' | 'unknown' {
    const channelId = getChannelId(channelEndpoint);
    const channel = CHANNELS.get(channelId);
    if (!channel) return 'unknown';
    if (channel.isConnected) return 'connected';
    if (channel.connecting) return 'reconnecting';
    if (channel.reconnectAttempts > 0) return 'reconnecting';
    return 'disconnected';
  },
};

export default wsClient;
