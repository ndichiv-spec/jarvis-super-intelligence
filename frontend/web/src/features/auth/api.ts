import apiClient, { setAuthToken } from '@/lib/api-client';
import API_ENDPOINTS from '@/config/api';
import type { LoginResponse, LoginRequest, RegisterRequest, User, SessionInfo, APIKeyInfo, APIKeyCreate } from './types';

export const authApi = {
  async login(credentials: LoginRequest): Promise<LoginResponse> {
    const response = await apiClient.post<LoginResponse>(API_ENDPOINTS.auth.login, credentials);
    setAuthToken(response.access_token);
    return response;
  },

  async register(data: RegisterRequest): Promise<LoginResponse> {
    const response = await apiClient.post<LoginResponse>(API_ENDPOINTS.auth.register, data);
    setAuthToken(response.access_token);
    return response;
  },

  async logout(): Promise<{ message: string }> {
    try {
      return await apiClient.post<{ message: string }>(API_ENDPOINTS.auth.logout);
    } finally {
      setAuthToken(null);
    }
  },

  getMe(): Promise<User> {
    return apiClient.get<User>(API_ENDPOINTS.auth.me);
  },

  updateMe(data: Partial<Pick<User, 'full_name' | 'username' | 'avatar_url'>>): Promise<User> {
    return apiClient.put<User>(API_ENDPOINTS.auth.me, data);
  },

  changePassword(currentPassword: string, newPassword: string): Promise<{ message: string }> {
    return apiClient.post<{ message: string }>(API_ENDPOINTS.auth.changePassword, {
      current_password: currentPassword,
      new_password: newPassword,
    });
  },

  forgotPassword(email: string): Promise<{ message: string }> {
    return apiClient.post<{ message: string }>(API_ENDPOINTS.auth.forgotPassword, { email });
  },

  resetPassword(token: string, newPassword: string): Promise<{ message: string }> {
    return apiClient.post<{ message: string }>(API_ENDPOINTS.auth.resetPassword, {
      token,
      new_password: newPassword,
    });
  },

  async getSessions(): Promise<SessionInfo[]> {
    const response = await apiClient.get<{ sessions: SessionInfo[] }>(API_ENDPOINTS.auth.sessions);
    return response.sessions;
  },

  revokeSession(sessionId: string): Promise<{ message: string }> {
    return apiClient.delete<{ message: string }>(`${API_ENDPOINTS.auth.sessions}/${sessionId}`);
  },

  revokeAllSessions(): Promise<{ message: string }> {
    return apiClient.delete<{ message: string }>(API_ENDPOINTS.auth.sessions);
  },

  async getApiKeys(): Promise<APIKeyInfo[]> {
    const response = await apiClient.get<{ api_keys: APIKeyInfo[] }>(API_ENDPOINTS.auth.apiKeys);
    return response.api_keys;
  },

  createApiKey(data: APIKeyCreate): Promise<APIKeyInfo> {
    return apiClient.post<APIKeyInfo>(API_ENDPOINTS.auth.apiKeys, data);
  },

  revokeApiKey(keyId: string): Promise<{ message: string }> {
    return apiClient.delete<{ message: string }>(`${API_ENDPOINTS.auth.apiKeys}/${keyId}`);
  },
};

export default authApi;
