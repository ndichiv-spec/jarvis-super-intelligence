'use client';

import { ThemeProvider as NextThemesProvider, ThemeProviderProps } from 'next-themes';

export function ThemeProvider({ children, ...props }: ThemeProviderProps) {
  // next-themes renders an inline <script> to prevent theme flash (FOUC).
  // React 19 warns about <script> rendered inside a component, so on the
  // client we mark the script as a JSON data block (never executed by React
  // on the client; the real script already ran from the server HTML).
  const scriptProps =
    typeof window === 'undefined'
      ? undefined
      : { type: 'application/json' as const };

  return (
    <NextThemesProvider {...props} scriptProps={scriptProps}>
      {children}
    </NextThemesProvider>
  );
}