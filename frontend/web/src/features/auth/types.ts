export interface User {
  id: string;
  email: string;
  username: string;
  full_name?: string;
  avatar_url?: string;
  status: 'active' | 'inactive' | 'suspended';
  tenant_id: string;
  roles?: UserRole[];
  last_login_at?: string;
  created_at?: string;
}

export interface UserRole {
  id: string;
  name: string;
  permissions: string[];
}

export interface LoginResponse {
  access_token?: string;
  token_type?: string;
  user: User;
}

export interface RegisterRequest {
  email: string;
  username: string;
  password: string;
  full_name?: string;
  tenant_slug?: string;
}

export interface LoginRequest {
  identifier: string;
  password: string;
}

export interface SessionInfo {
  id: string;
  user_id: string;
  device?: string;
  ip?: string | null;
  ip_address?: string;
  user_agent?: string;
  created_at: string;
  last_active_at?: string;
  is_current?: boolean | null;
}

export interface APIKeyInfo {
  id: string;
  name: string;
  description?: string;
  scopes: string[];
  prefix: string;
  created_at: string;
  expires_at?: string;
  last_used_at?: string;
}

export interface APIKeyCreate {
  name: string;
  description?: string;
  scopes?: string[];
  expires_in_days?: number;
}

export interface Permission {
  id: string;
  resource: string;
  action: string;
  description?: string;
}

export interface Role {
  id: string;
  name: string;
  description?: string;
  permissions: string[];
  is_system: boolean;
  user_count?: number;
  created_at?: string;
}
