import { describe, it, expect } from 'vitest';
import env from './env';
import API_ENDPOINTS from './api';

describe('API endpoint contract (frontend -> canonical backend)', () => {
  // These assertions codify the route contracts that the tracked
  // `jarvis_backend/routers/legacy.py` (chat) and `routers/auth.py` serve.
  // If a backend route moves or the frontend prefix changes, these fail.

  it('base API URL is env-driven (no hard-coded host baked into endpoints)', () => {
    expect(typeof env.API_URL).toBe('string');
    // In NODE_ENV !== development, API_URL falls back to '' (relative paths).
  });

  it('chat send + stream use the /api/v1 surface (legacy.py POST /api/v1/chat and /api/v1/chat/stream)', () => {
    expect(API_ENDPOINTS.chat.stream).toBe(`${env.API_URL}/api/v1/chat/stream`);
    expect(API_ENDPOINTS.chat.stream).toMatch(/chat\/stream$/);
    expect(API_ENDPOINTS.chat.send).toBe(`${env.API_URL}/api/v1/chat`);
  });

  it('chat sessions/history/switch use the /api/chat (non-v1) surface (legacy.py GET /api/chat/sessions, /history, /switch)', () => {
    expect(API_ENDPOINTS.chat.sessions).toBe(`${env.API_URL}/api/chat/sessions`);
    expect(API_ENDPOINTS.chat.history('s1')).toBe(`${env.API_URL}/api/chat/history/s1`);
    expect(API_ENDPOINTS.chat.switchModel).toBe(`${env.API_URL}/api/chat/switch`);
  });

  it('history/regenerate/feedbackMessage/export are URL-builder functions', () => {
    expect(typeof API_ENDPOINTS.chat.history).toBe('function');
    expect(typeof API_ENDPOINTS.chat.regenerate).toBe('function');
    expect(typeof API_ENDPOINTS.chat.feedbackMessage).toBe('function');
    expect(typeof API_ENDPOINTS.chat.export).toBe('function');
  });

  it('chat status resolves to the canonical ai/status route', () => {
    expect(API_ENDPOINTS.chat.status).toBe(`${env.API_URL}/api/v1/ai/status`);
  });

  it('auth routes match the canonical backend auth router', () => {
    // auth.py exposes: login, register, logout, me, forgot-password, reset-password,
    // change-password, sessions, api-keys (no `refresh` key here).
    expect(API_ENDPOINTS.auth.login).toBe(`${env.API_URL}/api/v1/auth/login`);
    expect(API_ENDPOINTS.auth.register).toBe(`${env.API_URL}/api/v1/auth/register`);
    expect(API_ENDPOINTS.auth.me).toBe(`${env.API_URL}/api/v1/auth/me`);
    expect(API_ENDPOINTS.auth.logout).toBe(`${env.API_URL}/api/v1/auth/logout`);
    expect(API_ENDPOINTS.auth.forgotPassword).toBe(`${env.API_URL}/api/v1/auth/forgot-password`);
  });
});
