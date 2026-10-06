/**
 * Runtime URL resolution.
 *
 * Every network address in the app is derived here instead of being hardcoded at
 * each call site. Two problems this solves:
 *
 *  1. Scheme correctness. A page served over HTTPS cannot open a `ws://` socket
 *     (mixed content is blocked) and a page served over HTTP cannot open
 *     `wss://` on a plaintext port. Deriving the scheme from `window.location`
 *     keeps the socket scheme and the page scheme in agreement automatically.
 *  2. Proxy awareness. In production the frontend and the API are usually behind
 *     one origin, so a relative path is correct and an absolute `127.0.0.1`
 *     address is wrong. Returning a relative path lets the Next.js rewrite
 *     proxy (or the reverse proxy) do the routing.
 */

/** Only local development may use a loopback API fallback. */
const FALLBACK_ORIGIN =
  process.env.NODE_ENV === 'development' ? 'http://127.0.0.1:8000' : '';

function readEnv(key: string): string | undefined {
  const value = process.env[key];
  return value && value.length > 0 ? value : undefined;
}

/**
 * Origin of the backend HTTP API.
 *
 * Precedence: `NEXT_PUBLIC_API_URL` -> the page's own origin (correct behind a
 * reverse proxy) -> `127.0.0.1:8000` for local dev.
 *
 * Returns an absolute origin with no trailing slash.
 */
export function getApiOrigin(): string {
  const configured = readEnv('NEXT_PUBLIC_API_URL');
  if (configured) return new URL(configured).origin;

  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin;
  }

  return FALLBACK_ORIGIN ? new URL(FALLBACK_ORIGIN).origin : '';
}

/**
 * Build an HTTP request URL from the configured public origin and endpoint.
 * Query parameters are encoded by URLSearchParams; fragments are removed
 * because they are client-side state and are never part of an HTTP request.
 */
export function getApiUrl(
  endpoint: string,
  query?: URLSearchParams | Record<string, string | number | boolean | null | undefined>,
  baseUrl = readEnv('NEXT_PUBLIC_API_URL')
): string {
  const base = baseUrl || (typeof window !== 'undefined' ? window.location.origin : '');
  const basePath = normalizeBasePath(readEnv('NEXT_PUBLIC_BASE_PATH') ?? '');
  const endpointUrl = new URL(endpoint, base || 'http://jarvis.invalid');

  if (basePath && endpointUrl.origin === (base ? new URL(base).origin : 'http://jarvis.invalid')) {
    endpointUrl.pathname = joinPaths(basePath, endpointUrl.pathname);
  }
  if (query instanceof URLSearchParams) {
    query.forEach((value, key) => endpointUrl.searchParams.set(key, value));
  } else if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) endpointUrl.searchParams.set(key, String(value));
    }
  }
  endpointUrl.hash = '';

  if (!base || (typeof window !== 'undefined' && endpointUrl.origin === window.location.origin)) {
    return `${endpointUrl.pathname}${endpointUrl.search}`;
  }
  return endpointUrl.toString();
}

/**
 * Base URL for WebSocket connections.
 *
 * Precedence: `NEXT_PUBLIC_WS_URL` -> derived from {@link getApiOrigin} by
 * swapping the scheme to match the page (`http`->`ws`, `https`->`wss`) ->
 * `127.0.0.1:8000` for local dev.
 */
export function getWsBase(): string {
  const configured = readEnv('NEXT_PUBLIC_WS_URL');
  const pageIsSecure =
    typeof window !== 'undefined' && window.location?.protocol === 'https:';

  if (configured) {
    const configuredSecure = configured.toLowerCase().startsWith('wss://');
    return toWebSocketOrigin(configured, isBrowser() ? pageIsSecure : configuredSecure);
  }

  return toWebSocketOrigin(getApiOrigin(), pageIsSecure);
}

/**
 * Absolute WebSocket URL for a backend path.
 *
 * @param path Backend path beginning with a slash, e.g. `/api/v1/voice/ws/chat`.
 */
export function getWsUrl(path: string): string {
  const wsBase = getWsBase();
  const base = wsBase || (typeof window !== 'undefined' ? toWebSocketOrigin(window.location.origin) : '');
  if (!base) return normalizePath(path);

  const url = new URL(path, `${stripTrailingSlash(base)}/`);
  const basePath = normalizeBasePath(readEnv('NEXT_PUBLIC_BASE_PATH') ?? '');
  if (basePath && !/^[a-z][a-z\d+.-]*:/i.test(path)) {
    url.pathname = joinPaths(basePath, url.pathname);
  }
  url.protocol = new URL(base).protocol;
  url.hash = '';
  return url.toString();
}

/** Convert an HTTP(S) origin into its WebSocket equivalent. */
export function toWebSocketOrigin(origin: string, secure?: boolean): string {
  const useSecure =
    secure ??
    (typeof window !== 'undefined'
      ? window.location?.protocol === 'https:'
      : origin.startsWith('https://'));

  if (!origin) return '';
  const url = new URL(origin);
  url.protocol = useSecure ? 'wss:' : 'ws:';
  url.pathname = '';
  url.search = '';
  url.hash = '';
  return stripTrailingSlash(url.toString());
}

/** True when the page is running in a browser. */
export function isBrowser(): boolean {
  return typeof window !== 'undefined';
}

/**
 * True when the frontend and backend are same-origin, meaning relative API
 * paths are preferable to absolute ones.
 */
export function isSameOriginApi(): boolean {
  if (!isBrowser()) return false;
  const configured = readEnv('NEXT_PUBLIC_API_URL');
  return !configured;
}

function normalizePath(path: string): string {
  return path.startsWith('/') ? path : `/${path}`;
}

function normalizeBasePath(path: string): string {
  if (!path || path === '/') return '';
  return `/${path.split('/').filter(Boolean).join('/')}`;
}

function joinPaths(prefix: string, path: string): string {
  return `${normalizeBasePath(prefix)}${normalizePath(path)}` || '/';
}

function stripTrailingSlash(value: string): string {
  return value.endsWith('/') ? value.slice(0, -1) : value;
}