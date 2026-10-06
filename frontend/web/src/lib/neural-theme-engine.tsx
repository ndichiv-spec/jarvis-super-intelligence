"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

// ============================================================
// NEURAL THEME ENGINE - Advanced AI-Reactive Theming System
// ============================================================

export type ThemeMood = 'neutral' | 'analytical' | 'creative' | 'empathetic' | 'focused' | 'playful' | 'serious';

export interface NeuralThemeConfig {
  id: string;
  name: string;
  description: string;
  colors: {
    primary: string;
    primaryGlow: string;
    secondary: string;
    accent: string;
    background: string;
    backgroundGradient: string;
    surface: string;
    surfaceBorder: string;
    text: string;
    textSecondary: string;
    success: string;
    warning: string;
    error: string;
  };
  effects: {
    particleColor: string;
    glowIntensity: number;
    blurAmount: number;
    animationSpeed: number;
    gridOpacity: number;
    scanlineIntensity: number;
    shimmerEnabled: boolean;
    holographicEnabled: boolean;
  };
  fonts: {
    primary: string;
    mono: string;
    heading: string;
  };
  icon: string;
  author: string;
  version: string;
}

// Pre-built Neural Themes
export const NEURAL_THEMES: NeuralThemeConfig[] = [
  {
    id: 'stark-holographic',
    name: 'Stark Holographic',
    description: 'Original Tony Stark holographic interface with cyan/teal aesthetics',
    icon: '🔷',
    author: 'JARVIS Design System',
    version: '3.0.0',
    colors: {
      primary: '#00d4ff',
      primaryGlow: 'rgba(0, 212, 255, 0.3)',
      secondary: '#0078d4',
      accent: '#00e5a0',
      background: '#030712',
      backgroundGradient: 'radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0, 212, 255, 0.08), transparent), radial-gradient(ellipse 60% 40% at 80% 60%, rgba(0, 229, 160, 0.05), transparent)',
      surface: 'rgba(0, 212, 255, 0.05)',
      surfaceBorder: 'rgba(0, 212, 255, 0.2)',
      text: '#b3e5fc',
      textSecondary: '#81d4fa',
      success: '#10b981',
      warning: '#f59e0b',
      error: '#ef4444',
    },
    effects: {
      particleColor: '#00d4ff',
      glowIntensity: 0.8,
      blurAmount: 24,
      animationSpeed: 1,
      gridOpacity: 0.08,
      scanlineIntensity: 0.03,
      shimmerEnabled: true,
      holographicEnabled: true,
    },
    fonts: {
      primary: 'Inter, -apple-system, sans-serif',
      mono: 'JetBrains Mono, Fira Code, monospace',
      heading: 'Orbitron, sans-serif',
    },
  },
  {
    id: 'quantum-deep',
    name: 'Quantum Deep',
    description: 'Ultra-dark quantum computing aesthetic with deep purple accents',
    icon: '🟣',
    author: 'JARVIS Neural Engine',
    version: '1.0.0',
    colors: {
      primary: '#a78bfa',
      primaryGlow: 'rgba(167, 139, 250, 0.3)',
      secondary: '#7c3aed',
      accent: '#c084fc',
      background: '#0a0a0f',
      backgroundGradient: 'radial-gradient(ellipse 70% 60% at 30% 20%, rgba(167, 139, 250, 0.1), transparent), radial-gradient(ellipse 50% 40% at 70% 80%, rgba(192, 132, 252, 0.08), transparent)',
      surface: 'rgba(167, 139, 250, 0.05)',
      surfaceBorder: 'rgba(167, 139, 250, 0.15)',
      text: '#e9d5ff',
      textSecondary: '#c4b5fd',
      success: '#34d399',
      warning: '#fbbf24',
      error: '#f87171',
    },
    effects: {
      particleColor: '#a78bfa',
      glowIntensity: 0.6,
      blurAmount: 20,
      animationSpeed: 0.7,
      gridOpacity: 0.05,
      scanlineIntensity: 0.02,
      shimmerEnabled: true,
      holographicEnabled: false,
    },
    fonts: {
      primary: 'Inter, -apple-system, sans-serif',
      mono: 'JetBrains Mono, Fira Code, monospace',
      heading: 'Space Grotesk, sans-serif',
    },
  },
  {
    id: 'neural-cyan',
    name: 'Neural Cyan Pulse',
    description: 'AI-reactive theme with pulsing cyan neural network patterns',
    icon: '💎',
    author: 'JARVIS AI',
    version: '1.0.0',
    colors: {
      primary: '#06b6d4',
      primaryGlow: 'rgba(6, 182, 212, 0.35)',
      secondary: '#0891b2',
      accent: '#22d3ee',
      background: '#020617',
      backgroundGradient: 'radial-gradient(ellipse 90% 50% at 50% 0%, rgba(6, 182, 212, 0.12), transparent), radial-gradient(ellipse 60% 40% at 50% 100%, rgba(34, 211, 238, 0.06), transparent)',
      surface: 'rgba(6, 182, 212, 0.06)',
      surfaceBorder: 'rgba(6, 182, 212, 0.2)',
      text: '#cffafe',
      textSecondary: '#a5f3fc',
      success: '#10b981',
      warning: '#f59e0b',
      error: '#ef4444',
    },
    effects: {
      particleColor: '#06b6d4',
      glowIntensity: 0.9,
      blurAmount: 28,
      animationSpeed: 1.2,
      gridOpacity: 0.1,
      scanlineIntensity: 0.04,
      shimmerEnabled: true,
      holographicEnabled: true,
    },
    fonts: {
      primary: 'Inter, -apple-system, sans-serif',
      mono: 'JetBrains Mono, Fira Code, monospace',
      heading: 'Rajdhani, sans-serif',
    },
  },
  {
    id: 'arc-reactor',
    name: 'Arc Reactor Core',
    description: 'Palladium core aesthetic with bright blue-white reactor glow',
    icon: '⚡',
    author: 'Stark Industries',
    version: '1.0.0',
    colors: {
      primary: '#60a5fa',
      primaryGlow: 'rgba(96, 165, 250, 0.4)',
      secondary: '#3b82f6',
      accent: '#93c5fd',
      background: '#020617',
      backgroundGradient: 'radial-gradient(circle at 50% 50%, rgba(96, 165, 250, 0.15), transparent 70%), radial-gradient(ellipse 80% 50% at 50% -20%, rgba(147, 197, 253, 0.08), transparent)',
      surface: 'rgba(96, 165, 250, 0.06)',
      surfaceBorder: 'rgba(96, 165, 250, 0.25)',
      text: '#dbeafe',
      textSecondary: '#bfdbfe',
      success: '#34d399',
      warning: '#fbbf24',
      error: '#f87171',
    },
    effects: {
      particleColor: '#60a5fa',
      glowIntensity: 1.0,
      blurAmount: 32,
      animationSpeed: 1.5,
      gridOpacity: 0.12,
      scanlineIntensity: 0.05,
      shimmerEnabled: true,
      holographicEnabled: true,
    },
    fonts: {
      primary: 'Inter, -apple-system, sans-serif',
      mono: 'JetBrains Mono, Fira Code, monospace',
      heading: 'Orbitron, sans-serif',
    },
  },
  {
    id: 'midnight-emerald',
    name: 'Midnight Emerald',
    description: 'Deep midnight theme with rich emerald green accents',
    icon: '💚',
    author: 'JARVIS Design System',
    version: '1.0.0',
    colors: {
      primary: '#10b981',
      primaryGlow: 'rgba(16, 185, 129, 0.3)',
      secondary: '#059669',
      accent: '#34d399',
      background: '#020a06',
      backgroundGradient: 'radial-gradient(ellipse 70% 50% at 50% 0%, rgba(16, 185, 129, 0.1), transparent), radial-gradient(ellipse 60% 40% at 80% 80%, rgba(52, 211, 153, 0.06), transparent)',
      surface: 'rgba(16, 185, 129, 0.05)',
      surfaceBorder: 'rgba(16, 185, 129, 0.18)',
      text: '#d1fae5',
      textSecondary: '#a7f3d0',
      success: '#10b981',
      warning: '#fbbf24',
      error: '#ef4444',
    },
    effects: {
      particleColor: '#10b981',
      glowIntensity: 0.7,
      blurAmount: 22,
      animationSpeed: 0.8,
      gridOpacity: 0.06,
      scanlineIntensity: 0.02,
      shimmerEnabled: false,
      holographicEnabled: false,
    },
    fonts: {
      primary: 'Inter, -apple-system, sans-serif',
      mono: 'JetBrains Mono, Fira Code, monospace',
      heading: 'Inter, sans-serif',
    },
  },
  {
    id: 'neural-rose',
    name: 'Neural Rose',
    description: 'Warm neural rose with pink-magenta ambient lighting',
    icon: '🌸',
    author: 'JARVIS AI',
    version: '1.0.0',
    colors: {
      primary: '#f43f5e',
      primaryGlow: 'rgba(244, 63, 94, 0.3)',
      secondary: '#e11d48',
      accent: '#fb7185',
      background: '#0a0208',
      backgroundGradient: 'radial-gradient(ellipse 80% 50% at 50% 0%, rgba(244, 63, 94, 0.1), transparent), radial-gradient(ellipse 60% 40% at 20% 80%, rgba(251, 113, 133, 0.06), transparent)',
      surface: 'rgba(244, 63, 94, 0.05)',
      surfaceBorder: 'rgba(244, 63, 94, 0.18)',
      text: '#ffe4e6',
      textSecondary: '#fecdd3',
      success: '#34d399',
      warning: '#fbbf24',
      error: '#ef4444',
    },
    effects: {
      particleColor: '#f43f5e',
      glowIntensity: 0.75,
      blurAmount: 24,
      animationSpeed: 1.1,
      gridOpacity: 0.07,
      scanlineIntensity: 0.03,
      shimmerEnabled: true,
      holographicEnabled: false,
    },
    fonts: {
      primary: 'Inter, -apple-system, sans-serif',
      mono: 'JetBrains Mono, Fira Code, monospace',
      heading: 'Outfit, sans-serif',
    },
  },
];

