'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import { ThemeProvider as NextThemeProvider } from 'next-themes';

interface AdvancedTheme {
  name: string;
  colors: {
    background: string;
    foreground: string;
    primary: string;
    secondary: string;
    accent: string;
    border: string;
    muted: string;
    card: string;
    glow: string;
    gradient: string;
  };
  effects: {
    glassmorphism: boolean;
    neumorphism: boolean;
    holographic: boolean;
    cyberpunk: boolean;
  };
}

const advancedThemes: Record<string, AdvancedTheme> = {
  'jarvis-quantum': {
    name: 'Jarvis Quantum',
    colors: {
      background: 'linear-gradient(135deg, #0a0a0f 0%, #1a1a2e 50%, #16213e 100%)',
      foreground: '#e0e0ff',
      primary: '#00ffff',
      secondary: '#ff00ff',
      accent: '#ffff00',
      border: 'rgba(0, 255, 255, 0.3)',
      muted: 'rgba(255, 255, 255, 0.1)',
      card: 'rgba(26, 26, 46, 0.8)',
      glow: 'rgba(0, 255, 255, 0.5)',
      gradient: 'linear-gradient(45deg, #00ffff, #ff00ff, #ffff00)'
    },
    effects: {
      glassmorphism: true,
      neumorphism: false,
      holographic: true,
      cyberpunk: false
    }
  },
  'cyberpunk-night': {
    name: 'Cyberpunk Night',
    colors: {
      background: 'linear-gradient(135deg, #0d0221 0%, #1a0033 50%, #330867 100%)',
      foreground: '#ff00ff',
      primary: '#ff0080',
      secondary: '#00ffff',
      accent: '#ffff00',
      border: 'rgba(255, 0, 255, 0.5)',
      muted: 'rgba(255, 0, 128, 0.1)',
      card: 'rgba(26, 0, 51, 0.9)',
      glow: 'rgba(255, 0, 128, 0.6)',
      gradient: 'linear-gradient(45deg, #ff0080, #00ffff, #ffff00)'
    },
    effects: {
      glassmorphism: true,
      neumorphism: false,
      holographic: false,
      cyberpunk: true
    }
  },
  'neural-dark': {
    name: 'Neural Dark',
    colors: {
      background: 'linear-gradient(135deg, #000000 0%, #0f3460 50%, #16213e 100%)',
      foreground: '#00ff88',
      primary: '#00ff88',
      secondary: '#0088ff',
      accent: '#ffaa00',
      border: 'rgba(0, 255, 136, 0.3)',
      muted: 'rgba(0, 255, 136, 0.1)',
      card: 'rgba(15, 52, 96, 0.8)',
      glow: 'rgba(0, 255, 136, 0.4)',
      gradient: 'linear-gradient(45deg, #00ff88, #0088ff, #ffaa00)'
    },
    effects: {
      glassmorphism: true,
      neumorphism: true,
      holographic: false,
      cyberpunk: false
    }
  },
  'holographic-dark': {
    name: 'Holographic Dark',
    colors: {
      background: 'linear-gradient(135deg, #0a0a0a 0%, #1a1a1a 50%, #2a2a2a 100%)',
      foreground: '#ffffff',
      primary: '#ff0088',
      secondary: '#00ffff',
      accent: '#ffff00',
      border: 'rgba(255, 0, 136, 0.3)',
      muted: 'rgba(255, 255, 255, 0.1)',
      card: 'rgba(42, 42, 42, 0.8)',
      glow: 'rgba(255, 0, 136, 0.5)',
      gradient: 'linear-gradient(45deg, #ff0088, #00ffff, #ffff00, #ff0088)'
    },
    effects: {
      glassmorphism: true,
      neumorphism: false,
      holographic: true,
      cyberpunk: false
    }
  }
};

interface AdvancedThemeContextType {
  currentTheme: string;
  setTheme: (theme: string) => void;
  theme: AdvancedTheme;
  availableThemes: string[];
}

const AdvancedThemeContext = createContext<AdvancedThemeContextType | undefined>(undefined);

export const useAdvancedTheme = () => {
  const context = useContext(AdvancedThemeContext);
  if (!context) {
    throw new Error('useAdvancedTheme must be used within AdvancedThemeProvider');
  }
  return context;
};

export const AdvancedThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [currentTheme, setCurrentTheme] = useState('jarvis-quantum');

  useEffect(() => {
    const root = document.documentElement;
    const theme = advancedThemes[currentTheme];
    
    // Apply CSS custom properties
    root.style.setProperty('--advanced-bg', theme.colors.background);
    root.style.setProperty('--advanced-fg', theme.colors.foreground);
    root.style.setProperty('--advanced-primary', theme.colors.primary);
    root.style.setProperty('--advanced-secondary', theme.colors.secondary);
    root.style.setProperty('--advanced-accent', theme.colors.accent);
    root.style.setProperty('--advanced-border', theme.colors.border);
    root.style.setProperty('--advanced-muted', theme.colors.muted);
    root.style.setProperty('--advanced-card', theme.colors.card);
    root.style.setProperty('--advanced-glow', theme.colors.glow);
    root.style.setProperty('--advanced-gradient', theme.colors.gradient);
    
    // Apply effects
    root.style.setProperty('--glassmorphism', theme.effects.glassmorphism ? '1' : '0');
    root.style.setProperty('--neumorphism', theme.effects.neumorphism ? '1' : '0');
    root.style.setProperty('--holographic', theme.effects.holographic ? '1' : '0');
    root.style.setProperty('--cyberpunk', theme.effects.cyberpunk ? '1' : '0');
  }, [currentTheme]);

  const setTheme = (theme: string) => {
    if (advancedThemes[theme]) {
      setCurrentTheme(theme);
    }
  };

  return (
    <AdvancedThemeContext.Provider value={{
      currentTheme,
      setTheme,
      theme: advancedThemes[currentTheme],
      availableThemes: Object.keys(advancedThemes)
    }}>
      <NextThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
        {children}
      </NextThemeProvider>
    </AdvancedThemeContext.Provider>
  );
};
