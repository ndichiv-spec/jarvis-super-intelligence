import { afterEach, describe, expect, it, vi } from 'vitest';
import { getApiOrigin, getApiUrl, getWsUrl } from './runtime-url';

describe('runtime URL construction', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it('uses the browser origin for API requests and encodes query parameters', () => {
    vi.stubGlobal('window', {
      location: {
        origin: 'https://jarvis.example.com',
        protocol: 'https:',
      },
    });
    vi.stubEnv('NEXT_PUBLIC_API_URL', '');
    vi.stubEnv('NEXT_PUBLIC_BASE_PATH', '');

    expect(getApiOrigin()).toBe('https://jarvis.example.com');
    expect(
      getApiUrl('/api/v1/chat?conversation_id=123#conversation/123', {
        query: 'a & b',
        page: 2,
      }),
    ).toBe('/api/v1/chat?conversation_id=123&query=a+%26+b&page=2');
  });

  it('keeps HTTPS WebSockets secure and never sends URL fragments', () => {
    vi.stubGlobal('window', {
      location: {
        origin: 'https://jarvis.example.com',
        protocol: 'https:',
      },
    });
    vi.stubEnv('NEXT_PUBLIC_API_URL', '');
    vi.stubEnv('NEXT_PUBLIC_WS_URL', '');
    vi.stubEnv('NEXT_PUBLIC_BASE_PATH', '');

    expect(getWsUrl('/ws/health?channel=monitoring#client-state')).toBe(
      'wss://jarvis.example.com/ws/health?channel=monitoring',
    );
  });

  it('upgrades a configured insecure WebSocket origin when the page uses HTTPS', () => {
    vi.stubGlobal('window', {
      location: {
        origin: 'https://jarvis.example.com',
        protocol: 'https:',
      },
    });
    vi.stubEnv('NEXT_PUBLIC_API_URL', '');
    vi.stubEnv('NEXT_PUBLIC_WS_URL', 'ws://backend.example.com:8080');
    vi.stubEnv('NEXT_PUBLIC_BASE_PATH', '');

    expect(getWsUrl('/ws/health')).toBe('wss://backend.example.com:8080/ws/health');
  });

  it('applies configured path prefixes and preserves configured ports', () => {
    vi.stubGlobal('window', {
      location: {
        origin: 'https://jarvis.example.com',
        protocol: 'https:',
      },
    });
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'https://api.example.com:8443');
    vi.stubEnv('NEXT_PUBLIC_WS_URL', '');
    vi.stubEnv('NEXT_PUBLIC_BASE_PATH', '/app/');

    expect(getApiUrl('/api/v1/chat')).toBe(
      'https://api.example.com:8443/app/api/v1/chat',
    );
    expect(getWsUrl('/ws/health')).toBe(
      'wss://api.example.com:8443/app/ws/health',
    );
  });
});
