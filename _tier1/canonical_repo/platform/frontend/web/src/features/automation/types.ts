export interface AutomationTask {
  id: string;
  name: string;
  description?: string;
  trigger_type: 'schedule' | 'event' | 'webhook' | 'manual';
  trigger_config: Record<string, unknown>;
  action_type: string;
  action_config: Record<string, unknown>;
  enabled: boolean;
  last_run_at?: string;
  last_run_status?: 'completed' | 'failed' | 'running';
  created_at: string;
}

export interface AutomationExecution {
  id: string;
  task_id: string;
  task_name: string;
  status: 'running' | 'completed' | 'failed';
  started_at: string;
  completed_at?: string;
  duration_ms: number;
  result?: Record<string, unknown>;
  error?: string;
}

export interface AutomationStats {
  total_tasks: number;
  active_tasks: number;
  success_rate: number;
  executions_today: number;
  avg_duration_ms: number;
}
