import type {
  Audio as AudioToken,
  Voice as VoiceToken,
} from '@/lib/design-tokens';

/** All possible states of the realtime voice engine. */
export type VoiceEngineState =
  | 'idle'
  | 'connecting'
  | 'listening'
  | 'thinking'
  | 'processing'
  | 'speaking'
  | 'error';

/** A single captured audio frame with metadata used by VAD and the stream. */
export interface AudioFrame {
  /** PCM16 samples (mono, little-endian). */
  pcm: Int16Array;
  /** Timestamp in ms from AudioContext.currentTime. */
  timestamp: number;
  /** RMS energy of the frame, normalized to 0..1. */
  level: number;
  /** Duration of the frame in milliseconds. */
  durationMs: number;
}

/** A chunk of synthesized speech text and its (possibly streaming) audio. */
export interface TTSChunk {
  text: string;
  audio?: Uint8Array;
  done: boolean;
}

/** Configuration for the realtime voice engine. */
export interface VoiceEngineConfig {
  /** Number of frequency bins used for VAD energy (barCount from design tokens). */
  barCount: number;
  /** FFT size used by the analyser / frame splitter. */
  fftSize: number;
  /** Smoothing gain for the analyser. */
  smoothingGain: number;
  /** Milliseconds of silence after the last voiced frame before sending audio_end. */
  vadSilenceMs: number;
  /** RMS threshold for voice activity detection. */
  vadThreshold: number;
  /** Maximum transcription window length before sending audio_end. */
  maxTranscribeTimeMs: number;
  /** Microphone sample rate. */
  sampleRate: number;
  /** Number of audio channels (1 = mono). */
  channels: number;
}

/** Default configuration matching designTokens.audio and common STT/TTS needs. */
export const DEFAULT_ENGINE_CONFIG: VoiceEngineConfig = {
  barCount: 48,
  fftSize: 2048,
  smoothingGain: 0.78,
  vadSilenceMs: 1200,
  vadThreshold: 0.03,
  maxTranscribeTimeMs: 30000,
  sampleRate: 16000,
  channels: 1,
};

/** Event payloads emitted by VoiceEngine / VoiceStreamClient. */
export type VoiceEngineEvent =
  | { type: 'streamStart'; timestamp: number }
  | { type: 'streamData'; frame: AudioFrame }
  | { type: 'streamEnd'; transcript?: string; reason?: string }
  | { type: 'sttDone'; text: string; confidence: number; language?: string }
  | { type: 'ttsStart'; text: string }
  | { type: 'ttsChunk'; data: Uint8Array; partialText?: string }
  | { type: 'ttsEnd'; text: string; interrupted?: boolean }
  | { type: 'stateChanged'; state: VoiceEngineState; previous?: VoiceEngineState }
  | { type: 'audioLevel'; level: number }
  | { type: 'audioFrames'; count: number }
  | { type: 'barData'; data: Float32Array };

/** Typed event map for callbacks. */
export type VoiceEngineEvents = {
  streamStart: (e: Extract<VoiceEngineEvent, { type: 'streamStart' }>) => void;
  streamData: (e: Extract<VoiceEngineEvent, { type: 'streamData' }>) => void;
  streamEnd: (e: Extract<VoiceEngineEvent, { type: 'streamEnd' }>) => void;
  sttDone: (e: Extract<VoiceEngineEvent, { type: 'sttDone' }>) => void;
  ttsStart: (e: Extract<VoiceEngineEvent, { type: 'ttsStart' }>) => void;
  ttsChunk: (e: Extract<VoiceEngineEvent, { type: 'ttsChunk' }>) => void;
  ttsEnd: (e: Extract<VoiceEngineEvent, { type: 'ttsEnd' }>) => void;
  stateChanged: (e: Extract<VoiceEngineEvent, { type: 'stateChanged' }>) => void;
  audioLevel: (e: Extract<VoiceEngineEvent, { type: 'audioLevel' }>) => void;
  audioFrames: (e: Extract<VoiceEngineEvent, { type: 'audioFrames' }>) => void;
  barData: (e: Extract<VoiceEngineEvent, { type: 'barData' }>) => void;
};
