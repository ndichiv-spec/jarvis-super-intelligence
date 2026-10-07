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

let _refreshing = false;
let _onAuthError: (() => void) | null = null;

// Persisted keys from versions that stored bearer credentials in localStorage.
const AUTH_STORAGE_KEY = 'jarvis-auth-storage';
const FEATURE_AUTH_STORAGE_KEY = 'jarvis-feature-auth-storage';

export function setAuthToken(_token: string | null, _refreshToken: string | null = null) {
  // Authentication uses server-managed HttpOnly cookies only.
}

export function getAuthToken(): string | null {
  return null;
}

export function onAuthError(handler: () => void) {
  _onAuthError = handler;
}

/**
 * Clear persisted UI auth state after the HttpOnly session cannot be refreshed.
 */
export function clearAuthToken(): void {
  if (typeof window !== 'undefined') {
    try {
      localStorage.removeItem(AUTH_STORAGE_KEY);
      localStorage.removeItem(FEATURE_AUTH_STORAGE_KEY);
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
    const headers: Record<string, string> = {
      ...(fetchConfig.headers as Record<string, string>),
    };

    if (!(data instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    let lastError: Error | null = null;
    let refreshAttempted = false;

    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const response = await fetch(url, {
          ...fetchConfig,
          headers,
          body: data instanceof FormData ? data as FormData : data ? JSON.stringify(data) : undefined,
          signal: controller.signal,
          credentials: 'include',
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
          const errorBody = await response.json().catch(() => ({ error: response.statusText }));
          const errorMessage = errorBody.error || errorBody.detail || `HTTP ${response.status}`;
          const errorCategory = response.headers.get('X-Browser-Error-Category');

          // On a 401, try ONE silent refresh using the HttpOnly refresh cookie.
          // If it succeeds, retry the request with the rotated access cookie instead
          // of forcing the user back to the login page.
          let refreshed = false;
          if (response.status === 401 && !_refreshing && !refreshAttempted) {
            refreshAttempted = true;
            _refreshing = true;
            try {
              if (await this._tryRefresh()) {
                refreshed = true;
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
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);
      const response = await fetch(`${this.baseUrl}/api/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        credentials: 'include',
      });
      clearTimeout(timeoutId);
      if (!response.ok) return false;
      // The backend rotates both HttpOnly cookies; JavaScript never receives
      // or persists either credential.
      return true;
    } catch {
      return false;
    }
  }
}

export const apiClient = new ApiClient();
export default apiClient;
