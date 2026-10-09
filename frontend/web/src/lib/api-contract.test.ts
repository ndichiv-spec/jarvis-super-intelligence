import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { jarvisAPI } from './api';

describe('RBAC API request contracts', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends only the supported create-user fields', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({
      id: 'new-user',
      email: 'new@example.test',
      username: 'newuser',
      roles: ['user'],
      status: 'pending_authorization',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));

    await jarvisAPI.rbac.createUser({
      email: 'new@example.test',
      username: 'newuser',
      password: 'long-enough-password',
    });

    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toEqual({
      email: 'new@example.test',
      username: 'newuser',
      password: 'long-enough-password',
    });
  });

  it('uses only supported audit-list filters and exports all records without filter parameters', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ logs: [], total: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
      .mockResolvedValueOnce(new Response('id,action', { status: 200 }));

    await jarvisAPI.rbac.getAuditLogs({
      user_id: 'actor-1',
      action: 'user_updated',
      resource_type: 'rbac',
      page: 2,
      per_page: 25,
    });
    await jarvisAPI.rbac.exportAuditLogs();

    const listUrl = new URL(String(fetchMock.mock.calls[0][0]), 'http://localhost');
    expect(listUrl.searchParams.get('user_id')).toBe('actor-1');
    expect(listUrl.searchParams.get('action')).toBe('user_updated');
    expect(listUrl.searchParams.get('resource_type')).toBe('rbac');
    expect(listUrl.searchParams.get('page')).toBe('2');
    expect(listUrl.searchParams.get('per_page')).toBe('25');
    expect(listUrl.searchParams.has('date_from')).toBe(false);
    expect(listUrl.searchParams.has('date_to')).toBe(false);
    expect(String(fetchMock.mock.calls[1][0])).toMatch(/\/api\/v1\/rbac\/audit-logs\/export$/);
  });
});
