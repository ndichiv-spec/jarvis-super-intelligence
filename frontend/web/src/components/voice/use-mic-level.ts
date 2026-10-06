'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Microphone amplitude metering.
 *
 * Exposes a single normalised level (0..1) derived from an `AnalyserNode`, which
 * is what the audio visualizers consume. Polling from the animation loop is
 * necessary because `AnalyserNode` has no push-based level callback.
 *
 * All level samples are forced through one ref. Pushing a new value into React
 * state at frame rate would re-render the component tree 60 times a second, so
 * subscribers are instead notified imperatively via {@link subscribe}.
 */

export interface MicLevelOptions {
  /** Start listening as soon as the hook mounts. */
  autoStart?: boolean;
  /** Smoothing factor between 0 (no smoothing) and 1 (very slow). */
  smoothing?: number;
}

export interface MicLevelController {
  /** True while a capture stream is active. */
  readonly active: boolean;
  /** Error from the most recent start attempt. */
  readonly error: Error | null;
  start: () => Promise<void>;
  stop: () => void;
  /**
   * Register a callback invoked on each animation frame with the smoothed
   * level (0..1).
   *
   * There is deliberately no `level` property on the controller. A level
   * sampled at frame rate cannot be stored in state without re-rendering the
   * component tree 60 times a second, and it cannot be read from a ref during
   * render either, because refs are not render-safe. Consumers therefore opt in
   * per frame through this subscription.
   */
  subscribe: (listener: (level: number) => void) => () => void;
}

export function useMicLevel(options: MicLevelOptions = {}): MicLevelController {
  const { autoStart = false, smoothing = 0.15 } = options;

  const [active, setActive] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const levelRef = useRef(0);
  const smoothedRef = useRef(0);
  const listenersRef = useRef(new Set<(level: number) => void>());

  const contextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const dataRef = useRef<Uint8Array<ArrayBuffer> | null>(null);
  const rafRef = useRef<number | null>(null);

  const subscribe = useCallback((listener: (level: number) => void) => {
    listenersRef.current.add(listener);
    return () => {
      listenersRef.current.delete(listener);
    };
  }, []);

  const stop = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    analyserRef.current = null;
    void contextRef.current?.close().catch(() => undefined);
    contextRef.current = null;
    levelRef.current = 0;
    smoothedRef.current = 0;
    setActive(false);
    // Emit a final zero so subscribers stop rendering a stale non-zero level.
    for (const listener of listenersRef.current) listener(0);
  }, []);

  const start = useCallback(async () => {
    if (typeof window === 'undefined') return;
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setError(new Error('Microphone capture is not available in this browser.'));
      return;
    }

    try {
      setError(null);

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      const AudioCtor =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioCtor) {
        stop();
        setError(new Error('Web Audio API is not available in this browser.'));
        return;
      }

      const context = new AudioCtor();
      contextRef.current = context;
      if (context.state === 'suspended') await context.resume();

      const source = context.createMediaStreamSource(stream);
      const analyser = context.createAnalyser();
      analyser.fftSize = 1024;
      // Smoothing inside the analyser complements the frame-level easing below:
      // the former de-noises the FFT, the latter stops visual jitter.
      analyser.smoothingTimeConstant = 0.6;
      source.connect(analyser);

      // Deliberately not connected to the destination: routing the mic to the
      // speakers would create a feedback loop.
      analyserRef.current = analyser;
      dataRef.current = new Uint8Array(new ArrayBuffer(analyser.frequencyBinCount));

      setActive(true);

      const tick = () => {
        if (!analyserRef.current || !dataRef.current) return;
        analyserRef.current.getByteFrequencyData(dataRef.current);

        // RMS over the bins, weighted toward speech frequencies (roughly
        // 300Hz-4kHz sit in the first ~15% of bins at fftSize 1024). Using the
        // full spectrum would let bass-heavy room noise dominate the reading.
        const limit = Math.max(1, Math.floor(dataRef.current.length * 0.15));
        let sum = 0;
        for (let i = 0; i < limit; i += 1) {
          const value = dataRef.current[i] / 255;
          sum += value * value;
        }
        const rms = Math.sqrt(sum / limit);

        // Perceptual curve: raw RMS spends most of its range near silence, so
        // the visualizer would barely move during normal speech.
        const target = Math.min(1, Math.pow(rms * 3.2, 0.7));

        smoothedRef.current += (target - smoothedRef.current) * smoothing;
        levelRef.current = smoothedRef.current;

        for (const listener of listenersRef.current) listener(levelRef.current);

        rafRef.current = requestAnimationFrame(tick);
      };

      rafRef.current = requestAnimationFrame(tick);
    } catch (cause) {
      stop();
      const message =
        cause instanceof DOMException && cause.name === 'NotAllowedError'
          ? 'Microphone permission denied.'
          : cause instanceof Error
            ? cause.message
            : 'Failed to access the microphone.';
      setError(new Error(message));
    }
  }, [smoothing, stop]);

  useEffect(() => {
    if (!autoStart) return;
    // Deferred so the permission prompt is not raised synchronously inside the
    // effect body, which would commit a state update in the same pass as mount.
    const timer = window.setTimeout(() => {
      void start();
    }, 0);
    return () => {
      window.clearTimeout(timer);
      stop();
    };
  }, [autoStart, start, stop]);

  return { active, error, start, stop, subscribe };
}