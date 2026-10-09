import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiClient, getAuthToken, onAuthError, setAuthToken } from './api-client';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('cookie-authenticated API client', () => {
  it('sends HttpOnly cookies and never adds a JavaScript bearer token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    setAuthToken('must-not-be-used');

    await new ApiClient('https://api.example.test').get('/private', { retries: 0 });

    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(request.credentials).toBe('include');
    expect(request.headers).not.toHaveProperty('Authorization');
    expect(getAuthToken()).toBeNull();
  });

  it('refreshes the HttpOnly session cookie once after an expired access cookie', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'expired' }), { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ authenticated: true }), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    vi.stubGlobal('fetch', fetchMock);

    await new ApiClient('https://api.example.test').get('/private', { retries: 1 });

    const [, refreshRequest] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(refreshRequest.credentials).toBe('include');
    expect(refreshRequest.body).toBeUndefined();
    expect(refreshRequest.headers).not.toHaveProperty('Authorization');
  });

  it('does not treat an expired endpoint credential as an expired owner session', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'invalid endpoint credential' }), { status: 401 }),
    );
    const onAuthErrorMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    onAuthError(onAuthErrorMock);

    await expect(
      new ApiClient('https://api.example.test').get('/endpoint', {
        headers: { Authorization: 'Bearer jep_endpoint.secret' },
        retries: 0,
      }),
    ).rejects.toMatchObject({ status: 401 });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(onAuthErrorMock).not.toHaveBeenCalled();
  });
});
