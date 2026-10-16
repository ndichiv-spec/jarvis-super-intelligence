import type { ChatStreamChunk } from './types';

const SSE_DATA_PREFIX = 'data: ';

/**
 * Parse a single SSE line of the form `data: <json>` into a chat stream
 * chunk. Returns `null` when the line is not a data event or its payload is
 * not valid JSON.
 *
 * This is the SINGLE source of truth for chat-SSE parsing and is shared with
 * `chatApi.sendStreamingMessage` (in `api.ts`) so behaviour cannot drift
 * between the live stream handler and its tests. It intentionally mirrors the
 * original inline logic: a line must start with exactly `data: ` (6 chars),
 * the payload is `JSON.parse`'d, and malformed lines are skipped (not thrown).
 */
export function parseSseDataLine(line: string): ChatStreamChunk | null {
  if (!line.startsWith(SSE_DATA_PREFIX)) {
    return null;
  }
  try {
    // `data: ` is 6 characters; mirror the live handler's `slice(6)`.
    return JSON.parse(line.slice(SSE_DATA_PREFIX.length)) as ChatStreamChunk;
  } catch {
    // skip malformed chunks (matches the live handler's try/catch semantics)
    return null;
  }
}
