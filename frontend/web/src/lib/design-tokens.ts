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
} as const;

export type DesignTokenKey = keyof typeof designTokens;
