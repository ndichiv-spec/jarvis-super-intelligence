export type AsyncStatus = 'idle' | 'loading' | 'success' | 'error';

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface ApiError {
  error: string;
  detail?: string;
  status_code: number;
}

export type { ChatMessage, ChatResponse, SessionInfo } from '@/features/chat/types';
export type { User, LoginResponse, RegisterRequest } from '@/features/auth/types';
export type { AgentTask, AgentStats, TaskExecution, SchedulerStatus } from '@/features/agents/types';
export type { MetricsData, HealthStatus, HealthReport } from '@/features/monitoring/types';
export type { MemoryEntry, MemoryStats, CognitiveReport } from '@/features/memory/types';
export type { VoiceProfile, VoiceStatus } from '@/features/voice/types';
export type { SystemStatus, SystemProcess, ProviderSettings } from '@/features/system/types';
export type { AutomationTask } from '@/features/automation/types';
