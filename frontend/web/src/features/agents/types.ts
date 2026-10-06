export interface AgentTask {
  id?: string;
  name: string;
  description?: string;
  schedule_type: string;
  schedule_value: string;
  priority: 'low' | 'normal' | 'high' | 'critical';
  enabled: boolean;
  timeout: number;
  max_retries: number;
  last_run_at?: string;
  last_run_status?: 'completed' | 'failed' | 'running' | 'pending';
  last_run_duration_ms?: number;
  created_at?: string;
}

export interface TaskExecution {
  id: string;
  task_name: string;
  status: 'completed' | 'failed' | 'retrying' | 'running';
  started_at: string;
  completed_at?: string;
  duration_ms: number;
  retries: number;
  error?: string;
}

export interface AgentStats {
  total_tasks: number;
  active_tasks: number;
  success_rate_percent: number;
  avg_execution_time_ms: number;
}

export interface SchedulerStatus {
  running: boolean;
  total_scheduled: number;
  next_run_at?: string;
  single_worker_required?: boolean;
}

export interface AgentStatus {
  id: string;
  name: string;
  status: 'idle' | 'running' | 'error' | 'offline';
  current_task?: string;
  uptime: number;
  task_count: number;
  success_rate: number;
  last_active: string;
}

export interface CollaborationAgent {
  id: string;
  name: string;
  capabilities: string[];
  status: string;
  current_load: number;
}

export interface CollaborationTask {
  id: string;
  description: string;
  agents_needed: string[];
  collaboration_pattern: string;
  status: string;
  created_at: string;
}
