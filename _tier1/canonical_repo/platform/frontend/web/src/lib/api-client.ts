import env from '@/config/env';

export interface RequestConfig extends Omit<RequestInit, 'body'> {
  params?: Record<string, string | number | boolean | undefined>;
  data?: unknown;
  timeout?: number;
  retries?: number;
  retryDelay?: number;
}

export class ApiClientError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
    public details?: unknown
  ) {
    super(message);
    this.name = 'ApiClientError';
  }
}

/**
 * Thrown when a 401 response triggers the global auth-error handler.
 * Pages should check for this and suppress visible error toasts,
 * since the user is already being redirected to /login.
 */
export class AuthError extends ApiClientError {
  constructor(message: string, code?: string, details?: unknown) {
    super(message, 401, code, details);
    this.name = 'AuthError';
  }
}

let _authToken: string | null = null;
let _refreshToken: string | null = null;
let _authHydrated = false;
let _refreshing = false;
let _onAuthError: (() => void) | null = null;

// zustand persist key used by stores/authStore.ts. Lazily read on first
// request so API calls are authenticated even if the auth-store module hasn't
// been imported yet — removes the first-render auth race that caused silent
// 401 -> re-login on fresh mounts.
const AUTH_STORAGE_KEY = 'jarvis-auth-storage';

export function setAuthToken(token: string | null, refreshToken: string | null = null) {
  _authToken = token;
  _refreshToken = refreshToken;
  _authHydrated = true;
  if (typeof window !== 'undefined' && token !== null && token !== '') {
    try {
      const existing = JSON.parse(localStorage.getItem(AUTH_STORAGE_KEY) || '{}');
      localStorage.setItem(
        AUTH_STORAGE_KEY,
        JSON.stringify({ ...existing, token, refreshToken: refreshToken ?? existing.refreshToken ?? null })
      );
    } catch { /* ignore storage errors */ }
  }
}

function _hydrateFromStorage(): void {
  if (_authHydrated || typeof window === 'undefined') return;
  _authHydrated = true;
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    if (raw) {
      const s = JSON.parse(raw);
      if (s.token) _authToken = s.token;
      if (s.refreshToken) _refreshToken = s.refreshToken;
    }
  } catch { /* ignore */ }
}

export function getAuthToken(): string | null {
  _hydrateFromStorage();
  return _authToken;
}

export function onAuthError(handler: () => void) {
  _onAuthError = handler;
}

/**
 * Clear all auth state — both the in-memory token/refresh token and the
 * persisted `jarvis-auth-storage` entry in localStorage. Called when a 401
 * can't be resolved via refresh, so the login page correctly shows the
 * sign-in form instead of redirect-looping back to a protected route.
 */
export function clearAuthToken(): void {
  _authToken = null;
  _refreshToken = null;
  _authHydrated = false;
  if (typeof window !== 'undefined') {
    try {
      localStorage.removeItem(AUTH_STORAGE_KEY);
    } catch { /* ignore */ }
  }
}

export class ApiClient {
  constructor(private baseUrl: string = env.API_URL) {}

