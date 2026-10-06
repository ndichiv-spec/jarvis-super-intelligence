export interface AutomationTask {
  id: string;
  name: string;
  description?: string;
  trigger_type: 'schedule' | 'event' | 'webhook' | 'manual';
  trigger_config: Record<string, unknown>;
  action_type: string;
  action_config: Record<string, unknown>;
  enabled: boolean;
  engine?: 'local' | 'n8n';
  last_run_at?: string;
  last_run_status?: 'accepted' | 'completed' | 'failed';
  created_at: string;
}

export interface AutomationExecution {
  id: string;
  task_id: string;
  task_name: string;
  status: 'accepted' | 'completed' | 'failed';
  started_at: string;
  completed_at?: string;
  duration_ms: number;
  engine?: 'local' | 'n8n';
  result?: Record<string, unknown>;
  run?: Record<string, unknown>;
  error?: string;
}

export interface AutomationStats {
  total_tasks: number;
  active_tasks: number;
  success_rate: number;
  executions_today: number;
  avg_duration_ms: number;
}
