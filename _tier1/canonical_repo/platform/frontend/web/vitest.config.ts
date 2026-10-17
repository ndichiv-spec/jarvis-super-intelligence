import { defineConfig } from 'vitest/config';

// Vitest configuration for the JARVIS Next.js frontend.
//
// Only pure-logic unit tests run here (API-config shape + SSE chunk parsing).
// They use the `node` environment so they execute fast in CI without a browser
// or the Next.js runtime. Components under `src/components|app|lib` are NOT
// imported (they pull in React/Next/JSX), so no jsdom/vite-react plugin is
// needed and the alias `@` is unused by the test import graph.
export default defineConfig({
  test: {
    globals: false,
    environment: 'node',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx', 'tests/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: ['src/features/chat/sse.ts', 'src/config/api.ts'],
    },
    passWithNoTests: false,
    restoreMocks: true,
  },
});
