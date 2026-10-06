'use client';

import { useEffect, useState } from 'react';
import { Mic, MicOff, Radio, Sparkles } from 'lucide-react';

import { cn } from '@/lib/utils';
import { AudioVisualizer, type VisualizerVariant } from '@/components/voice/audio-visualizer';
import { useMicLevel } from '@/components/voice/use-mic-level';
import { Button } from '@/components/ui/button';
import { useVoiceStore } from '@/features/voice/store';

/**
 * Voice presence control.
 *
 * Combines a microphone toggle with an audio-reactive visualizer so the user can
 * see the assistant's listening and speaking states at a glance, rather than
 * inferring them from text alone.
 *
 * The visualizer drives its amplitude from whichever source is available, in
 * priority order:
 *   1. a live `AnalyserNode` level, when the microphone is engaged;
 *   2. a synthetic envelope derived from the assistant's speaking state, when
 *      text-to-speech is running but no mic is attached.
 *
 * That second fallback matters because the current backend streams PCM over a
 * WebSocket rather than exposing an audio element to attach an analyser to, so
 * there is no client-side tap on speech playback yet. The synthetic envelope is
 * labelled as such in the accessible name so it is never mistaken for a real
 * measurement.
 */

export type VoicePresenceState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

interface VoiceOrbProps {
  state: VoicePresenceState;
  level?: number;
  size?: number;
  className?: string;
}

const ORB_TONE: Record<VoicePresenceState, { ring: string; core: string; label: string }> = {
  idle: { ring: 'rgba(148,163,184,0.35)', core: 'hsl(200 20% 60%)', label: 'Idle' },
  listening: { ring: 'rgba(0,212,255,0.75)', core: 'hsl(190 100% 55%)', label: 'Listening' },
  thinking: { ring: 'rgba(167,139,250,0.75)', core: 'hsl(258 90% 70%)', label: 'Thinking' },
  speaking: { ring: 'rgba(0,229,160,0.8)', core: 'hsl(174 100% 50%)', label: 'Speaking' },
  error: { ring: 'rgba(239,68,68,0.7)', core: 'hsl(0 84% 60%)', label: 'Error' },
};

/** Radial state indicator for the assistant. */
export function VoiceOrb({ state, level = 0, size = 96, className }: VoiceOrbProps) {
  const tone = ORB_TONE[state];
  const amplitude = Math.max(0, Math.min(1, level));

  return (
    <div
      className={cn('relative grid place-items-center', className)}
      style={{ width: size, height: size }}
      role="status"
      aria-label={`Assistant ${tone.label.toLowerCase()}`}
    >
      {/* Halo scales with amplitude so speech is visible from across the room */}
      <span
        aria-hidden="true"
        className="absolute inset-0 rounded-full transition-transform duration-200"
        style={{
          transform: `scale(${1 + amplitude * 0.22})`,
          boxShadow: `0 0 ${18 + amplitude * 46}px ${tone.ring}`,
          opacity: 0.55 + amplitude * 0.45,
        }}
      />
      {/* Static ring so the control keeps a defined edge at silence */}
      <span
        aria-hidden="true"
        className="absolute inset-1 rounded-full border"
        style={{ borderColor: tone.ring }}
      />
      <span
        aria-hidden="true"
        className="rounded-full transition-all duration-200"
        style={{
          width: `${34 + amplitude * 22}%`,
          height: `${34 + amplitude * 22}%`,
          background: `radial-gradient(circle at 35% 30%, ${tone.core}, transparent 70%)`,
          boxShadow: `inset 0 0 18px ${tone.ring}`,
        }}
      />
    </div>
  );
}

interface VoicePresenceProps {
  /** Override the store-derived state (useful in tests and demos). */
  state?: VoicePresenceState;
  /**
   * Drive the component from external state instead of the voice store.
   *
   * The voice control panel owns its own listening/speaking flags rather than
   * reading the store, so it passes them here. Left unset, the store is used.
   */
  isSpeaking?: boolean;
  isListening?: boolean;
  variant?: VisualizerVariant;
  /** Engage the microphone to drive the visualizer with real input. */
  enableMic?: boolean;
  width?: number;
  height?: number;
  className?: string;
  onTranscript?: (text: string) => void;
  /** Hide the built-in microphone toggle when the caller provides its own. */
  showMicToggle?: boolean;
}

/**
 * Derive a synthetic amplitude envelope for the speaking state.
 *
 * A pair of out-of-phase sines approximates speech cadence -- syllable bursts
 * separated by short pauses -- closely enough to read as "talking" without
 * claiming to be a measurement of the actual signal.
 */
function syntheticEnvelope(elapsed: number, active: boolean): number {
  if (!active) return 0;
  const syllable = (Math.sin(elapsed / 90) + 1) / 2;
  const phrase = (Math.sin(elapsed / 620 + 1.2) + 1) / 2;
  const gate = phrase > 0.25 ? 1 : 0.25;
  return Math.min(1, syllable * gate * 0.85);
}

