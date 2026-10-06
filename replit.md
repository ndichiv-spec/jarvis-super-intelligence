# JARVIS Super AI

A holographic AI dashboard platform with multi-tier intelligence, neural chat, agent orchestration, system monitoring, and advanced visualization tools.

## Run & Operate

- `pnpm --filter @workspace/jarvis run dev` — run the frontend (reads $PORT)
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- Frontend: React 19.1.0 + Vite 7 (artifact: `artifacts/jarvis`)
- Routing: wouter 3.x (replaces Next.js App Router)
- State: Zustand v5 (always use selectors — never `useStore()` without a selector)
- UI: framer-motion 12.x, recharts, lucide-react, next-themes (Vite-compatible)
- Forms: react-hook-form
- Notifications: sonner (toast)

## Where things live

- Frontend: `artifacts/jarvis/src/`
  - Pages: `src/pages/` (wouter routes in `src/App.tsx`)
  - Layouts: `src/layouts/DashboardLayout.tsx`
  - State stores: `src/stores/` (Zustand v5)
  - API client: `src/lib/api.ts`
  - WebSocket: `src/lib/websocket.ts`
  - Theme: `src/styles/` + `src/components/neural-theme-provider.tsx`
- Note: `src/app/` directory contains unused Next.js App Router files — safe to ignore

## Architecture decisions

- Migrated from Next.js 15 + FastAPI (Python) to Vite + React frontend-only
- Python backend NOT migrated — frontend shows "Backend Connection Lost" banner when backend is absent (expected)
- Zustand v5 requires selectors on every `useStore()` call — bare calls return new object every render and cause infinite loops
- API base: `import.meta.env.VITE_API_URL || ''` (relative paths through Replit proxy)
- WS base: dynamic from `window.location.host` (protocol-aware wss/ws)
- wouter replaces Next.js `useRouter` / `Link` — use `useLocation()` for programmatic navigation

## Product

JARVIS is a multi-tier AI command center featuring:
- **SUPREME UI** — full neural chat interface with live AI conversations
- **OMEGA Control** — autonomous AI operations panel with model benchmarking
- **System Dashboard** — real-time CPU/memory/process monitoring
- **Knowledge Matrix** — knowledge base with document ingestion
- **Cognitive Systems** — memory, consciousness, and emotional intelligence views
- **Agent Orchestration** — AI agent management and spawning
- **Holographic Interface** — Arc Reactor visualization and neural network canvas
- **Image Generation** — DALL-E / Stable Diffusion / Replicate interface
- **Voice Interface** — TTS and ASR command center
- **Workflow Automation** — 28+ action types workflow builder
- **Admin Panel** — user management, roles, audit logs

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

- **Zustand v5**: NEVER call `useStore()` without a selector — always `useStore((s) => s.field)`. Bare calls return a new object reference each render, causing infinite re-render loops.
- **wouter vs Next.js**: `useLocation()` returns `[location, setLocation]`. Use `setLocation('/path')` to navigate. There is no `router` variable — remove any dependency array entries referencing `router`.
- **Backend absent**: All API calls return 502 (backend not running). This is expected. The UI shows a "Backend Connection Lost" banner. Pages still render with placeholder/empty data.
- **`src/app/` is dead code**: The Next.js App Router files are still present but unused by Vite. Do not import from them.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
