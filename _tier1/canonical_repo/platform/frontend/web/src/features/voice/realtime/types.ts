export type VoiceEngineState = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking' | 'processing' | 'error';

export interface AudioFrame {
  pcm: Int16Array;
  timestamp: number;
  level: number;
  durationMs: number;
}

export interface TTSChunk {
  text: string;
  audio?: Uint8Array;
  done: boolean;
}

export interface VoiceEngineConfig {
  barCount: number;
  fftSize: number;
  smoothingGain: number;
  vadSilenceMs: number;
  vadThreshold: number;
  maxTranscribeTimeMs: number;
  sampleRate: number;
  channels: number;
}

export const DEFAULT_VOICE_ENGINE_CONFIG: VoiceEngineConfig = {
  barCount: 48,
  fftSize: 2048,
  smoothingGain: 0.78,
  vadSilenceMs: 1200,
  vadThreshold: 0.03,
  maxTranscribeTimeMs: 30000,
  sampleRate: 16000,
  channels: 1,
};

export type VoiceEngineEvent =
  | { type: 'streamStart' }
  | { type: 'streamData'; frame: AudioFrame }
  | { type: 'streamEnd' }
  | { type: 'sttDone'; text: string; confidence: number }
  | { type: 'ttsStart' }
  | { type: 'ttsChunk'; chunk: TTSChunk }
  | { type: 'ttsEnd' }
  | { type: 'stateChanged'; state: VoiceEngineState };

export type VoiceEngineEvents = {
  [K in VoiceEngineEvent as K['type']]: K;
};

export class AudioEngineError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AudioEngineError';
  }
}

export function stateToTokenClass(state: VoiceEngineState): string {
  return `.vs-${state}`;
}