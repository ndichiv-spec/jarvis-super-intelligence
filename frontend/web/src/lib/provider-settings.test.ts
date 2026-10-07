import { afterEach, describe, expect, it, vi } from 'vitest';
import { jarvisAPI } from './api';
import type { ProviderSettings } from './api';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('provider settings API contract', () => {
  it('sends editable preferences only and never forwards secret fields', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        success: true,
        settings: {},
        providers: {},
        env_file_exists: false,
        env_path: '',
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const data = {
      ollama_base_url: 'http://localhost:11434',
      ollama_model: 'llama3',
      aws_region: 'us-east-1',
      openai_api_key: 'must-not-be-forwarded',
    } satisfies Partial<ProviderSettings>;
    await jarvisAPI.updateProviderSettings(data);

    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toEqual({
      ollama_base_url: 'http://localhost:11434',
      ollama_model: 'llama3',
      aws_region: 'us-east-1',
    });
  });
});
