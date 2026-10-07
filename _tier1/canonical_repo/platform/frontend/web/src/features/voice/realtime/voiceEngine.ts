import { DEFAULT_VOICE_ENGINE_CONFIG, type VoiceEngineConfig, type VoiceEngineState, type AudioFrame, stateToTokenClass } from './types';
import { AudioEngine, getAudioEngine, destroyAudioEngine } from './audioEngine';
import { VoiceStreamClient } from './streamClient';

let _engine: VoiceEngine | null = null;

export function getVoiceEngine(config?: Partial<VoiceEngineConfig>): VoiceEngine {
  if (!_engine) _engine = new VoiceEngine(config);
  return _engine;
}

export function destroyVoiceEngine(): void {
  _engine?.stop();
  _engine = null;
}

export class VoiceEngine {
  readonly analyser: AnalyserNode;
  private audio: AudioEngine;
  private stream: VoiceStreamClient;
  private _state: VoiceEngineState = 'idle';
  private _transcript = '';
  private _vadSilenceTimer: ReturnType<typeof setTimeout> | null = null;
  private _bargeThreshold = 0.04;
  private _config: VoiceEngineConfig;
  private _streamFrames: ReadableStream<ArrayBuffer> | null = null;
  private _reader: ReadableStreamDefaultReader<ArrayBuffer> | null = null;
  private stateCbs: Array<(s: VoiceEngineState) => void> = [];
  private transcriptCbs: Array<(t: string) => void> = [];
  private streamDataCbs: Array<(d: any) => void> = [];

  constructor(config?: Partial<VoiceEngineConfig>) {
    this._config = { ...DEFAULT_VOICE_ENGINE_CONFIG, ...config };
    this.audio = getAudioEngine(this._config);
    this.analyser = this.audio.analyser;
    this.stream = new VoiceStreamClient(
      (typeof window !== 'undefined'
        ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
        : process.env.NEXT_PUBLIC_WS_URL || '') + '/api/v1/voice/ws/chat',
      this._config
    );
    this._bindStream();
  }

  get state(): VoiceEngineState { return this._state; }

  onStateChange(cb: (s: VoiceEngineState) => void): void { this.stateCbs.push(cb); }
  onTranscript(cb: (t: string) => void): void { this.transcriptCbs.push(cb); }
  onStreamData(cb: (d: any) => void): void { this.streamDataCbs.push(cb); }
  private emitState(s: VoiceEngineState): void { this._state = s; for (const c of this.stateCbs) c(s); }
  private emitTranscript(t: string): void { for (const c of this.transcriptCbs) c(t); }
  private emitStreamData(d: any): void { for (const c of this.streamDataCbs) c(d); }

  async start(): Promise<void> {
    this.emitState('connecting');
    await this.stream.connect();
    await this.audio.start();
    this.emitState('listening');
    this._captureLoop();
  }

  async stop(): Promise<void> {
    this.audio.stop();
    await this.stream.disconnect();
    this._clearVAD();
    this.emitState('idle');
  }

  toggle(): void {
    if (this._state === 'idle' || this._state === 'error') void this.start();
    else void this.stop();
  }

  private async _captureLoop(): Promise<void> {
    while (this._state === 'listening' || this._state === 'thinking' || this._state === 'speaking') {
      const level = this.audio.getLevel();
      if (this._state === 'speaking' && level > this._bargeThreshold) {
        await this.stream.interrupt();
        this.emitState('thinking');
        this.emitState('listening');
        continue;
      }
      if (level > this._config.vadThreshold) {
        this._resetVAD();
        const frame = this.audio.captureFrame();
        this.stream.emit({ type: 'streamData', frame });
        this.emitStreamData(frame);
      } else if (this._state === 'listening') {
        this._scheduleVAD();
      }
      await new Promise(r => setTimeout(r, 20));
    }
  }

  private _resetVAD(): void {
    if (this._vadSilenceTimer) { clearTimeout(this._vadSilenceTimer); this._vadSilenceTimer = null; }
  }

  private _scheduleVAD(): void {
    if (this._vadSilenceTimer) return;
    this._vadSilenceTimer = setTimeout(async () => {
      this.stream.emit({ type: 'streamEnd' });
      await this.stop();
    }, this._config.vadSilenceMs);
  }

  private _clearVAD(): void {
    if (this._vadSilenceTimer) { clearTimeout(this._vadSilenceTimer); this._vadSilenceTimer = null; }
  }

  private _bindStream(): void {
    this.stream.onEvent((e) => {
      switch (e.type) {
        case 'sttDone':
          this.emitTranscript(e.text);
          this.emitState('thinking');
          break;
        case 'stateChanged':
          this.emitState(e.state);
          break;
        case 'ttsStart':
          this.emitState('speaking');
          break;
        case 'ttsEnd':
          this.emitState('listening');
          break;
      }
    });
  }
}