// AI Mood Detection Mapping
export const MOOD_THEME_MAP: Record<ThemeMood, string> = {
  neutral: 'stark-holographic',
  analytical: 'quantum-deep',
  creative: 'neural-cyan',
  empathetic: 'neural-rose',
  focused: 'arc-reactor',
  playful: 'midnight-emerald',
  serious: 'quantum-deep',
};

interface NeuralThemeContextType {
  activeTheme: NeuralThemeConfig;
  themeId: string;
  setThemeId: (id: string) => void;
  mood: ThemeMood;
  setMood: (mood: ThemeMood) => void;
  autoThemeEnabled: boolean;
  setAutoThemeEnabled: (enabled: boolean) => void;
  applyTheme: (theme: NeuralThemeConfig) => void;
  themes: NeuralThemeConfig[];
}

const NeuralThemeContext = createContext<NeuralThemeContextType | undefined>(undefined);

export function NeuralThemeProvider({ children }: { children: React.ReactNode }) {
  const [themeId, setThemeId] = useState('stark-holographic');
  const [mood, setMood] = useState<ThemeMood>('neutral');
  const [autoThemeEnabled, setAutoThemeEnabled] = useState(false);
  const [preferencesLoaded, setPreferencesLoaded] = useState(false);
  const activeTheme = NEURAL_THEMES.find(t => t.id === themeId) || NEURAL_THEMES[0];

  // Auto-switch theme based on AI mood
  useEffect(() => {
    if (!autoThemeEnabled || mood === 'neutral') return;
    const autoThemeId = MOOD_THEME_MAP[mood];
    if (!autoThemeId || autoThemeId === themeId) return;
    const frame = window.requestAnimationFrame(() => setThemeId(autoThemeId));
    return () => window.cancelAnimationFrame(frame);
  }, [mood, autoThemeEnabled, themeId]);

  const applyTheme = useCallback((theme: NeuralThemeConfig) => {
    const root = document.documentElement;
    
    // Apply CSS custom properties
    root.style.setProperty('--neural-primary', theme.colors.primary);
    root.style.setProperty('--neural-primary-glow', theme.colors.primaryGlow);
    root.style.setProperty('--neural-secondary', theme.colors.secondary);
    root.style.setProperty('--neural-accent', theme.colors.accent);
    root.style.setProperty('--neural-bg', theme.colors.background);
    root.style.setProperty('--neural-bg-gradient', theme.colors.backgroundGradient);
    root.style.setProperty('--neural-surface', theme.colors.surface);
    root.style.setProperty('--neural-surface-border', theme.colors.surfaceBorder);
    root.style.setProperty('--neural-text', theme.colors.text);
    root.style.setProperty('--neural-text-secondary', theme.colors.textSecondary);
    root.style.setProperty('--neural-success', theme.colors.success);
    root.style.setProperty('--neural-warning', theme.colors.warning);
    root.style.setProperty('--neural-error', theme.colors.error);
    
    // Apply effects
    root.style.setProperty('--neural-particle-color', theme.effects.particleColor);
    root.style.setProperty('--neural-glow-intensity', theme.effects.glowIntensity.toString());
    root.style.setProperty('--neural-blur-amount', `${theme.effects.blurAmount}px`);
    root.style.setProperty('--neural-animation-speed', theme.effects.animationSpeed.toString());
    root.style.setProperty('--neural-grid-opacity', theme.effects.gridOpacity.toString());
    root.style.setProperty('--neural-scanline-intensity', theme.effects.scanlineIntensity.toString());
    
    // Apply fonts
    root.style.setProperty('--neural-font-primary', theme.fonts.primary);
    root.style.setProperty('--neural-font-mono', theme.fonts.mono);
    root.style.setProperty('--neural-font-heading', theme.fonts.heading);
    
    // Apply to body
    document.body.style.background = theme.colors.background;
    document.body.style.backgroundImage = theme.colors.backgroundGradient;
    document.body.style.fontFamily = theme.fonts.primary;
  }, []);

  useEffect(() => {
    applyTheme(activeTheme);
  }, [activeTheme, applyTheme]);

  // Persist theme selection
  useEffect(() => {
    if (!preferencesLoaded) return;
    localStorage.setItem('jarvis-neural-theme', themeId);
    localStorage.setItem('jarvis-auto-theme', autoThemeEnabled.toString());
  }, [themeId, autoThemeEnabled, preferencesLoaded]);

  // Load saved theme
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const saved = localStorage.getItem('jarvis-neural-theme');
      const auto = localStorage.getItem('jarvis-auto-theme');
      if (saved && NEURAL_THEMES.some((theme) => theme.id === saved)) setThemeId(saved);
      if (auto !== null) setAutoThemeEnabled(auto === 'true');
      setPreferencesLoaded(true);
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  return (
    <NeuralThemeContext.Provider
      value={{
        activeTheme,
        themeId,
        setThemeId,
        mood,
        setMood,
        autoThemeEnabled,
        setAutoThemeEnabled,
        applyTheme,
        themes: NEURAL_THEMES,
      }}
    >
      {children}
    </NeuralThemeContext.Provider>
  );
}

