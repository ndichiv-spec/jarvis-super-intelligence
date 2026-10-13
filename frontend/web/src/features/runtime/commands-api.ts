import apiClient from '@/lib/api-client';
import API_ENDPOINTS from '@/config/api';

export interface CommandEvent {
  event?: string;
  sequence?: number;
  timestamp?: number | string;
  [key: string]: unknown;
}

export interface CommandAuthorization {
  required?: boolean;
  node_ids?: string[];
  approved_node_ids?: string[];
  approved?: boolean;
}

export interface CommandRecord {
  command_id: string;
  goal?: string;
  status: string;
  plan?: unknown;
  authorization?: CommandAuthorization | null;
  events?: CommandEvent[];
  result?: unknown;
  errors?: unknown[];
  task_id?: string | null;
  capabilities?: string[];
  request_id?: string;
  conversation_id?: string;
  created_at?: number | string;
  completed_at?: number | string | null;
  [key: string]: unknown;
}

export interface SubmitCommandRequest {
  goal: string;
  conversation_id?: string;
  request_id: string;
}

export const commandsApi = {
  async list(limit = 50): Promise<CommandRecord[]> {
    const response = await apiClient.get<{ commands: CommandRecord[] }>(API_ENDPOINTS.commands.list, {
      params: { limit },
    });
    return Array.isArray(response.commands) ? response.commands : [];
  },

  submit(request: SubmitCommandRequest): Promise<CommandRecord> {
    return apiClient.post<CommandRecord>(API_ENDPOINTS.commands.submit, request);
  },

  get(commandId: string): Promise<CommandRecord> {
    return apiClient.get<CommandRecord>(API_ENDPOINTS.commands.get(commandId));
  },

  authorize(commandId: string, nodeId: string, approved: boolean): Promise<CommandRecord> {
    return apiClient.post<CommandRecord>(API_ENDPOINTS.commands.authorize(commandId), {
      approved,
      node_id: nodeId,
    });
  },
};
