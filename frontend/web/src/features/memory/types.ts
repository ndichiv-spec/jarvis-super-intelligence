export interface MemoryEntry {
  id: string;
  content: string;
  layer: 'short_term' | 'long_term' | 'working' | 'episodic';
  importance: number;
  tags?: string[];
  created_at: string;
  last_accessed?: string;
  access_count?: number;
}

export interface MemoryStats {
  total_entries: number;
  short_term_count: number;
  long_term_count: number;
  working_count: number;
  episodic_count: number;
  avg_importance: number;
  last_consolidated?: string;
}

export interface CognitiveReport {
  status: string;
  consciousness_active: boolean;
  attention_focus?: string;
  active_goals: string[];
  recent_reflections: string[];
  memory_stats: MemoryStats;
  emotional_state?: EmotionalState;
}

export interface EmotionalState {
  primary_emotion: string;
  valence: number;
  arousal: number;
  dominance: number;
}

export interface KnowledgeGraphNode {
  id: string;
  label: string;
  type: string;
  properties: Record<string, unknown>;
}

export interface KnowledgeGraphEdge {
  source: string;
  target: string;
  relationship: string;
  weight: number;
}
