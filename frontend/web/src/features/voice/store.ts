import { create } from 'zustand';
import type { VoiceProfile, VoiceStatus } from './types';
import voiceApi from './api';

interface VoiceState {
  status: VoiceStatus | null;
  profiles: VoiceProfile[];
  availableVoices: string[];
  isSpeaking: boolean;
  isListening: boolean;
  transcript: string | null;
  isLoading: boolean;
  error: string | null;

  speak: (text: string) => Promise<void>;
  listen: () => Promise<void>;
  loadStatus: () => Promise<void>;
  loadProfiles: () => Promise<void>;
  loadVoices: () => Promise<void>;
  createProfile: (name: string) => Promise<void>;
  clearTranscript: () => void;
  clearError: () => void;
}

export const useVoiceStore = create<VoiceState>((set, get) => ({
  status: null,
  profiles: [],
  availableVoices: [],
  isSpeaking: false,
  isListening: false,
  transcript: null,
  isLoading: false,
  error: null,

  speak: async (text: string) => {
    set({ isSpeaking: true, error: null });
    try {
      await voiceApi.speak(text);
      set({ isSpeaking: false });
    } catch (error) {
      set({ isSpeaking: false, error: error instanceof Error ? error.message : 'Speech failed' });
    }
  },

  listen: async () => {
    set({ isListening: true, error: null });
    try {
      const result = await voiceApi.listen();
      set({ isListening: false, transcript: result.text || null });
    } catch (error) {
      set({ isListening: false, error: error instanceof Error ? error.message : 'Listening failed' });
    }
  },

  loadStatus: async () => {
    try {
      const status = await voiceApi.getStatus();
      set({ status });
    } catch {
      // silent
    }
  },

  loadProfiles: async () => {
    try {
      const data = await voiceApi.listProfiles();
      set({ profiles: data.profiles || [] });
    } catch {
      // silent
    }
  },

  loadVoices: async () => {
    try {
      const data = await voiceApi.getVoices();
      set({ availableVoices: data.voices || [] });
    } catch {
      // silent
    }
  },

  createProfile: async (name: string) => {
    try {
      await voiceApi.createProfile(name);
      get().loadProfiles();
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to create profile' });
    }
  },

  clearTranscript: () => set({ transcript: null }),

  clearError: () => set({ error: null }),
}));

export default useVoiceStore;
