export interface VoiceProfile {
  name: string;
  rate: number;
  volume: number;
  pitch?: number;
  language?: string;
}

export interface VoiceStatus {
  speaking: boolean;
  listening: boolean;
  active_profile?: string;
  available_voices: string[];
  mic_available: boolean;
  speaker_available: boolean;
}

export interface VoiceCommand {
  text: string;
  confidence: number;
  intent?: string;
  entities?: Record<string, string>;
}

export interface SpeechRequest {
  text: string;
  profile_name?: string;
  rate?: number;
  volume?: number;
}

export interface TranscriptionResult {
  text: string;
  confidence: number;
  language: string;
  duration: number;
}
