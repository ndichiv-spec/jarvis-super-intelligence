export type CommandStatus =
  | 'RECEIVED'
  | 'UNDERSTANDING'
  | 'PLANNING'
  | 'AWAITING_AUTHORIZATION'
  | 'READY'
  | 'EXECUTING'
  | 'WAITING'
  | 'VERIFYING'
  | 'RECOVERING'
  | 'REPLANNING'
  | 'COMPLETED'
  | 'PARTIAL'
  | 'FAILED'
  | 'CANCELLED';

const TERMINAL_COMMAND_STATUSES = new Set<CommandStatus>([
  'COMPLETED', 'PARTIAL', 'FAILED', 'CANCELLED',
]);

export function isActiveCommandStatus(status: CommandStatus): boolean {
  return !TERMINAL_COMMAND_STATUSES.has(status);
}

export interface RuntimeEvent {
  sequence: number;
  event: string;
  timestamp: number;
  detail?: string;
  capability?: string | null;
  success?: boolean | null;
  capabilities?: string[];
  status?: string;
}

export interface CommandStep {
  step_id: string;
  capability: string;
  summary: string;
  depends_on: string[];
}

export interface RuntimeCommand {
  command_id: string;
  goal: string;
  status: CommandStatus;
  plan: CommandStep[];
  active_step: string | null;
  capabilities: string[];
  models: string[];
  events: RuntimeEvent[];
  result: null | {
    summary: string;
    evidence: Array<Record<string, unknown>>;
    confidence_state: string;
    completion_condition_met: string;
  };
  errors: string[];
  authorization: null | { capabilities: string[]; approved: boolean | null };
}

export interface RuntimeCapability {
  id: string;
  name: string;
  domain: string;
  availability: string;
  availability_reason?: string | null;
  risk_level: string;
}
