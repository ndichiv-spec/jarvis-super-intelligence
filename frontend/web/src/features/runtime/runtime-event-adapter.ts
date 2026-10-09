import { API_ENDPOINTS } from '@/config/api';
import { ApiClientError, apiClient } from '@/lib/api-client';
import type { RuntimeEvent, RuntimeSnapshot } from './presentation-contract';

const CURSOR_KEY_PREFIX = 'jarvis-runtime-cursor:';
const RESUME_PAGE_SIZE = 500;

interface RuntimeResume {
  snapshot: RuntimeSnapshot;
  events: RuntimeEvent[];
  highWaterSequence: number;
  oldestAvailableSequence: number;
  resyncRequired: boolean;
  hasMore: boolean;
}

export interface RuntimeEventAdapterHandlers {
  onSnapshot: (snapshot: RuntimeSnapshot) => void;
  onEvent: (event: RuntimeEvent) => void;
  onError: (error: Error) => void;
}

export function startRuntimeEventAdapter(
  sessionId: string,
  endpointId: string,
  handlers: RuntimeEventAdapterHandlers,
): () => void {
  const controller = new AbortController();
  const cursorKey = `${CURSOR_KEY_PREFIX}${endpointId}:${sessionId}`;
  let lastSequence = readCursor(cursorKey);
  let reconnectAttempt = 0;

  const run = async () => {
    while (!controller.signal.aborted) {
      try {
        if (lastSequence === null) {
          const snapshot = await apiClient.get<RuntimeSnapshot>(
            API_ENDPOINTS.runtime.snapshot(sessionId),
            { retries: 0, timeout: 15000 },
          );
          if (controller.signal.aborted) return;
          handlers.onSnapshot(snapshot);
          saveCursor(cursorKey, snapshot.sequence);
          lastSequence = snapshot.sequence;
        } else {
          let resume: RuntimeResume;
          do {
            resume = await apiClient.get<RuntimeResume>(
              API_ENDPOINTS.runtime.resume(sessionId),
              {
                params: { after: lastSequence, limit: RESUME_PAGE_SIZE },
                retries: 0,
                timeout: 15000,
              },
            );
            if (controller.signal.aborted) return;
            if (resume.resyncRequired) {
              handlers.onSnapshot(resume.snapshot);
              saveCursor(cursorKey, resume.highWaterSequence);
              lastSequence = resume.highWaterSequence;
              break;
            }
            for (const event of resume.events) {
              if (event.sequence <= lastSequence) continue;
              handlers.onEvent(event);
              saveCursor(cursorKey, event.sequence);
              lastSequence = event.sequence;
            }
          } while (resume.hasMore && !controller.signal.aborted);

          if (controller.signal.aborted) return;
          handlers.onSnapshot(resume.snapshot);
          if (resume.highWaterSequence > lastSequence) {
            saveCursor(cursorKey, resume.highWaterSequence);
            lastSequence = resume.highWaterSequence;
          }
        }

        const url = new URL(API_ENDPOINTS.runtime.events);
        url.searchParams.set('session_id', sessionId);
        url.searchParams.set('after', String(lastSequence));

        const response = await fetch(url, {
          method: 'GET',
          headers: {
            Accept: 'text/event-stream',
            'Last-Event-ID': String(lastSequence),
          },
          credentials: 'include',
          cache: 'no-store',
          signal: controller.signal,
        });
        if (!response.ok) {
          const message = response.status === 409
            ? 'Runtime history needs snapshot resynchronization.'
            : `Runtime event stream returned HTTP ${response.status}.`;
          throw new ApiClientError(message, response.status);
        }
        if (!response.body) {
          throw new Error('Runtime event stream did not provide a readable body.');
        }

        reconnectAttempt = 0;
        await consumeSse(response.body, controller.signal, (event) => {
          if (event.sequence <= lastSequence!) return;
          handlers.onEvent(event);
          saveCursor(cursorKey, event.sequence);
          lastSequence = event.sequence;
        });
        if (!controller.signal.aborted) {
          reconnectAttempt += 1;
          await waitForReconnect(controller.signal, reconnectAttempt);
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        const normalized = error instanceof Error ? error : new Error(String(error));
        handlers.onError(normalized);
        if (error instanceof ApiClientError && error.status >= 400 && error.status < 500
          && error.status !== 409) return;
        reconnectAttempt += 1;
        await waitForReconnect(controller.signal, reconnectAttempt);
      }
    }
  };

  void run();
  return () => controller.abort();
}

function readCursor(key: string): number | null {
  const stored = localStorage.getItem(key);
  if (stored === null) return null;
  const sequence = Number(stored);
  if (!Number.isSafeInteger(sequence) || sequence < 0) {
    localStorage.removeItem(key);
    return null;
  }
  return sequence;
}

function saveCursor(key: string, sequence: number): void {
  localStorage.setItem(key, String(sequence));
}

function waitForReconnect(signal: AbortSignal, attempt: number): Promise<void> {
  const delay = Math.min(30000, 500 * (2 ** Math.min(attempt - 1, 6)));
  return new Promise<void>((resolve) => {
    const timeout = setTimeout(resolve, delay);
    signal.addEventListener('abort', () => {
      clearTimeout(timeout);
      resolve();
    }, { once: true });
  });
}

async function consumeSse(
  body: ReadableStream<Uint8Array>,
  signal: AbortSignal,
  onEvent: (event: RuntimeEvent) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (!signal.aborted) {
      const { value, done } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      let boundary = buffer.indexOf('\n\n');
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = parseSseFrame(frame);
        if (event) onEvent(event);
        boundary = buffer.indexOf('\n\n');
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined);
  }
}

function parseSseFrame(frame: string): RuntimeEvent | null {
  const data: string[] = [];
  let eventName = '';
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) eventName = line.slice(6).trim();
    if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
  }
  if (eventName === 'resync_required') {
    throw new Error('Runtime event retention requires a fresh snapshot.');
  }
  if (!data.length) return null;
  const parsed: unknown = JSON.parse(data.join('\n'));
  if (
    !parsed
    || typeof parsed !== 'object'
    || !('id' in parsed)
    || !('sequence' in parsed)
    || !('sessionId' in parsed)
    || !('type' in parsed)
    || typeof parsed.id !== 'string'
    || typeof parsed.sequence !== 'number'
    || typeof parsed.sessionId !== 'string'
    || typeof parsed.type !== 'string'
  ) {
    throw new Error('Runtime stream emitted an invalid event envelope.');
  }
  return parsed as RuntimeEvent;
}
