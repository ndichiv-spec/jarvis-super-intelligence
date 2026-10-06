import { create } from 'zustand';
import { ChatMessage } from '@/lib/api';
import { io, Socket } from 'socket.io-client';
import { getWsUrl } from '@/lib/runtime-url';

interface ChatState {
  messages: ChatMessage[];
  isLoading: boolean;
  isStreaming: boolean;
  streamingContent: string;
  socket: Socket | null;
  connected: boolean;

  addMessage: (message: ChatMessage) => void;
  setMessages: (messages: ChatMessage[]) => void;
  setLoading: (loading: boolean) => void;
  setStreaming: (streaming: boolean) => void;
  updateStreamingContent: (content: string) => void;
  clearChat: () => void;
  connectWebSocket: () => void;
  disconnectWebSocket: () => void;
  sendWebSocketMessage: (message: string) => void;
}

const WS_URL = getWsUrl('/ws/chat');

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isLoading: false,
  isStreaming: false,
  streamingContent: '',
  socket: null,
  connected: false,

  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),

  setMessages: (messages) => set({ messages }),

  setLoading: (loading) => set({ isLoading: loading }),

  setStreaming: (streaming) => set({ isStreaming: streaming }),

  updateStreamingContent: (content) => set({ streamingContent: content }),

  clearChat: () => set({ messages: [], streamingContent: '' }),

  connectWebSocket: () => {
    const socket = io(WS_URL, {
      path: '/ws/chat',
      transports: ['websocket'],
    });

    socket.on('connect', () => {
      set({ connected: true, socket });
    });

    socket.on('disconnect', () => {
      set({ connected: false, socket: null });
    });

    socket.on('typing', (data: any) => {
      set({ isStreaming: true, streamingContent: '' });
    });

    socket.on('chunk', (data: any) => {
      set((state) => ({
        streamingContent: state.streamingContent + (data.content || ''),
      }));
    });

    socket.on('complete', (data: any) => {
      set((state) => ({
        isStreaming: false,
        streamingContent: '',
        messages: [
          ...state.messages,
          {
            role: 'assistant',
            content: data.content || state.streamingContent,
            timestamp: new Date().toISOString(),
            confidence: data.confidence,
            sources: data.sources,
            tool_calls: data.tool_calls,
          },
        ],
      }));
    });

    set({ socket });
  },

  disconnectWebSocket: () => {
    const { socket } = get();
    if (socket) {
      socket.disconnect();
      set({ socket: null, connected: false });
    }
  },

  sendWebSocketMessage: (message: string) => {
    const { socket } = get();
    if (socket && socket.connected) {
      socket.send(JSON.stringify({ type: 'message', content: message }));
    }
  },
}));