export function VoicePresence({
  state: stateOverride,
  isSpeaking: isSpeakingOverride,
  isListening: isListeningOverride,
  variant = 'bars',
  enableMic = true,
  width = 260,
  height = 48,
  className,
  onTranscript,
  showMicToggle = true,
}: VoicePresenceProps) {
  const storeIsSpeaking = useVoiceStore((s) => s.isSpeaking);
  const storeIsListening = useVoiceStore((s) => s.isListening);
  const transcript = useVoiceStore((s) => s.transcript);
  const storeError = useVoiceStore((s) => s.error);
  const clearError = useVoiceStore((s) => s.clearError);

  // External overrides win, so a caller owning its own state does not have to
  // mirror it into the store just to light up the visualizer.
  const isSpeaking = isSpeakingOverride ?? storeIsSpeaking;
  const isListening = isListeningOverride ?? storeIsListening;

  const mic = useMicLevel({ autoStart: false });
  const [level, setLevel] = useState(0);
  const micOn = enableMic && mic.active;

  // Imperative subscription: reading the level through React state at frame rate
  // would re-render the tree continuously.
  useEffect(() => {
    if (!micOn) return;
    return mic.subscribe(setLevel);
  }, [mic, micOn]);

  const state: VoicePresenceState =
    stateOverride ??
    (storeError || mic.error
      ? 'error'
      : isSpeaking
        ? 'speaking'
        : isListening
          ? 'listening'
          : 'idle');

  // Fallback envelope, driven by rAF so it runs only while actually speaking.
  //
  // State is only written from inside the frame callback, never synchronously in
  // the effect body: a synchronous write here would cascade an extra render on
  // every transition between speaking and silent. When speech stops the last
  // frame emitted is 0, so the level decays to rest without a separate reset.
  useEffect(() => {
    if (micOn || !isSpeaking) return;

    const start = performance.now();
    let raf: number | null = null;
    let cancelled = false;

    const tick = () => {
      if (cancelled) return;
      setLevel(syntheticEnvelope(performance.now() - start, true));
      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);

    return () => {
      cancelled = true;
      if (raf !== null) cancelAnimationFrame(raf);
      // Release the level so a later render does not inherit a stale amplitude.
      setLevel(0);
    };
  }, [micOn, isSpeaking]);

  useEffect(() => {
    if (transcript && onTranscript) onTranscript(transcript);
  }, [transcript, onTranscript]);

  const activeLevel = micOn ? level : level;
  const isSynthetic = !micOn && isSpeaking;

  return (
    <div className={cn('flex flex-col items-center gap-3', className)}>
      <VoiceOrb state={state} level={activeLevel} />

      <AudioVisualizer
        level={activeLevel}
        variant={variant}
        width={width}
        height={height}
        label={
          isSynthetic
            ? 'Assistant speaking (activity estimate)'
            : micOn
              ? 'Microphone input level'
              : 'Voice activity'
        }
      />

      {enableMic && showMicToggle && (
        <Button
          variant={micOn ? 'default' : 'outline'}
          size="sm"
          onClick={() => (micOn ? mic.stop() : void mic.start())}
          aria-pressed={micOn}
        >
          {micOn ? <Mic className="mr-2 h-3.5 w-3.5" /> : <MicOff className="mr-2 h-3.5 w-3.5" />}
          {micOn ? 'Microphone active' : 'Enable microphone'}
        </Button>
      )}

      <StatusLine state={state} isSynthetic={isSynthetic} error={storeError ?? mic.error} onDismiss={clearError} />

      {transcript && (
        <p className="max-w-md text-center text-[12px] text-muted-foreground/70">“{transcript}”</p>
      )}
    </div>
  );
}

const STATUS_COPY: Record<VoicePresenceState, { text: string; icon: typeof Mic }> = {
  idle: { text: 'Standing by', icon: Mic },
  listening: { text: 'Listening', icon: Mic },
  thinking: { text: 'Processing speech', icon: Sparkles },
  speaking: { text: 'Speaking', icon: Radio },
  error: { text: 'Voice error', icon: MicOff },
};

function StatusLine({
  state,
  isSynthetic,
  error,
  onDismiss,
}: {
  state: VoicePresenceState;
  isSynthetic: boolean;
  error: Error | string | null;
  onDismiss: () => void;
}) {
  const { text, icon: Icon } = STATUS_COPY[state];

  if (state === 'error' && error) {
    const message = typeof error === 'string' ? error : error.message;
    return (
      <div
        role="alert"
        className="flex max-w-md items-center gap-2 rounded-lg border border-red-400/25 bg-red-500/10 px-3 py-1.5 text-[11.5px] text-red-300"
      >
        <MicOff className="h-3.5 w-3.5 shrink-0" />
        <span className="min-w-0 flex-1 truncate">{message}</span>
        <button type="button" onClick={onDismiss} className="shrink-0 underline opacity-70 hover:opacity-100">
          Dismiss
        </button>
      </div>
    );
  }

  return (
    <p className="flex items-center gap-1.5 text-[11px] uppercase tracking-widest text-muted-foreground/60">
      <Icon className={cn('h-3 w-3', state === 'speaking' && 'animate-pulse text-cyan-400')} />
      {text}
      {isSynthetic && <span className="text-[9.5px] normal-case tracking-normal opacity-60">(estimated)</span>}
    </p>
  );
}