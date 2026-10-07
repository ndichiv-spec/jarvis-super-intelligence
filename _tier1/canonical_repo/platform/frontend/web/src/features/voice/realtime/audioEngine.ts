import { DEFAULT_VOICE_ENGINE_CONFIG, type VoiceEngineConfig, type AudioFrame } from './types';

export class AudioEngineError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AudioEngineError';
  }
}

let _instance: AudioEngine | null = null;

export function getAudioEngine(config?: Partial<VoiceEngineConfig>): AudioEngine {
  if (!_instance) {
    _instance = new AudioEngine(config);
  }
  return _instance;
}

export function destroyAudioEngine(): void {
  if (_instance) {
    _instance.stop();
    _instance = null;
  }
}

export class AudioEngine {
  readonly analyser: AnalyserNode;
  readonly config: VoiceEngineConfig;
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private _isActive = false;
  private _hasPermission = false;
  private _level = 0;
  private _frameCount = 0;

  constructor(config?: Partial<VoiceEngineConfig>) {
    this.config = { ...DEFAULT_VOICE_ENGINE_CONFIG, ...config };
    this.analyser = this._createAnalyser(this.config.fftSize, this.config.smoothingGain);
  }

  get isActive(): boolean { return this._isActive; }
  get hasPermission(): boolean { return this._hasPermission; }
  get frameCount(): number { return this._frameCount; }

  private _createAnalyser(fftSize: number, smoothing: number): AnalyserNode {
    const ac = new AudioContext({ sampleRate: this.config.sampleRate });
    this.ctx = ac;
    const a = ac.createAnalyser();
    a.fftSize = fftSize;
    a.smoothingTimeConstant = smoothing;
    this._frameCount = fftSize / 2;
    return a;
  }

  async requestPermission(): Promise<boolean> {
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: false },
      });
      this.stream = s;
      this._hasPermission = true;
      return true;
    } catch {
      this._hasPermission = false;
      throw new AudioEngineError('MIC_ACCESS_DENIED');
    }
  }

  async start(): Promise<void> {
    if (!this._hasPermission) await this.requestPermission();
    if (!this.ctx) this._createAnalyser(this.config.fftSize, this.config.smoothingGain);
    if (this.ctx?.state === 'suspended') await this.ctx.resume();
    if (!this.source && this.stream) {
      this.source = this.ctx!.createMediaStreamSource(this.stream);
      this.source.connect(this.analyser);
    }
    this._isActive = true;
  }

  stop(): void {
    this._isActive = false;
    if (this.source) { this.source.disconnect(); this.source = null; }
    if (this.stream) { this.stream.getTracks().forEach(t => t.stop()); this.stream = null; }
  }

  getLevel(): number {
    if (!this._isActive) return 0;
    const buf = new Float32Array(this.analyser.fftSize);
    this.analyser.getFloatTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
    const rms = Math.sqrt(sum / buf.length);
    this._level = Math.min(1, rms * 3);
    return this._level;
  }

  captureFrame(): AudioFrame {
    const buf = new Float32Array(this.analyser.fftSize);
    this.analyser.getFloatTimeDomainData(buf);
    const pcm = new Int16Array(buf.length);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) {
      const s = Math.max(-1, Math.min(1, buf[i]));
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      sum += s * s;
    }
    const rms = Math.sqrt(sum / buf.length);
    return { pcm, timestamp: performance.now(), level: Math.min(1, rms * 3), durationMs: (buf.length / this.config.sampleRate) * 1000 };
  }
}