  private buildUrl(endpoint: string, params?: Record<string, string | number | boolean | undefined>): string {
    const url = endpoint.startsWith('http') ? endpoint : `${this.baseUrl}${endpoint}`;
    if (!params) return url;

    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== '') {
        searchParams.set(key, String(value));
      }
    }
    const qs = searchParams.toString();
    return qs ? `${url}${url.includes('?') ? '&' : '?'}${qs}` : url;
  }

  private async request<T>(endpoint: string, config: RequestConfig = {}): Promise<T> {
    const { params, data, timeout = env.REQUEST_TIMEOUT, retries = 2, retryDelay = 1000, ...fetchConfig } = config;
    const url = this.buildUrl(endpoint, params);
    // Make sure the in-memory token is populated from persisted storage on a
    // fresh mount (no-op when authStore already synced it).
    _hydrateFromStorage();

    const headers: Record<string, string> = {
      ...(fetchConfig.headers as Record<string, string>),
    };

    if (!(data instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }

    if (_authToken) {
      headers['Authorization'] = `Bearer ${_authToken}`;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const response = await fetch(url, {
          ...fetchConfig,
          headers,
          body: data instanceof FormData ? data as FormData : data ? JSON.stringify(data) : undefined,
          signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
          const errorBody = await response.json().catch(() => ({ error: response.statusText }));
          const errorMessage = errorBody.error || errorBody.detail || `HTTP ${response.status}`;
          const errorCategory = response.headers.get('X-Browser-Error-Category');

          // On a 401, try ONE silent refresh with the persisted refresh token.
          // If it succeeds, retry the request with the new access token instead
          // of forcing the user back to the login page.
          let refreshed = false;
          if (response.status === 401 && !_refreshing) {
            _refreshing = true;
            try {
              if (await this._tryRefresh()) {
                refreshed = true;
                headers['Authorization'] = `Bearer ${_authToken}`;
              }
            } finally {
              _refreshing = false;
            }
          }

          if (refreshed) {
            continue;
          }

          // Only treat actual 401 as auth errors. For other HTTP errors, throw
          // a generic ApiClientError with the real status code so page-level
          // catch blocks can handle non-auth failures gracefully.
          if (response.status === 401) {
            if (_onAuthError) {
              _onAuthError();
            }

            // Clear the stale token so the next page load (login) shows the
            // sign-in form instead of redirect-looping back here with the same
            // invalid token. This must happen *before* AuthError is thrown.
            clearAuthToken();

            // After the auth-error redirect is fired, throw an AuthError so that
            // page-level catch blocks can recognize it and suppress any visible
            // error toast (the user is already being sent to /login).
            throw new AuthError(
              errorMessage,
              errorBody.code,
              { ...errorBody, error_category: errorCategory }
            );
          }

          throw new ApiClientError(
            errorMessage,
            response.status,
            errorBody.code,
            { ...errorBody, error_category: errorCategory }
          );
        }

        const contentType = response.headers.get('content-type');
        if (contentType?.includes('application/json')) {
          return response.json() as Promise<T>;
        }
        return response as unknown as T;

      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));

        if (error instanceof ApiClientError && error.status < 500) {
          clearTimeout(timeoutId);
          throw error;
        }

        if (attempt < retries) {
          await new Promise((resolve) => setTimeout(resolve, retryDelay * Math.pow(2, attempt)));
          continue;
        }
      }
    }

    clearTimeout(timeoutId);
    throw lastError || new ApiClientError('Request failed after retries', 0);
  }

  async get<T>(endpoint: string, config?: RequestConfig): Promise<T> {
    return this.request<T>(endpoint, { ...config, method: 'GET' });
  }

  async post<T>(endpoint: string, data?: unknown, config?: RequestConfig): Promise<T> {
    return this.request<T>(endpoint, { ...config, method: 'POST', data });
  }

  async put<T>(endpoint: string, data?: unknown, config?: RequestConfig): Promise<T> {
    return this.request<T>(endpoint, { ...config, method: 'PUT', data });
  }

  async patch<T>(endpoint: string, data?: unknown, config?: RequestConfig): Promise<T> {
    return this.request<T>(endpoint, { ...config, method: 'PATCH', data });
  }

  async delete<T>(endpoint: string, config?: RequestConfig): Promise<T> {
    return this.request<T>(endpoint, { ...config, method: 'DELETE' });
  }

  async upload<T>(endpoint: string, formData: FormData, config?: RequestConfig): Promise<T> {
    return this.request<T>(endpoint, {
      ...config,
      method: 'POST',
      data: formData,
      headers: {},
    });
  }

  private async _tryRefresh(): Promise<boolean> {
    if (!_refreshToken) return false;
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);
      const response = await fetch(`${this.baseUrl}/api/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: _refreshToken }),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      if (!response.ok) return false;
      const data = await response.json().catch(() => null);
      const newAccess = data?.access_token;
      if (!newAccess) return false;
      // The refresh token stays valid (backend doesn't rotate/revoke on
      // refresh), so we only swap in the new access token here.
      setAuthToken(newAccess, _refreshToken);
      return true;
    } catch {
      return false;
    }
  }
}

export const apiClient = new ApiClient();
export default apiClient;
