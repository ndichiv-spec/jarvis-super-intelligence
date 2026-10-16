import { describe, it, expect } from 'vitest';
import { parseSseDataLine } from './sse';

describe('parseSseDataLine (chat SSE stream parser)', () => {
  it('parses a valid `data: <json>` line into a chunk', () => {
    expect(parseSseDataLine('data: {"type":"chunk","content":"hello"}')).toEqual({
      type: 'chunk',
      content: 'hello',
    });
  });

  it('returns null for non-data lines (kept-alive, events, blanks)', () => {
    expect(parseSseDataLine(': keepalive')).toBeNull();
    expect(parseSseDataLine('event: chunk')).toBeNull();
    expect(parseSseDataLine('retry: 2000')).toBeNull();
    expect(parseSseDataLine('')).toBeNull();
  });

  it('returns null for malformed or empty JSON payload (skipped, not thrown)', () => {
    // `data: {broken` is invalid JSON -> JSON.parse throws -> null
    expect(parseSseDataLine('data: {broken')).toBeNull();
    // empty payload after the prefix -> JSON.parse('') throws -> null
    expect(parseSseDataLine('data: ')).toBeNull();
  });

  it('slices exactly the 6-char `data: ` prefix, preserving payloads that start with the same text', () => {
    expect(parseSseDataLine('data: {"payload":"data: value"}')).toEqual({
      payload: 'data: value',
    });
  });

  it('treats `data:` WITHOUT a trailing space as a non-data line (matches the live handler)', () => {
    // the live handler only acts on `data: ` (with space); `data:` alone is skipped
    expect(parseSseDataLine('data:{"type":"chunk"}')).toBeNull();
  });

  it('preserves structured chunk fields unchanged', () => {
    // Deep-equality on the whole object avoids depending on ChatStreamChunk's
    // exact declared shape — this is the runtime JSON the backend emits.
    expect(
      parseSseDataLine(
        'data: {"type":"done","session_id":"s1","status":"COMPLETED","latency_ms":142}'
      )
    ).toEqual({ type: 'done', session_id: 's1', status: 'COMPLETED', latency_ms: 142 });
  });
});
