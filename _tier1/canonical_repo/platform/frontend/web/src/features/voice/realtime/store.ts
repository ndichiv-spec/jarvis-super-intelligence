import { create } from 'zustand';
import { getVoiceEngine, destroyVoiceEngine } from './voiceEngine';
import type { VoiceEngineState } from './types';

interface RealtimeVoiceState {
  voiceEngine: ReturnType<typeof getVoiceEngine> | null;
  voiceState: VoiceEngineState;
  connected: boolean;
  transcript: string | null;
  listening: boolean;
  speaking: boolean;
  thinking: boolean;
  processing: boolean;
  audioLevel: number;
  micAvailable: boolean;
  speakersAvailable: boolean;
  barData: Float32Array | null;
  error: string | null;
  profileName: string | null;
  initEngine: () => void;
  destroyEngine: () => void;
  toggleRecording: () => void;
  setVoiceState: (s: VoiceEngineState) => void;
  setTranscript: (t: string) => void;
  setSpeaking: (v: boolean) => void;
  setThinking: (v: boolean) => void;
  setProcessing: (v: boolean) => void;
  setListening: (v: boolean) => void;
  setError: (e: string | null) => void;
  clearError: () => void;
  setAudioLevel: (l: number) => void;
  setMicAvailable: (v: boolean) => void;
  setSpeakersAvailable: (v: boolean) => void;
  setBarData: (d: Float32Array) => void;
  setProfile: (n: string) => void;
  setAudioFrames: (c: number) => void;
}

export const useRealtimeVoiceStore = create<RealtimeVoiceState>((set, get) => ({
  voiceEngine: null,
  voiceState: 'idle',
  connected: false,
  transcript: null,
  listening: false,
  speaking: false,
  thinking: false,
  processing: false,
  audioLevel: 0,
  micAvailable: false,
  speakersAvailable: false,
  barData: null,
  error: null,
  profileName: null,

  initEngine: () => {
    const engine = getVoiceEngine();
    engine.onStateChange((s) => {
      set({ voiceState: s, listening: s === 'listening', speaking: s === 'speaking', thinking: s === 'thinking', processing: s === 'processing', error: s === 'error' ? 'Engine error' : null });
    });
    engine.onTranscript((t) => set({ transcript: t }));
    engine.onStreamData(() => set({ barData: new Float32Array(48) }));
    set({ voiceEngine: engine, micAvailable: true, speakersAvailable: true });
  },

  destroyEngine: () => {
    destroyVoiceEngine();
    set({ voiceEngine: null, voiceState: 'idle', connected: false });
  },

  toggleRecording: () => {
    const e = get().voiceEngine;
    if (!e) return;
    if (e.state === 'idle' || e.state === 'error') void e.start();
    else void e.stop();
  },

  setVoiceState: (s) => set({ voiceState: s }),
  setTranscript: (t) => set({ transcript: t }),
  setSpeaking: (v) => set({ speaking: v }),
  setThinking: (v) => set({ thinking: v }),
  setProcessing: (v) => set({ processing: v }),
  setListening: (v) => set({ listening: v }),
  setError: (e) => set({ error: e }),
  clearError: () => set({ error: null }),
  setAudioLevel: (l) => set({ audioLevel: l }),
  setMicAvailable: (v) => set({ micAvailable: v }),
  setSpeakersAvailable: (v) => set({ speakersAvailable: v }),
  setBarData: (d) => set({ barData: d }),
  setProfile: (n) => set({ profileName: n }),
  setAudioFrames: () => {},
}));