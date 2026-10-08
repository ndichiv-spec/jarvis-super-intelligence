export const designTokens = {
  colors: {
    background: { value: 'hsl(210 40% 2%)', hex: '#0a0a0f' },
    foreground: { value: 'hsl(195 100% 90%)', hex: '#b3e5fc' },
    card: { value: 'hsl(210 30% 5%)', hex: '#0d1117' },
    cardForeground: { value: 'hsl(195 100% 90%)', hex: '#b3e5fc' },
    primary: { value: 'hsl(190 100% 50%)', hex: '#00d4ff' },
    primaryForeground: { value: 'hsl(210 40% 5%)', hex: '#0a0a0f' },
    secondary: { value: 'hsl(210 30% 8%)', hex: '#0a0f1a' },
    secondaryForeground: { value: 'hsl(195 100% 90%)', hex: '#b3e5fc' },
    muted: { value: 'hsl(210 20% 15%)', hex: '#1a1f2d' },
    mutedForeground: { value: 'hsl(195 50% 65%)', hex: '#689fb0' },
    accent: { value: 'hsl(174 100% 45%)', hex: '#00e5a0' },
    accentForeground: { value: 'hsl(210 40% 5%)', hex: '#0a0a0f' },
    border: { value: 'hsl(190 60% 20%)', hex: '#0d232e' },
    input: { value: 'hsl(190 60% 20%)', hex: '#0d232e' },
    ring: { value: 'hsl(190 100% 50%)', hex: '#00d4ff' },
    success: { value: 'hsl(142 71% 45%)', hex: '#22c55e' },
    warning: { value: 'hsl(38 92% 50%)', hex: '#f59e0b' },
    info: { value: 'hsl(190 100% 50%)', hex: '#00d4ff' },
    destructive: { value: 'hsl(0 84% 60%)', hex: '#ef4444' },
  },

  gradients: {
    primary: 'linear-gradient(135deg, #00d4ff, #00e5a0, #00d4ff)',
    secondary: 'linear-gradient(135deg, #0078d4, #00d4ff)',
    glow: 'linear-gradient(135deg, rgba(0,212,255,0.3), rgba(0,229,160,0.1))',
    card: 'linear-gradient(135deg, rgba(0,212,255,0.08), rgba(0,229,160,0.04), rgba(0,120,212,0.06))',
    holoWindow: 'linear-gradient(180deg, rgba(3,7,18,0.95), rgba(0,20,40,0.9))',
    holoTitlebar: 'linear-gradient(90deg, rgba(0,212,255,0.12), rgba(0,229,160,0.06), rgba(0,120,212,0.08))',
    holoButton: 'linear-gradient(135deg, rgba(0,212,255,0.15), rgba(0,229,160,0.1))',
    userCard: 'linear-gradient(135deg, rgba(0,120,212,0.2), rgba(0,212,255,0.15))',
    assistantCard: 'linear-gradient(135deg, rgba(0,212,255,0.08), rgba(0,229,160,0.05))',
  },

  shadows: {
    glow: '0 0 40px rgba(0,212,255,0.2), 0 0 80px rgba(0,212,255,0.1)',
    card: '0 0 20px rgba(0,212,255,0.1), 0 4px 16px rgba(0,0,0,0.5)',
    holoWindow: '0 0 30px rgba(0,212,255,0.15), 0 0 60px rgba(0,212,255,0.08), 0 8px 32px rgba(0,0,0,0.6)',
    holoButton: '0 0 10px rgba(0,212,255,0.15)',
    holoButtonHover: '0 0 20px rgba(0,212,255,0.25)',
  },

  typography: {
    fontMono: 'font-mono',
    fontFamily: "'Inter', system-ui, sans-serif",
    sizes: {
      xs: '0.75rem',
      sm: '0.875rem',
      base: '1rem',
      lg: '1.125rem',
      xl: '1.25rem',
      xl2: '1.5rem',
      xl3: '1.875rem',
      xl4: '2.25rem',
      xl5: '3rem',
      xl6: '3.75rem',
      xl7: '4.5rem',
      xl8: '6rem',
    },
  },

  spacing: {
    xs: '0.25rem',
    sm: '0.5rem',
    md: '1rem',
    lg: '1.5rem',
    xl: '2rem',
    xl2: '3rem',
    xl3: '4rem',
    xl4: '6rem',
  },

  radius: {
    sm: 'calc(var(--radius) - 4px)',
    md: 'calc(var(--radius) - 2px)',
    lg: 'var(--radius)',
    xl: '1rem',
    full: '9999px',
  },

  sidebarWidth: 280,
  headerHeight: 64,

  glass: {
    light: 'rgba(255,255,255,0.03)',
    medium: 'rgba(255,255,255,0.05)',
    dark: 'rgba(255,255,255,0.02)',
    border: 'rgba(255,255,255,0.05)',
    stronger: 'rgba(255,255,255,0.08)',
  },

  /** Per-state color ramps for the voice orb, waveform, and audio bars. */
  voice: {
    idle: {
      ring: '#2a3346',
      glow: 'rgba(26,31,45,0.6)',
      bar: '#1a1f2d',
      barActive: '#3b4a63',
      label: '#689fb0',
      waveform: '#1a1f2d',
    },
    connecting: {
      ring: '#689fb0',
      glow: 'rgba(104,159,176,0.4)',
      bar: '#689fb0',
      barActive: '#7dd3fc',
      label: '#7dd3fc',
      waveform: '#689fb0',
    },
    listening: {
      ring: '#00d4ff',
      glow: 'rgba(0,212,255,0.45)',
      bar: '#00d4ff',
      barActive: '#00e5a0',
      label: '#00d4ff',
      waveform: '#00d4ff',
    },
    thinking: {
      ring: '#f59e0b',
      glow: 'rgba(245,158,11,0.45)',
      bar: '#f59e0b',
      barActive: '#fbbf24',
      label: '#fbbf24',
      waveform: '#f59e0b',
    },
    speaking: {
      ring: '#00e5a0',
      glow: 'rgba(0,229,160,0.45)',
      bar: '#00e5a0',
      barActive: '#5eead4',
      label: '#00e5a0',
      waveform: '#00e5a0',
    },
    processing: {
      ring: '#0078d4',
      glow: 'rgba(0,120,212,0.45)',
      bar: '#0078d4',
      barActive: '#38bdf8',
      label: '#38bdf8',
      waveform: '#0078d4',
    },
    error: {
      ring: '#ef4444',
      glow: 'rgba(239,68,68,0.45)',
      bar: '#ef4444',
      barActive: '#f87171',
      label: '#f87171',
      waveform: '#ef4444',
    },
  },

  /** Geometry / analysis parameters for the voice visualizer. */
  audio: {
    barCount: 48,
    minBarHeight: '2px',
    maxBarHeight: '72px',
    barGap: '3px',
    barRadius: '2px',
    fftSize: 2048,
    smoothing: 0.78,
    ringThickness: '2px',
    orbSize: 220,
  },

  /** Status chip color triples (translucent bg + matching border + label). */
  states: {
    pending: {
      bg: 'rgba(104,159,176,0.12)',
      fg: '#689fb0',
      border: 'rgba(104,159,176,0.35)',
    },
    running: {
      bg: 'rgba(0,212,255,0.12)',
      fg: '#00d4ff',
      border: 'rgba(0,212,255,0.35)',
    },
    complete: {
      bg: 'rgba(34,197,94,0.12)',
      fg: '#22c55e',
      border: 'rgba(34,197,94,0.35)',
    },
    failed: {
      bg: 'rgba(239,68,68,0.12)',
      fg: '#ef4444',
      border: 'rgba(239,68,68,0.35)',
    },
    skipped: {
      bg: 'rgba(26,31,45,0.6)',
      fg: '#94a3b8',
      border: 'rgba(148,163,184,0.3)',
    },
    needsReview: {
      bg: 'rgba(245,158,11,0.12)',
      fg: '#f59e0b',
      border: 'rgba(245,158,11,0.35)',
    },
    unavailable: {
      bg: 'rgba(148,163,184,0.08)',
      fg: '#64748b',
      border: 'rgba(148,163,184,0.25)',
    },
  },

  /**
   * Categorical series palette - 8 hues that stay distinguishable on the
   * #0a0a0f background and remain separable under common colorblind types.
   */
  charts: {
    series: {
      cyan: '#00d4ff',
      teal: '#00e5a0',
      amber: '#f59e0b',
      violet: '#a78bfa',
      rose: '#fb7185',
      lime: '#a3e635',
      orange: '#fb923c',
      slate: '#94a3b8',
    },
    grid: 'rgba(0,212,255,0.08)',
    axis: 'rgba(0,212,255,0.2)',
    surface: 'rgba(0,212,255,0.04)',
  },

  /** Spacing + surface defaults for agent-generated (generative) UI. */
  generativeUi: {
    spacing: {
      xs: '0.25rem',
      sm: '0.5rem',
      md: '0.75rem',
      lg: '1rem',
      xl: '1.5rem',
      '2xl': '2rem',
    },
    radius: '12px',
    border: '1px solid rgba(0,212,255,0.15)',
    surface: 'rgba(3,7,18,0.85)',
    accent: '#00d4ff',
  },

  /** Shared motion tokens - short, glow-led, non-bouncy. */
  motion: {
    fast: '120ms',
    normal: '220ms',
    slow: '400ms',
    spring: {
      stiffness: 260,
      damping: 26,
    },
    easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
  },
} as const;

export type DesignTokenKey = keyof typeof designTokens;

export type VoiceState = keyof typeof designTokens.voice;
export type VoiceStateColor = (typeof designTokens.voice)[VoiceState];

/** Safely resolve a voice state token, falling back to `idle`. */
export const voiceStateColor = (state: string): VoiceStateColor =>
  (designTokens.voice as Record<string, VoiceStateColor | undefined>)[state] ??
  designTokens.voice.idle;
