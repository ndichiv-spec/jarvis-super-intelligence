import apiClient from '@/lib/api-client';
import API_ENDPOINTS from '@/config/api';
import type { MemoryEntry, MemoryStats, CognitiveReport, KnowledgeGraphNode, KnowledgeGraphEdge } from './types';

export const memoryApi = {
  store(content: string, layer: string = 'short_term', importance?: number): Promise<{ success: boolean; entry: MemoryEntry }> {
    return apiClient.post(API_ENDPOINTS.memory.store, { content, layer, importance });
  },

  recall(query?: string, limit: number = 10): Promise<{ entries: MemoryEntry[] }> {
    return apiClient.get(API_ENDPOINTS.memory.recall, { params: { query, limit } });
  },

  getStats(): Promise<MemoryStats> {
    return apiClient.get<MemoryStats>(API_ENDPOINTS.memory.stats);
  },

  consolidate(): Promise<{ success: boolean; message: string }> {
    return apiClient.post(API_ENDPOINTS.memory.consolidate);
  },

  getCognitiveReport(): Promise<CognitiveReport> {
    return apiClient.get<CognitiveReport>(API_ENDPOINTS.memory.cognitiveReport);
  },

  processInteraction(userInput: string, aiResponse: string, userId: string = 'default'): Promise<any> {
    return apiClient.post(API_ENDPOINTS.memory.cognitiveProcess, {
      user_input: userInput,
      ai_response: aiResponse,
      user_id: userId,
    });
  },

  analyzeEmotion(text: string): Promise<any> {
    return apiClient.get(API_ENDPOINTS.memory.emotionAnalyze, { params: { text } });
  },

  searchKnowledgeGraph(query: string, category?: string): Promise<{ nodes: KnowledgeGraphNode[]; edges: KnowledgeGraphEdge[] }> {
    return apiClient.get(API_ENDPOINTS.memory.knowledgeGraph, { params: { query, category } });
  },
};

export default memoryApi;
