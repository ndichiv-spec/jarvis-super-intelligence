import { DEFAULT_VOICE_ENGINE_CONFIG, type VoiceEngineConfig, type VoiceEngineState, type VoiceEngineEvent, type TTSChunk } from './types';

export class VoiceStreamClient {
  readonly state: VoiceEngineState = 'idle';
  connected = false;
  private ws: WebSocket | null = null;
  private endpoint: string;
  private config: VoiceEngineConfig;
  private pendingFrame = false;
  private reconnectAttempts = 0;
  private maxReconnect = 5;
  private eventCbs: Array<(e: VoiceEngineEvent) => void> = [];
  private onceCbs: Array<(e: VoiceEngineEvent) => void> = [];
  private ttsQueue: TTSChunk[] = [];
  private ttsPlaying = false;
  private ttsCtx: AudioContext | null = null;
  private _interrupted = false;

  constructor(endpoint: string, config?: Partial<VoiceEngineConfig>) {
    this.endpoint = endpoint;
    this.config = { ...DEFAULT_VOICE_ENGINE_CONFIG, ...config };
  }

  onEvent(cb: (e: VoiceEngineEvent) => void): void { this.eventCbs.push(cb); }
  onceEvent(cb: (e: VoiceEngineEvent) => void): void { this.onceCbs.push(cb); }
  notify(e: VoiceEngineEvent): void {
    for (const c of this.eventCbs) c(e);
    for (const c of this.onceCbs) c(e);
    this.onceCbs = [];
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        const ws = new WebSocket(this.endpoint);
        ws.binaryType = 'arraybuffer';
        ws.onopen = () => {
          this.connected = true;
          this.reconnectAttempts = 0;
          this.notify({ type: 'stateChanged', state: 'connecting' });
          resolve();
        };
        ws.onmessage = (ev) => this._onMessage(ev.data);
        ws.onclose = () => { this.connected = false; };
        ws.onerror = (err) => reject(err);
        this.ws = ws;
      } catch (e) {
        reject(e);
      }
    });
  }

  async disconnect(): Promise<void> {
    this.ws?.close();
    this.ws = null;
    this.connected = false;
  }

  async startStream(frames: ReadableStream<ArrayBuffer>): Promise<void> {
    const reader = frames.getReader();
    const pump = async (): Promise<void> => {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (!this.connected) break;
        if (this.pendingFrame) continue;
        this.pendingFrame = true;
        this.ws?.send(value);
        this.pendingFrame = false;
      }
    };
    await pump();
  }

  async interrupt(): Promise<void> {
    this._interrupted = true;
    this.ws?.send(JSON.stringify({ type: 'audio_end' }));
    this.ttsQueue = [];
    this.ttsPlaying = false;
    this.ttsCtx?.close().catch(() => {});
    this.ttsCtx = null;
  }

  private _onMessage(data: ArrayBuffer | string): void {
    try {
      const raw = typeof data === 'string' ? data : new TextDecoder().decode(data);
      const msg = JSON.parse(raw);
      switch (msg.type) {
        case 'stt_text':
          this.notify({ type: 'sttDone', text: msg.text, confidence: msg.confidence ?? 0 });
          break;
        case 'thinking':
          this.notify({ type: 'stateChanged', state: 'thinking' });
          break;
        case 'tts_audio':
          this._enqueueTTS({ text: '', audio: new Uint8Array(msg.audio), done: false });
          break;
        case 'tts_chunk':
          this._enqueueTTS({ text: '', audio: new Uint8Array(msg.data), done: false });
          break;
        case 'tts_done':
          this._enqueueTTS({ text: '', done: true });
          break;
        case 'state':
          this.notify({ type: 'stateChanged', state: msg.state });
          break;
        case 'error':
          this.notify({ type: 'stateChanged', state: 'error' });
          break;
      }
    } catch { /* ignore malformed */ }
  }

  private _enqueueTTS(chunk: TTSChunk): void {
    this.ttsQueue.push(chunk);
    if (!this.ttsPlaying) this._playNext();
  }

  private async _playNext(): Promise<void> {
    if (this.ttsQueue.length === 0) { this.ttsPlaying = false; return; }
    const chunk = this.ttsQueue.shift()!;
    if (chunk.done) { this._playNext(); return; }
    this.ttsPlaying = true;
    try {
      if (!this.ttsCtx) this.ttsCtx = new AudioContext();
      if (this.ttsCtx.state === 'suspended') await this.ttsCtx.resume();
      const buf = this.ttsCtx.createBuffer(1, chunk.audio!.length, 24000);
      buf.getChannelData(0).set(new Float32Array(chunk.audio!.buffer));
      const src = this.ttsCtx.createBufferSource();
      src.buffer = buf;
      src.connect(this.ttsCtx.destination);
      src.start();
      await new Promise<void>((r) => { src.onended = () => r(); });
    } catch { /* ignore playback errors */ }
    this._playNext();
  }
}