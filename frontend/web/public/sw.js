/**
 * JARVIS service worker.
 *
 * Scope is deliberately narrow: cache the app shell so the UI boots offline,
 * and never touch API traffic. A chat client that served a stale or cached
 * `/api/v1/chat` response would be actively harmful, so the API is explicitly
 * excluded rather than merely deprioritised.
 *
 * Strategy per resource type:
 *   - navigations  network-first, falling back to the cached shell
 *   - static assets cache-first (hashed filenames are immutable)
 *   - everything else, including /api/*   passthrough only
 */

const VERSION = 'jarvis-v1';
const SHELL_CACHE = `${VERSION}-shell`;
const ASSET_CACHE = `${VERSION}-assets`;

/** Hashed build output, plus the manifest and icons. */
const PRECACHE_URLS = ['/manifest.json', '/icons/icon.svg', '/icons/icon-192x192.png'];

/** Routes rendered on the server that are worth having available offline. */
const SHELL_ROUTES = ['/dashboard', '/login'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      // Individually, so one missing entry cannot fail the whole install.
      await Promise.allSettled(PRECACHE_URLS.map((url) => cache.add(url)));
      await self.skipWaiting();
    })()
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys.filter((key) => !key.startsWith(VERSION)).map((key) => caches.delete(key))
      );
      await self.clients.claim();
    })()
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;

  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Same-origin only: never proxy third-party or cross-origin traffic.
  if (url.origin !== self.location.origin) return;

  // API traffic is never cached, served from cache, or intercepted.
  if (url.pathname.startsWith('/api/') || url.pathname === '/health' || url.pathname === '/ping') {
    return;
  }

  // WebSocket upgrades must pass straight through.
  if (request.headers.get('upgrade') === 'websocket') return;

  if (request.mode === 'navigate') {
    event.respondWith(handleNavigate(request));
    return;
  }

  if (isImmutableAsset(url.pathname)) {
    event.respondWith(cacheFirst(request));
  }
});

/** Next.js emits content-hashed filenames under /_next/static. */
function isImmutableAsset(pathname) {
  return pathname.startsWith('/_next/static/') || pathname.startsWith('/icons/');
}

async function handleNavigate(request) {
  try {
    // Network-first: a fresh shell is always preferred when online.
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(SHELL_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request, { ignoreSearch: true });
    if (cached) return cached;

    const shell = await caches.open(SHELL_CACHE);
    for (const route of SHELL_ROUTES) {
      const fallback = await shell.match(route);
      if (fallback) return fallback;
    }

    return new Response('JARVIS is offline and no cached shell is available.', {
      status: 503,
      headers: { 'Content-Type': 'text/plain' },
    });
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(ASSET_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // A failed asset fetch returns a synthetic 504 rather than throwing, so a
    // single missing image cannot surface as an unhandled rejection.
    return new Response('', { status: 504 });
  }
}