export function useNeuralTheme() {
  const context = useContext(NeuralThemeContext);
  if (!context) {
    throw new Error('useNeuralTheme must be used within NeuralThemeProvider');
  }
  return context;
}

// AI Mood Detection Helper
export function detectAIMood(text: string, context?: string): ThemeMood {
  const lower = `${text} ${context ?? ''}`.toLowerCase();
  
  // Analytical: code, math, data, logic
  if (/code|function|algorithm|data|math|logic|calculate|analyze/i.test(lower)) {
    return 'analytical';
  }
  
  // Creative: design, create, imagine, art, story
  if (/create|design|imagine|story|art|creative|write|build/i.test(lower)) {
    return 'creative';
  }
  
  // Empathetic: emotion, feel, help, care, support
  if (/feel|emotion|help|support|care|understand|empathy/i.test(lower)) {
    return 'empathetic';
  }
  
  // Focused: concentrate, focus, important, critical
  if (/focus|concentrate|critical|important|urgent|priority/i.test(lower)) {
    return 'focused';
  }
  
  // Playful: fun, game, joke, play, entertainment
  if (/fun|game|joke|play|entertainment|humor/i.test(lower)) {
    return 'playful';
  }
  
  // Serious: security, risk, danger, warning, critical
  if (/security|risk|danger|critical|warning|error|fail/i.test(lower)) {
    return 'serious';
  }
  
  return 'neutral';
}
