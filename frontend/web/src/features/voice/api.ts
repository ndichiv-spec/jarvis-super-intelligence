import apiClient from '@/lib/api-client';
import API_ENDPOINTS from '@/config/api';
import type { VoiceProfile, VoiceStatus, SpeechRequest, TranscriptionResult } from './types';

export const voiceApi = {
  speak(text: string, profileName?: string): Promise<{ success: boolean }> {
    return apiClient.post(API_ENDPOINTS.voice.speak, { text, profile_name: profileName });
  },

  listen(timeout: number = 5, phraseTimeLimit: number = 10): Promise<{ success: boolean; text: string; confidence: number }> {
    return apiClient.post(API_ENDPOINTS.voice.listen, { timeout, phrase_time_limit: phraseTimeLimit });
  },

  transcribe(file: File): Promise<TranscriptionResult> {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.upload<TranscriptionResult>(API_ENDPOINTS.voice.transcribe, formData);
  },

  createProfile(name: string, rate: number = 150, volume: number = 0.9): Promise<{ success: boolean; profile: VoiceProfile }> {
    return apiClient.post(API_ENDPOINTS.voice.profiles, { name, rate, volume });
  },

  listProfiles(): Promise<{ profiles: VoiceProfile[] }> {
    return apiClient.get(API_ENDPOINTS.voice.profiles);
  },

  getVoices(): Promise<{ voices: string[] }> {
    return apiClient.get(API_ENDPOINTS.voice.voices);
  },

  getStatus(): Promise<VoiceStatus> {
    return apiClient.get<VoiceStatus>(API_ENDPOINTS.voice.status);
  },
};

export default voiceApi;
