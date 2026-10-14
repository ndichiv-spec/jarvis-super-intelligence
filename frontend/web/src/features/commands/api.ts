import apiClient from '@/lib/api-client';
import API_ENDPOINTS from '@/config/api';

export interface WorldCommandAuthorization {
  required?: boolean;
  node_ids?: string[];
  actions?: Array<{ node_id: string; capability: string; risk_level: string }>;
  approved_node_ids?: string[];
  approved?: boolean;
  node_id?: string | null;
}

export interface WorldCommand {
  command_id: string;
  conversation_id?: string | null;
  goal: string;
  status: string;
  authorization?: WorldCommandAuthorization | null;
  result?: Record<string, unknown> | null;
  errors?: string[];
}

export const worldWorkspaceApi = {
  submit(goal: string, conversationId?: string | null, requestId?: string): Promise<WorldCommand> {
    return apiClient.post(API_ENDPOINTS.commands.submit, {
      goal,
      conversation_id: conversationId || undefined,
      request_id: requestId,
      autonomy: 'SUPERVISED',
    });
  },

  get(commandId: string): Promise<WorldCommand> {
    return apiClient.get(API_ENDPOINTS.commands.get(commandId));
  },

  authorize(commandId: string, approved: boolean, nodeId?: string): Promise<WorldCommand> {
    return apiClient.post(API_ENDPOINTS.commands.authorize(commandId), {
      approved,
      node_id: nodeId,
    });
  },
};
