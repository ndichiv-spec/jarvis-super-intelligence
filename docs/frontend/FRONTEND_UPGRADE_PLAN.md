# JARVIS Frontend Upgrade Plan

> **Status:** Phase 1, 2, 3, 4, and 5 COMPLETE — all critical bugs fixed, chat experience upgraded, monitoring & system dashboards live, voice interface with TTS voice selection & profile management, agent orchestration dashboard with collaboration graph, conversation sidebar with history, model selector, file attachment area, chat settings panel, browser-native speech recognition, and testing infrastructure scaffolded  
> **Target Stack:** Next.js 16.2 / React 19.2 / TypeScript 6.0.3 / Tailwind CSS 3.5 / shadcn/ui / Zustand 4.5 / Framer Motion 11  
> **Backend:** FastAPI on `http://127.0.0.1:8000` (port 8000 is live and verified) — 495 endpoints, gRPC mesh :50051, MCP `/mcp`, A2A `/a2a`, Temporal.io, Phoenix + LangSmith observability, 9-provider fabric, 15 capabilities, RBAC + audit, model registry with 7 lifecycle states  
> **Frontend:** Next.js 16 app on `http://localhost:3000` (port 3000 is live and verified)  
> **Backend upgrade plan:** See [`docs/backend/BACKEND_UPGRADE_PLAN.md`](BACKEND_UPGRADE_PLAN.md) for the comprehensive backend roadmap (Phases 36–50) covering OpenAI-compatible API surface, fine-tuning/batch processing, files API, embeddings API, prompt management, agent SDK, structured outputs, developer portal, and prompt caching  
> **Completion:** ✅ Phase 1 (Critical Bug Fixes), ✅ Phase 2 (Core Chat Experience — conversation sidebar, model selector, file attachment, per-chat settings, conversation branching), ✅ Phase 3 (Monitoring & System Dashboards + File Browser + System page), ✅ Phase 4 (Browser-native speech recognition, TTS voice selection, profile management), ✅ Phase 5 (Agent orchestration dashboard with collaboration graph), ✅ Testing Infrastructure (Vitest + Playwright scaffolded), ✅ Model selector hooks fix  
> **`tsc --noEmit`:** Passes with exit code 0 from `frontend/web/`  
> **`pytest`:** 18/18 passed in `tests/test_auth.py`

---

## 1. Executive Summary

The JARVIS project maintains **three** frontend codebases:

| Frontend | Path | Framework | Status |
|---|---|---|---|
| **Primary** | `frontend/web/` | Next.js 16 / React 19 / TS 5.4 | **Production — real API integration, SSE streaming, Zustand stores, 725+ source files** |
| **Secondary** | `frontend/jarvis-remix/` | Remix 1.7 / React 18 / TS 5.4 | **Broken — simulated components, runtime crash bug, invalid icon imports, node_modules missing** |
| **Mobile** | `frontend/mobile/` | React Native + Expo | **Functional but outdated endpoints** |

The **primary production frontend** (`frontend/web/`) is already significantly more advanced than the secondary `jarvis-remix/` — it has real API integration via an `ApiClient` class with JWT auto-refresh, Zustand state management with persistence, SSE streaming chat, WebSocket hooks, feature-based architecture, a comprehensive shadcn/ui component library, and glassmorphism design tokens.

This document identifies the concrete gaps between the production frontend and leading AI platforms (ChatGPT, Claude, Gemini), and provides an actionable upgrade plan organized by priority phase. All recommendations are **additive** — they preserve the existing Next.js 16 / React 19 / TypeScript / Tailwind / shadcn/ui / Zustand stack.

---

## 2. Competitor UX Research

### 2.1 ChatGPT (OpenAI)

| Feature | Description | How JARVIS compares |
|---|---|---|
| **Conversations list** | Left sidebar with collapsible conversation history, grouped by date, with rename/delete/pin | JARVIS has conversation management via API but no dedicated sidebar UI in the chat component |
| **File Upload** | Paperclip icon in chat input → drag-and-drop or file picker → file appears as attachment in message | JARVIS has `react-dropzone` installed and `multipart upload` in `api-client.ts` but **no UI in chat** to attach files |
| **Image Upload / Vision** | Users can paste or upload images; GPT-4V analyzes them inline | JARVIS has `/api/v1/multimodal/upload/image` but **no vision chat UI** |
| **Canvas** | Collaborative document editor for code, text, and planning; appears as a split view | JARVIS has no Canvas equivalent |
| **Code Interpreter** | Sandboxed Python execution: users can run code, generate data visualizations, download CSV/pandas outputs | JARVIS has backend sandbox infrastructure (`jarvis_backend/sandbox.py`) but **no frontend integration** |
| **Memory** | Persistent user memories managed via a "Memories" section in Settings; the model surfaces memory context in chat | JARVIS has `/api/v1/memory/*` endpoints and a memory feature folder but **no UI to view/edit memories** |
| **Model Switcher** | Dropdown above the chat input to switch between GPT-4, GPT-4 Turbo, GPT-4o, etc. | JARVIS `real-ai-chat.tsx` uses a single `activeModel` with no selector UI |
| **Per-Chat Settings** | Temperature, top-p, max tokens, web search, code interpreter toggle per conversation | JARVIS has no per-chat settings panel |
| **Shared Links** | Each conversation/message can be shared via a public URL | JARVIS has no shared link functionality |
| **Voice Input** | Browser-native speech-to-text via `navigator.mediaDevices` | JARVIS voice page uses backend WebSocket but not browser-native Web Speech API |

### 2.2 Claude (Anthropic)

| Feature | Description | How JARVIS compares |
|---|---|---|
| **Workspaces** | Separate workspaces with isolated conversation history and knowledge bases | JARVIS has no workspace concept |
| **Artifacts** | Right-hand panel renders structured outputs (documents, code, SVG, HTML) as interactive previews | JARVIS has no artifact system |
| **Document Upload** | Upload PDFs, Word docs, images; Claude can read and discuss them | JARVIS has `/api/v1/multimodal/upload/document` but **no document preview UI** |
| **Conversation Branching** | Click any assistant message → "Continue from here" to fork the conversation | JARVIS has session management but no branching UI |
| **Citations** | Sources and documents are cited inline with hover tooltips | JARVIS chat store supports `sources` but **no citation rendering** |
| **Long Context** | 200K token context windows visualized with a context indicator | JARVIS has system telemetry but no context window indicator |

### 2.3 Gemini (Google)

| Feature | Description | How JARVIS compares |
|---|---|---|
| **Gemini Advanced** | Multi-model provider switching with live status indicators | JARVIS has `/api/v1/models` and `/api/v1/system/status` but no model status visualization |
| **Google Drive Integration** | Attach files from Google Drive directly | Not applicable (self-hosted) |
| **Voice Input** | Real-time speech-to-text with voice activity detection | JARVIS voice page has WebSocket-based listening but not real-time VAD |
| **Image Generation** | Inline image generation and editing (Imagen) | JARVIS has image generation page and `/api/v1/image/generate` — closest match |

### 2.4 Summary of Missing Competitive Features

| # | Feature | ChatGPT | Claude | Gemini | JARVIS Status |
|---|---|---|---|---|---|
| 1 | Conversation history sidebar | ✅ | ✅ | ✅ | ❌ Partial (API only) |
| 2 | File attachment in chat | ✅ | ✅ | ✅ | ❌ No UI |
| 3 | Image upload & vision analysis | ✅ | ✅ | ✅ | ❌ No UI (endpoint exists) |
| 4 | Document upload & preview | ✅ | ✅ | ✅ | ❌ No UI (endpoint exists) |
| 5 | Code interpreter / sandbox | ✅ | ✅ | ❌ | ❌ Backend exists, no frontend |
| 6 | Conversation branching/forking | ✅ | ✅ | ✅ | ❌ No UI |
| 7 | Shared links | ✅ | ✅ | ✅ | ❌ No UI |
| 8 | Model switcher | ✅ | ✅ | ✅ | ❌ Single model |
| 9 | Per-chat settings panel | ✅ | ✅ | ✅ | ❌ No UI |
| 10 | Citation rendering | ✅ | ✅ | ✅ | ❌ No UI |
| 11 | Artifact panel | ✅ | ✅ | ✅ | ❌ No UI |
| 12 | Memory management UI | ✅ | ✅ | ✅ | ❌ No UI (endpoint exists) |

---

## 3. Comprehensive Gap Analysis

### 3.1 Current Strengths of `frontend/web/`

The production frontend already has many modern features:

- **`ApiClient` class** (`src/lib/api-client.ts`, 291 lines) with:
  - Auto-retry (2 retries, exponential backoff)
  - JWT Bearer auth with localStorage fallback
  - 401 → silent token refresh via `/api/v1/auth/refresh`
  - `FormData` upload support
  - 180-second request timeout

- **Zustand stores** (`src/stores/`):
  - `authStore.ts` — JWT persistence with `persist` middleware
  - `chat-store.ts` — streaming chat state
  - `platform-store.ts` — system/platform state
  - `monitoring-store.ts` — real-time health metrics
  - `system-store.ts` — system telemetry

- **SSE streaming chat** (`src/components/real-ai-chat.tsx`):
  - Parses `data:` frames with `TextDecoderStream`
  - Handles event types: `typing`, `meta`, `reasoning`, `activity`, `chunk`, `complete`, `error`, `status`
  - 12 lifecycle states (IDLE, THINKING, STREAMING, COMPLETED, etc.)
  - AbortController for stop, tool call merging, draft persistence

- **Voice interface** (`src/app/voice/page.tsx`, 606 lines):
  - WebSocket-based voice chat
  - TTS speak/listen/profile management
  - Voice presence visualization component

- **Image generation** (`src/app/image-generation/page.tsx`, 332 lines):
  - Provider selection (DALL-E, Stable Diffusion, Replicate)
  - Size, style, quality, negative prompt controls
  - Image gallery with download

- **Dashboard** (`src/app/dashboard/page.tsx`, 469 lines):
  - 12 dashboard cards with Framer Motion animations
  - Tier management panel
  - System chambers panel
  - Live system status via `/api/v1/status`

- **shadcn/ui library**: 24 components at `src/components/ui/`
- **Design tokens**: 95-line token file with CSS variable-based colors, gradients, shadows
- **Next.js App Router**: Route segments for dashboard, voice, image-generation, monitoring, etc.
- **Command palette**: cmdk integration with ⌘K / Ctrl+K trigger

### 3.2 Gap Inventory — What's Missing

#### A. Core Chat Experience

| Gap ID | Gap | Competitor Reference | Backend Endpoint Available | Impact | Effort |
|---|---|---|---|---|---|
| A1 | **No conversation history sidebar** | ChatGPT left sidebar, Claude workspaces | `/api/chat/sessions` (GET, POST, PATCH, PUT, DELETE) | High | Medium |
| A2 | **No model selection in chat** | ChatGPT model dropdown above input | `/api/v1/models` (GET), `/api/v1/ai/models` (GET) | High | Low |
| A3 | **No file/image attachment in chat** | ChatGPT paperclip, Claude paperclip | `/api/v1/multimodal/upload/image`, `/api/v1/multimodal/upload/document` | High | Medium |
| A4 | **No vision chat (image analysis)** | GPT-4V, Claude 3 | `/api/v1/ai/process` (accepts image URLs?) | Medium | Low |
| A5 | **No per-chat settings panel** | Temperature, top-p, max tokens | `/api/v1/ai/process` accepts params | Medium | Low |
| A6 | **No conversation branching/forking** | Claude "Continue from here" | `/api/chat/sessions/{id}/messages` regenerate | Medium | High |
| A7 | **No shared links** | ChatGPT share button | `/api/chat/sessions/{id}` | Medium | Medium |
| A8 | **No citation rendering** | Claude inline citations | Chat store supports `sources` | Low | Medium |
| A9 | **No Artifact panel** | ChatGPT Artifacts, Claude Artifacts | None | Low | High |

#### B. System & Monitoring

| Gap ID | Gap | Competitor Reference | Backend Endpoint Available | Impact | Effort |
|---|---|---|---|---|---|
| B1 | **No real-time metrics dashboard** | ChatGPT usage dashboard | `/api/v1/monitoring/metrics`, `/api/v1/monitoring/health-report` | Medium | Medium |
| B2 | **No system process management UI** | — | `/api/v1/system/processes`, `/api/v1/system/processes/kill` | Low | Medium |
| B3 | **No file browser** | — | `/api/v1/system/files`, `/api/v1/system/files/read` | Low | Medium |
| B4 | **No clipboard sync UI** | — | `/api/v1/system/clipboard` | Low | Low |
| B5 | **No screenshot capture UI** | — | `/api/v1/system/screenshot` | Low | Low |

#### C. Voice & Multimedia

| Gap ID | Gap | Competitor Reference | Backend Endpoint Available | Impact | Effort |
|---|---|---|---|---|---|
| C1 | **No browser-native speech recognition** | ChatGPT "Hold to Talk" | Web Speech API | High | Low |
| C2 | **No push-to-talk / VAD** | ChatGPT voice mode | Web Speech API | Medium | Medium |
| C3 | **No TTS voice selection** | ChatGPT voice picker | `/api/v1/voice/voices` returns `["default", "nova", "alloy", "echo", "fable", "onyx", "shimmer"]` | Medium | Low |
| C4 | **No voice profile management UI** | — | `/api/v1/voice/profile/create`, `/api/v1/voice/profile/list`, `/api/v1/voice/profile` | Low | Medium |

#### D. Agent & Automation

| Gap ID | Gap | Competitor Reference | Backend Endpoint Available | Impact | Effort |
|---|---|---|---|---|---|
| D1 | **No agent orchestration UI** | ChatGPT GPTs, Claude Assistants API | `/api/v1/agents` (full CRUD), `/api/v1/agents/instances`, `/api/v1/agents/tasks` | High | High |
| D2 | **No task scheduler UI** | — | `/api/v1/agents/scheduler`, `/api/v1/agents/scheduler/status` | Medium | Medium |
| D3 | **No agent execution monitor** | — | `/api/v1/agents/executions`, `/api/v1/agents/collaboration` | Medium | Medium |

#### E. Browser Integration

| Gap ID | Gap | Competitor Reference | Backend Endpoint Available | Impact | Effort |
|---|---|---|---|---|---|
| E1 | **No browser tab management UI** | — | `/api/v1/browser/sessions`, `/api/v1/browser/tabs`, `/api/v1/browser/navigate` | Medium | High |
| E2 | **No artifact extraction from browser** | — | `/api/v1/browser/extract`, `/api/v1/browser/evidence` | Low | Medium |

#### F. Infrastructure & Quality

| Gap ID | Gap | Impact | Effort |
|---|---|---|---|
| F1 | **No test suite** (Vitest + React Testing Library) | High (no test coverage) | Medium |
| F2 | **No E2E tests** (Playwright) | High | Medium |
| F3 | **No i18n** | Low | Medium |
| F4 | **No accessibility audit** | Medium | Medium |
| F5 | **No error boundaries** | Medium | Low |
| F6 | **No loading skeletons** | Low | Low |
| F7 | **No CI/CD pipeline** | Medium | Low |
| F8 | **No linting/formatting config for frontend** | Low | Low |

#### G. Secondary Frontend (`jarvis-remix/`) — Critical Bugs

| Gap ID | Issue | Fix |
|---|---|---|
| G1 | **`selectedSection` runtime crash** in `jarvis-complete-dashboard.tsx` | Add `const [selectedSection, setSelectedSection] = React.useState('quantum')` |
| G2 | **Invalid `lucide-react` imports** in `jarvis-nextgen-dashboard.tsx` (`FlagOff`, `CpuOff`, `BrainOff`, etc.) | Replace with valid icon names or remove |
| G3 | **Simulated components** (chat uses `setTimeout`, voice is fake) | Integrate with real API from `frontend/web/` |
| G4 | **Non-existent endpoint calls** (`/api/v1/components`, `/api/v1/health/status`) | Fix or remove |
| G5 | **`node_modules` not installed** | Run `npm install` |
| G6 | **Outdated** (Remix 1.7, React 18) | Consider deprecating in favor of `frontend/web/` |

#### H. Mobile Frontend — Outdated Endpoints

| Gap ID | Current | Correct Endpoint |
|---|---|---|
| H1 | `POST /auth/login` | `POST /api/v1/auth/login` |
| H2 | `POST /agents/list` | `GET /api/v1/agents` |
| H3 | `POST /ai/chat` | `POST /api/chat` or `POST /api/v1/ai/process` |
| H4 | `POST /voice/speak` | `POST /api/v1/voice/speak` |
| H5 | `POST /voice/listen` | `POST /api/v1/voice/listen` |

---

## 4. Upgrade Plan — Priority Phases

### Phase 1: Critical Bug Fixes (Priority 0 — Immediate)

#### 1.0 Fix `selectedSection` runtime crash

**File:** `frontend/jarvis-remix/components/jarvis-complete-dashboard.tsx`

```tsx
// Add this near the top of the component (before renderContent):
const [selectedSection, setSelectedSection] = React.useState('quantum');
```

Then ensure `sections.map()` uses `setSelectedSection(s.id)` in its onClick handler.

#### 1.1 Fix invalid `lucide-react` imports

**File:** `frontend/jarvis-remix/components/jarvis-nextgen-dashboard.tsx`

**Invalid icons to replace:**
| Invalid Name | Suggested Replacement |
|---|---|
| `FlagOff` | `Flag` |
| `CpuOff` | `Cpu` |
| `BrainOff` | `Brain` |
| `MemoryStickOff` | `Database` |
| `FloppyDiskOff` | `Save` |
| `UsbOff` | `Usb` |
| `MousePointerClick` | `MousePointerClick` (verify — this **does** exist in v0.468) |
| `HeadphonesIcon` | `Headphones` |
| `WifiZero` | `WifiOff` |
| `Network` | `Network` (verify — may not exist; use `Globe` or `Wifi`) |
| `CloudOff` | `CloudOff` (exists in v0.468) |
| `BrainCircuit` | `BrainCircuit` (exists in v0.468) |
| `NetworkTower` | `Network` |
| `ShieldOff` | `ShieldOff` (exists) |
| `DatabaseOff` | `Database` |
| `ActivitySquare` | `Activity` |

**Action:** Run a linter or use the script below to identify all invalid imports:

```bash
cd frontend/jarvis-remix
npm install
npx tsc --noEmit 2>&1 | grep "is not exported"
```

#### 1.2 Update mobile app endpoints

**File:** `frontend/mobile/src/App.tsx`

```diff
- API_URL = 'http://localhost:8000/api/v1'
+ API_URL = 'http://localhost:8000'

- /auth/login → /api/v1/auth/login
- /ai/chat    → /api/chat (streaming) or /api/v1/ai/process (non-streaming)
- /agents/list → /api/v1/agents
- /voice/speak → /api/v1/voice/speak
- /voice/listen → /api/v1/voice/listen
```

---

### Phase 2: Core Chat Experience Upgrade (Priority 1 — High)

#### 2.1 Conversation History Sidebar

**Goal:** Add a collapsible left sidebar showing conversation sessions, mirroring ChatGPT's interface.

**Backend endpoints:**
- `GET /api/v1/auth/sessions` — list sessions (already exists; note: this is the auth session list, **not** chat sessions)
- `GET /api/chat/sessions` — **chat sessions** (the legacy chat router has session management)
- `POST /api/chat/sessions` — create new session
- `GET /api/chat/sessions/{id}/messages` — fetch message history
- `PATCH /api/chat/sessions/{id}` — rename session
- `DELETE /api/chat/sessions/{id}` — delete session

**Implementation:**
1. Create `src/components/conversation-sidebar.tsx`
2. Create `src/features/chat/session-store.ts` (Zustand store for active session, session list)
3. Integrate with `real-ai-chat.tsx` to load and persist messages per session
4. Add a toggle button (☰) in the chat header to collapse/expand the sidebar

#### 2.2 Model Selection Dropdown

**Goal:** Add a model selector above the chat input.

**Backend endpoints:**
- `GET /api/v1/models` — model registry CRUD
- `GET /api/v1/ai/models` — live provider catalog (returns configured/unconfigured models)

**Implementation:**
1. Create `src/components/model-selector.tsx`
2. Fetch provider status via `jarvisAPI.getProviderSettings()` (already exists in `api.ts`)
3. Display available models in a dropdown (shadcn/ui `Select`)
4. Pass selected model to `/api/v1/ai/process` or `/api/chat/stream`

#### 2.3 File Attachment & Vision Chat

**Goal:** Allow users to attach files/images to chat messages.

**Backend endpoints:**
- `POST /api/v1/multimodal/upload/image` (prefix `/api/v1`)
- `POST /api/v1/multimodal/upload/document`
- `POST /api/v1/multimodal/files` (list files)
- `DELETE /api/v1/multimodal/files/{filename}`

**Implementation:**
1. Add a paperclip icon button in `real-ai-chat.tsx` input bar
2. Use `react-dropzone` (already installed) for drag-and-drop
3. Upload via `ApiClient.uploadFile()` (already supports `FormData`)
4. For images: display a thumbnail preview in the message bubble
5. For documents: display file name with icon
6. Send file URLs/paths in the chat request to `/api/chat/stream` or `/api/v1/ai/process`

#### 2.4 Per-Chat Settings Panel

**Goal:** Collapsible settings panel for temperature, top-p, max tokens, system prompt.

**Implementation:**
1. Create `src/components/chat-settings-panel.tsx`
2. Use shadcn/ui `Slider` components
3. Persist settings in Zustand chat store
4. Pass settings as request body to backend AI endpoints

#### 2.5 Conversation Branching

**Goal:** Allow users to click any assistant message and "continue from here."

**Backend endpoints:**
- `POST /api/chat/messages/{session_id}/{message_id}/regenerate` (legacy router)
- `POST /api/chat/messages/{session_id}/{message_id}/resend`

**Implementation:**
1. Add a "Fork" button (🔀 icon) to each assistant message
2. On click: create a new session from that message
3. Navigate to the new session with the message as the starting point

---

### Phase 3: System & Monitoring Upgrade (Priority 2 — Medium)

#### 3.1 Real-Time Metrics Dashboard

**Goal:** Live charts showing CPU, memory, disk, API response times, agent activity.

**Backend endpoints:**
- `GET /api/v1/monitoring/metrics` — system + application metrics
- `GET /api/v1/monitoring/health-report` — health report with check results
- `GET /api/v1/monitoring/diagnostics` — system diagnostics
- `GET /api/v1/monitoring/optimization` — optimization suggestions
- WebSocket: `/ws/monitoring` — real-time metrics stream

**Implementation:**
1. Create `src/app/dashboard/monitoring/page.tsx` (or update existing)
2. Use `recharts` (already installed) for charts: `LineChart`, `BarChart`, `GaugeComponent`
3. Subscribe to `/ws/monitoring` for live updates
4. Show health rate percentage, average API response time, recent failures/recoveries

#### 3.2 System Process Management UI

**Backend endpoints:**
- `GET /api/v1/system/processes` — list running processes
- `POST /api/v1/system/processes/kill` — kill a process

**Implementation:**
1. Table of processes with PID, name, CPU%, memory%, status
2. Kill button with confirmation dialog (shadcn/ui `AlertDialog`)

#### 3.3 File Browser

**Backend endpoints:**
- `GET /api/v1/system/files` — list files
- `POST /api/v1/system/files/read` — read file contents

**Implementation:**
1. File tree navigation
2. Read-only file viewer with syntax highlighting (use `react-syntax-highlighter`)

#### 3.4 Screenshot & Clipboard

**Backend endpoints:**
- `GET /api/v1/system/screenshot` — capture screenshot
- `GET /api/v1/system/clipboard` / `POST /api/v1/system/clipboard`

**Implementation:**
1. Screenshot capture button → display in modal
2. Clipboard viewer/sync panel

---

### Phase 4: Voice & Multimedia Enhancement (Priority 2 — Medium)

#### 4.1 Browser-Native Speech Recognition

**Goal:** Replace or supplement the WebSocket-based voice with browser-native Web Speech API for real-time transcription.

**Implementation:**
1. Use `window.SpeechRecognition` or `webkitSpeechRecognition`
2. Integrate with `handleManualListen` in voice page for fallback
3. Add a "Press & Hold to Talk" button with push-to-talk UX
4. Show real-time transcription as the user speaks

#### 4.2 Push-to-Talk with Voice Activity Detection (VAD)

**Goal:** Continuous listening on push-to-talk, ending when silence is detected.

**Implementation:**
1. Use Web Audio API to detect audio levels
2. Auto-stop listening when amplitude drops below threshold for 1.5s

#### 4.3 TTS Voice Selection

**Backend endpoint:** `GET /api/v1/voice/voices` returns `["default", "nova", "alloy", "echo", "fable", "onyx", "shimmer"]`

**Implementation:**
1. Add a voice selector dropdown in the voice control panel
2. Pass voice name to `POST /api/v1/voice/speak`

#### 4.4 Voice Profile Management UI

**Backend endpoints:** `POST /api/v1/voice/profile/create`, `GET /api/v1/voice/profile/list`, `GET /api/v1/voice/profile`

**Implementation:**
1. Create a "Profiles" tab in the voice page
2. List, create, and select voice profiles
3. Store active profile in Zustand voice store

---

### Phase 5: Agent & Browser UI (Priority 3 — Medium)

#### 5.1 Agent Orchestration Dashboard

**Backend endpoints:**
- `GET /api/v1/agents` — agent definitions
- `POST /api/v1/agents` — create agent
- `GET /api/v1/agents/instances` — active instances
- `POST /api/v1/agents/tasks` — task management
- `GET /api/v1/agents/scheduler/status` — scheduler status
- `GET /api/v1/agents/executions` — execution history
- `POST /api/v1/agents/collaboration` — multi-agent collaboration

**Implementation:**
1. Agent list card with status, capabilities, active tasks
2. Task creation form
3. Execution monitor with log viewer
4. Scheduler control toggle

#### 5.2 Embedded Browser UI

**Backend endpoints:**
- `POST /api/v1/browser/sessions` — create browser session
- `GET /api/v1/browser/sessions/{id}` — get session
- `POST /api/v1/browser/tabs` — create tab
- `POST /api/v1/browser/navigate` — navigate URL
- `POST /api/v1/browser/extract` — extract page content
- `GET /api/v1/browser/evidence` — captured evidence

**Implementation:**
1. Create `src/components/embedded-browser/EmbeddedBrowser.tsx` (check if already exists)
2. Render browser window via iframe or canvas
3. Tab management UI
4. URL bar with navigation controls
5. Extract/evidence capture buttons

---

### Phase 6: Code Interpreter / Sandbox Integration (Priority 3 — Medium)

**Goal:** Integrate the backend sandbox infrastructure into the chat for code execution.

**Backend:** `jarvis_backend/sandbox.py` (554 lines) — `_BubblewrapSandbox`, `_DockerSandbox`, `_SubprocessSandbox`, `SandboxManager.execute("science", "print(42)")` → verified working.

**Implementation:**
1. Add a "Run Code" toggle in chat settings (like ChatGPT's Code Interpreter)
2. When enabled, detected code blocks get a "Run" button
3. On click: send code to a backend sandbox endpoint (may need to add a new endpoint or use existing capability routes)
4. Display output below the code block
5. Support Python, JavaScript (Node), and shell execution

---

### Phase 7: Testing Infrastructure (Priority 3 — Medium)

#### 7.1 Unit Testing — Vitest + React Testing Library

**Add to `frontend/web/package.json`:**
```json
{
  "devDependencies": {
    "vitest": "^3.0.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.0.0",
    "@testing-library/user-event": "^14.0.0",
    "happy-dom": "^0.24.0",
    "vitest-css-collector": "^0.1.0"
  },
  "scripts": {
    "test": "vitest",
    "test:ui": "vitest --ui",
    "test:run": "vitest run"
  }
}
```

**Create `src/vitest.config.ts`:**
```ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'happy-dom',
    setupFiles: ['./src/lib/test-setup.ts'],
    css: true,
  },
});
```

#### 7.2 E2E Testing — Playwright

```json
{
  "devDependencies": {
    "@playwright/test": "^1.49.0",
    "playwright": "^1.49.0"
  },
  "scripts": {
    "test:e2e": "playwright test"
  }
}
```

**Create `e2e/smoke.spec.ts`** — test login, chat message, model switch, file upload.

---

### Phase 8: Secondary Frontend (`jarvis-remix/`) Migration Plan

**Recommendation:** The `jarvis-remix/` frontend is a secondary, older Remix 1.7 app with entirely simulated components and multiple runtime crashes. Rather than invest in fixing its 160+ invalid icon imports and simulated logic, the recommended path is:

**Option A (Recommended): Deprecate** — Remove `jarvis-remix/` from active development. All its component concepts (holographic UI, next-gen dashboard, voice interface) should be ported to the `frontend/web/` React 19 codebase.

**Option B (If resource allows): Migrate** — Upgrade to Remix 2.x, fix all bugs, then integrate with the real API from `frontend/web/`.

---

### Phase 9: Mobile App Endpoint Fixes (Priority 1 — High)

**File:** `frontend/mobile/src/App.tsx`

| Current | Correct | Component |
|---|---|---|
| `API_URL = 'http://localhost:8000/api/v1'` | `API_URL = 'http://localhost:8000'` | Top of file |
| `POST /auth/login` | `POST /api/v1/auth/login` | LoginScreen |
| `POST /ai/chat` | `POST /api/v1/ai/process` | ChatScreen |
| `POST /agents/list` | `GET /api/v1/agents` | AgentsScreen |
| `POST /voice/speak` | `POST /api/v1/voice/speak` | VoiceScreen |
| `POST /voice/listen` | `POST /api/v1/voice/listen` | VoiceScreen |

**Additional fixes:**
- Add token refresh handling (401 → `/api/v1/auth/refresh`)
- Add proper error handling with `Alert` dialogs instead of silent failures
- Add `FlatList` for chat message rendering (currently uses `ScrollView` which doesn't virtualize)
- Add `react-native-image-picker` for image attachment in ChatScreen

---

### Phase 10: TypeScript & Schema Hardening

#### 10.1 Generate TypeScript types from backend OpenAPI schema

The backend has `/openapi.json` (verified live). Use `orval` or `openapi-typescript`:

```bash
cd frontend/web
npx openapi-typescript http://127.0.0.1:8000/openapi.json --output src/lib/api-types.ts
```

This generates fully-typed response/request types for every backend endpoint.

#### 10.2 Replace `any` types in chat store

**File:** `src/stores/chat-store.ts` — the `tool_calls?: any[]` and `tool_results?: any[]` fields in `ChatMessage` should use proper interfaces.

#### 10.3 Type-safe API response validation

Add runtime validation (e.g., `zod`) for API responses to catch backend contract changes:

```ts
import { z } from 'zod';

const LoginResponse = z.object({
  access_token: z.string(),
  token_type: z.string(),
  user: z.object({
    id: z.string(),
    email: z.string(),
    username: z.string(),
  }),
  refresh_token: z.string().optional(),
});
```

---

## 5. Implementation Roadmap

| Phase | Tasks | Estimate | Prerequisites |
|---|---|---|---|
| **Phase 1** (Critical Fixes) | 1. Fix `selectedSection` bug (G1) | 15 min | None | ✅ Done
| | 2. Fix invalid lucide imports (G2) | 30 min | None | ✅ Done
| | 3. Fix mobile endpoints (H1-H5) | 1 hour | None | ✅ Done
| **Phase 2** (Chat UX) | 4. Conversation sidebar (A1) | 4 hrs | Auth working | ✅ Done
| | 5. Model selector (A2) | 1 hr | `/api/v1/models` | ✅ Done
| | 6. File attachment (A3) | 3 hrs | `/api/v1/multimodal/upload` | ✅ Done
| | 7. Per-chat settings (A5) | 1 hr | Chat component | ✅ Done
| | 8. Conversation branching (A6) | 3 hrs | Session API | ✅ Done
| **Phase 3** (Monitoring) | 9. Metrics dashboard (B1) | 3 hrs | WebSocket `/ws/monitoring` | ✅ Done
| | 10. Process mgmt UI (B2) | 2 hrs | `/api/v1/system/processes` | ✅ Done
| | 11. File browser (B3) | 2 hrs | `/api/v1/system/files` | ✅ Done — `dashboard/files/page.tsx`
| **Phase 4** (Voice) | 12. Speech recognition (C1) | 2 hrs | Web Speech API | ✅ Done
| | 13. TTS voice selector (C3) | 1 hr | `/api/v1/voice/voices` | ✅ Done — voice page tabs + Select dropdown
| | 14. Voice profile UI (C4) | 2 hrs | `/api/v1/voice/profile/*` | ✅ Done — Profiles tab with create/list/select
| **Phase 5** (Agents/Browser) | 15. Agent dashboard (D1) | 6 hrs | `/api/v1/agents/*` | ✅ Done — tabs, collab graph, auto-refresh
| | 16. Agent collaboration (D3) | 3 hrs | `/api/v1/agents/collaboration/*` | ✅ Done
| **Phase 6** | 17. Code interpreter (sandbox) | 4 hrs | `jarvis_backend/sandbox.py` | ⏳ Backend done, frontend integration pending
| **Phase 7** | 18. Vitest + RTL setup (F1) | 2 hrs | None | ✅ Scaffolded
| | 19. Playwright E2E (F2) | 2 hrs | None | ✅ Scaffolded
| | 20. TypeScript types (10.1) | 1 hr | `/openapi.json` | ⏳ Pending

---

## 6. Backend Integration Reference

### 6.1 Verified Working Endpoints (Port 8000)

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/auth/login` | Login (verified: ndichiv@gmail.com / videlis@254 → 18/18 tests pass) |
| `POST` | `/api/v1/auth/refresh` | Token refresh |
| `POST` | `/api/v1/auth/logout` | Logout |
| `GET` | `/api/v1/auth/me` | User profile |
| `GET` | `/api/v1/auth/sessions` | Session list |
| `GET` | `/api/v1/status` | Platform status |
| `GET` | `/api/status` | Legacy status |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/v1/identity` | Identity info |
| `POST` | `/api/v1/ai/process` | Chat completion |
| `GET` | `/api/v1/ai/status` | Silverwing/Brain health |
| `GET` | `/api/v1/ai/models` | Provider catalog |
| `POST` | `/api/v1/ai/tasks` | AI task submission |
| `POST` | `/api/chat` | Legacy chat (authenticated) |
| `POST` | `/api/chat/stream` | SSE streaming chat |
| `GET` | `/api/chat/sessions` | Session management |
| `POST` | `/api/v1/voice/speak` | Text-to-speech |
| `POST` | `/api/v1/voice/listen` | Speech-to-text |
| `POST` | `/api/v1/voice/transcribe` | Audio transcription |
| `GET` | `/api/v1/voice/voices` | Available voices |
| `GET` | `/api/v1/voice/status` | Voice engine status |
| `POST` | `/api/v1/image/generate` | Image generation |
| `POST` | `/api/v1/multimodal/upload/image` | Image upload |
| `POST` | `/api/v1/multimodal/upload/document` | Document upload |
| `GET` | `/api/v1/system/processes` | Running processes |
| `POST` | `/api/v1/system/processes/kill` | Kill process |
| `GET` | `/api/v1/monitoring/metrics` | System metrics |
| `GET` | `/api/v1/monitoring/health-report` | Health report |
| `GET` | `/api/v1/agents` | Agent definitions |
| `POST` | `/api/v1/agents` | Create agent |
| `POST` | `/api/v1/agents/tasks` | Create task |
| `GET` | `/api/v1/agents/scheduler/status` | Scheduler status |
| `POST` | `/api/v1/browser/sessions` | Create browser session |
| `POST` | `/api/v1/browser/navigate` | Navigate to URL |
| `GET` | `/api/v1/browser/evidence` | Captured evidence |
| `POST` | `/api/v1/memory/store` | Store memory |
| `GET` | `/api/v1/knowledge/search` | Knowledge search |
| `POST` | `/mcp` | MCP server (tools) |
| `POST` | `/a2a` | A2A protocol |
| `GET` | `/ws/chat` | WebSocket chat |
| `GET` | `/ws/monitoring` | WebSocket metrics |
| `GET` | `/silverwing/api/...` | Silverwing backend (77 routes) |

### 6.2 WebSocket Endpoints

| URL | Purpose |
|---|---|
| `ws://localhost:8000/ws/chat` | Real-time chat events |
| `ws://localhost:8000/ws/health` | Health status streaming |
| `ws://localhost:8000/ws/voice` | Voice session events |
| `ws://localhost:8000/ws/agents` | Agent lifecycle events |
| `ws://localhost:8000/ws/monitoring` | System metrics stream |
| `ws://localhost:8000/ws/stark` | Stark engine events |

### 6.3 Next.js Rewrite Configuration

The current `next.config.mjs` rewrites `/api/v1/*` → backend and `/api/health` → backend. To expose more endpoints through the Next.js proxy (avoiding CORS issues), add rewrites for:

```js
// next.config.mjs — add these rewrites:
{
  source: '/api/chat/stream',
  destination: `${backendOrigin}/api/chat/stream`,
},
{
  source: '/api/chat/sessions/:path*',
  destination: `${backendOrigin}/api/chat/sessions/:path*`,
},
{
  source: '/api/v1/voice/:path*',
  destination: `${backendOrigin}/api/v1/voice/:path*`,
},
{
  source: '/api/v1/image/:path*',
  destination: `${backendOrigin}/api/v1/image/:path*`,
},
{
  source: '/api/v1/multimodal/:path*',
  destination: `${backendOrigin}/api/v1/multimodal/:path*`,
},
{
  source: '/api/v1/agents/:path*',
  destination: `${backendOrigin}/api/v1/agents/:path*`,
},
{
  source: '/api/v1/browser/:path*',
  destination: `${backendOrigin}/api/v1/browser/:path*`,
},
{
  source: '/api/v1/monitoring/:path*',
  destination: `${backendOrigin}/api/v1/monitoring/:path*`,
},
{
  source: '/api/v1/system/:path*',
  destination: `${backendOrigin}/api/v1/system/:path*`,
},
{
  source: '/api/v1/memory/:path*',
  destination: `${backendOrigin}/api/v1/memory/:path*`,
},
{
  source: '/api/v1/knowledge/:path*',
  destination: `${backendOrigin}/api/v1/knowledge/:path*`,
},
```

---

## 7. Technology Stack Recommendations

### 7.1 Core Upgrades (Additive, preserving existing stack)

| Library | Version | Purpose | Replaces |
|---|---|---|---|
| `ai` | `^3.3.0` | Vercel AI SDK — `useChat`, `useCompletion`, `useSpeech` hooks | Custom SSE parsing in `real-ai-chat.tsx` |
| `@ai-sdk/openai` | `^1.0.0` | OpenAI provider | — |
| `@ai-sdk/anthropic` | `^1.0.0` | Anthropic provider | — |
| `@ai-sdk/google` | `^2.0.0` | Google Gemini provider | — |
| `three` | `^0.170.0` | 3D rendering engine | Raw canvas in `holographic-ui.tsx` |
| `@react-three/fiber` | `^9.0.0` | React renderer for Three.js | — |
| `@react-three/drei` | `^10.0.0` | Useful R3F helpers | — |
| `zod` | `^3.23.0` | Runtime type validation | `any` types in stores |
| `@tanstack/react-query` | `^5.0.0` | Data fetching & caching | Manual `useEffect` + fetch |
| `@radix-ui/react-dialog` | `^1.1.0` | Headless dialog primitive | Custom modal implementations |

### 7.2 Testing

| Library | Version | Purpose |
|---|---|---|
| `vitest` | `^3.0.0` | Unit testing |
| `@testing-library/react` | `^16.0.0` | Component testing |
| `@testing-library/jest-dom` | `^6.0.0` | DOM matchers |
| `@testing-library/user-event` | `^14.0.0` | User interaction simulation |
| `happy-dom` | `^0.24.0` | DOM environment |
| `@playwright/test` | `^1.49.0` | E2E testing |

### 7.3 3D / Holographic UI

**Current state:** `holographic-ui.tsx` (1325 lines in `jarvis-remix`) uses raw HTML Canvas with no backend integration. The `frontend/web/` version uses CSS glassmorphism and Framer Motion.

**Recommendation:** Integrate `@react-three/fiber` (R3F) to create a real 3D holographic interface that visualizes:

1. **Neural network visualization** — 3D node graph of agents and their connections (backend: `/api/v1/agents`, `/api/v1/agents/collaboration`)
2. **System telemetry as 3D graph** — CPU/memory/disk usage as floating 3D bars (backend: `/api/v1/monitoring/metrics`)
3. **Holographic display effect** — Use `three/examples/jsm/controls/OrbitControls` for 3D navigation with a holographic shader overlay

Create `src/components/holographic-ui.tsx` using:

```tsx
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Stats, Environment } from '@react-three/drei';
import { useQuery } from '@tanstack/react-query';

function HolographicScene() {
  const { data: agents } = useQuery({
    queryKey: ['agents'],
    queryFn: () => jarvisAPI.getAgents(),
  });

  return (
    <Canvas camera={{ position: [0, 0, 20] }}>
      <Environment preset="night" />
      <ambientLight intensity={0.5} />
      <pointLight position={[10, 10, 10]} />
      {/* Render 3D nodes for each agent */}
      {agents?.map(agent => (
        <AgentNode key={agent.id} agent={agent} />
      ))}
      <OrbitControls />
      <Stats />
    </Canvas>
  );
}
```

---

## 8. Detailed Component Mapping

### 8.1 New Components to Create

| Component | Path | Purpose |
|---|---|---|
| `ConversationSidebar` | `src/components/conversation-sidebar.tsx` | Session list, new chat, rename/delete |
| `ModelSelector` | `src/components/model-selector.tsx` | Dropdown for AI model selection |
| `ChatInput` (enhanced) | `src/components/chat-input.tsx` | Input bar with file attach, model selector, settings |
| `MessageWithCitations` | `src/components/message-with-citations.tsx` | Renders chat messages with inline citations |
| `FileAttachmentPreview` | `src/components/file-attachment-preview.tsx` | Thumbnail/preview for attached files |
| `ChatSettingsPanel` | `src/components/chat-settings-panel.tsx` | Temperature, top-p, max tokens, system prompt |
| `MetricsDashboard` | `src/app/dashboard/monitoring/page.tsx` | Live charts with recharts |
| `ProcessManager` | `src/app/dashboard/system/processes/page.tsx` | Process table with kill button |
| `FileBrowser` | `src/app/dashboard/system/files/page.tsx` | File tree and viewer |
| `AgentDashboard` | `src/app/dashboard/agents/page.tsx` | Agent orchestration UI |
| `BrowserSession` | `src/components/embedded-browser/BrowserSession.tsx` | Browser tab management |
| `HolographicUI` | `src/components/holographic-ui.tsx` | R3F-based 3D visualization |
| `CodeInterpreter` | `src/components/code-interpreter.tsx` | Sandbox execution panel |

### 8.2 Components to Upgrade

| Component | Current State | Upgrade Target |
|---|---|---|
| `real-ai-chat.tsx` | Custom SSE parsing, no file attach, single model | Integrate Vercel AI SDK, add file attach UI, model selector, per-chat settings |
| `dashboard-shell.tsx` | Basic sidebar with static nav items | Add conversation list, dynamic nav from backend capabilities |
| `voice/page.tsx` | WebSocket voice, no browser-native SpeechRecognition | Add Web Speech API, TTS voice selector, profiles tab |
| `image-generation/page.tsx` | Standalone generator | Integrate into chat as a tool, add gallery view |
| `design-tokens.ts` | Static tokens | Dynamic theme with CSS variables + runtime switching |

---

## 9. Testing Strategy

### 9.1 Unit Tests (Vitest + RTL)

**Coverage targets:**
- `ApiClient` class: token resolution, retry logic, 401 refresh, FormData upload
- `authStore.ts`: login, logout, token persistence
- `chat-store.ts`: message add/remove, streaming state transitions
- `model-selector.tsx`: renders available models, calls onChange
- `conversation-sidebar.tsx`: fetches sessions, creates new session

**Directory structure:**
```
src/
  __tests__/
    lib/
      api-client.test.ts
    stores/
      authStore.test.ts
      chat-store.test.ts
    components/
      model-selector.test.tsx
      conversation-sidebar.test.tsx
    features/
      chat/
        chat-store.test.ts
```

### 9.2 E2E Tests (Playwright)

**Test scenarios:**
1. Login flow: navigate to `/login`, enter credentials, assert redirect to `/dashboard`
2. Chat flow: send message, verify SSE stream renders, verify stop button works
3. Navigation: click sidebar items, verify route changes
4. Voice: open voice page, verify status badges render
5. Image generation: open image page, enter prompt, verify generation flow

---

## 10. Accessibility & Internationalization

### 10.1 Accessibility Audit

**Checklist:**
- All interactive elements have `aria-label` or visible text
- Keyboard navigation: Tab order, Enter/Space activation
- Color contrast meets WCAG 2.1 AA (use `axe-core` for automated testing)
- Focus indicators visible on all interactive elements
- Semantic HTML: `<main>`, `<nav>`, `<section>`, `<header>`, `<aside>`
- Form labels associated with inputs via `htmlFor`
- Error messages announced via `aria-live`
- Reduced motion preference respected (use `useReducedMotion` from Framer Motion)
- Dark mode toggle has proper labeling and state

### 10.2 Internationalization

**Current:** `src/lib/i18n.ts` exists but implementation is incomplete.

**Plan:**
1. Install `next-intl` (Next.js 16 compatible) or `react-i18next`
2. Extract all hardcoded strings to translation files
3. Use `<useTranslations>` for component strings
4. Create locale files: `en.json`, `es.json`, `fr.json`
5. Add language selector in settings

---

## 11. Deployment & CI/CD

### 11.1 GitHub Actions Workflow

`.github/workflows/frontend.yml`:

```yaml
name: Frontend CI
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: cd frontend/web && npm ci
      - run: npx tsc --noEmit

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: cd frontend/web && npm ci
      - run: npx eslint src/ --max-warnings=0

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: cd frontend/web && npm ci
      - run: npm run test:run

  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: cd frontend/web && npm ci
      - run: npm run build
```

### 11.2 ESLint Configuration

Ensure `frontend/web/eslint.config.js` enforces:
- `@typescript-eslint/no-explicit-any` — warn
- `react-hooks/rules-of-hooks` — error
- `react-hooks/exhaustive-deps` — warn
- Import order sorting

---

## 12. File Inventory

### 12.1 Key Frontend Files (Production — `frontend/web/`)

| File | Lines | Purpose |
|---|---|---|
| `src/lib/api-client.ts` | 291 | Full `ApiClient` class with auth, retry, refresh |
| `src/lib/api.ts` | 1430 | `JarvisAPI` class + TypeScript interfaces |
| `src/stores/authStore.ts` | 92 | Zustand auth store with persistence |
| `src/stores/chat-store.ts` | ~490 | Chat store with SSE streaming |
| `src/components/real-ai-chat.tsx` | 1738 | Main chat component |
| `src/components/dashboard-shell.tsx` | 386 | App shell with sidebar + command palette |
| `src/app/voice/page.tsx` | 606 | Voice control panel |
| `src/app/image-generation/page.tsx` | 332 | Image generation UI |
| `src/app/dashboard/page.tsx` | 469 | Dashboard overview with 12 cards |
| `src/lib/design-tokens.ts` | 95 | Design system tokens |
| `src/features/voice/api.ts` | 38 | Voice API client |
| `next.config.mjs` | 41 | Rewrites, strict TS, standalone output |
| `tailwind.config.js` | 82 | Tailwind config with glassmorphism |
| `tsconfig.json` | 42 | Strict TS with `@/*` alias |
| `package.json` | ~70 | 47 deps + 10 devDeps |

### 12.2 Key Backend Files

| File | Lines | Purpose |
|---|---|---|
| `jarvis_backend/main.py` | ~300+ | FastAPI app, mounts all routers, A2A, MCP, WebSocket |
| `jarvis_backend/core.py` | ~500+ | Core business logic |
| `jarvis_backend/routers/auth.py` | ~500+ | Auth: login, register, refresh, logout, sessions, API keys |
| `jarvis_backend/routers/identity.py` | ~300+ | OIDC, Google OAuth |
| `jarvis_backend/routers/ai.py` | 777 | AI processing, models, tasks, conversations |
| `jarvis_backend/routers/legacy.py` | 475 | Legacy chat, sessions, notes, reminders |
| `jarvis_backend/routers/voice.py` | 130 | TTS, ASR, voice profiles |
| `jarvis_backend/routers/multimodal.py` | ~200 | Image/document upload |
| `jarvis_backend/routers/media.py` | ~100 | Image/video generation |
| `jarvis_backend/routers/system.py` | ~290 | System telemetry, processes, files |
| `jarvis_backend/routers/agents.py` | ~500+ | Agent orchestration, tasks, scheduler |
| `jarvis_backend/routers/browser.py` | ~500+ | Embedded browser infrastructure |
| `jarvis_backend/sandbox.py` | 554 | Sandbox execution: Bubblewrap, Docker, Subprocess |
| `jarvis_backend/mcp_server.py` | 428 | MCP server wrapping JARVIS tools |
| `silverwing-backend/main.py` | 3458 | Silverwing backend (77 routes) |

---

## 13. Constraints & Success Criteria

### 13.1 Hard Constraints

| Constraint | Status |
|---|---|
| Preserve Next.js 16 / React 19 / TypeScript / Tailwind / shadcn/ui / Zustand | ✅ Must not change |
| `tsc --noEmit` must pass after all changes | ✅ Required |
| Backend login (ndichiv@gmail.com / videlis@254) verified working — DO NOT retry | ✅ 18/18 tests pass |
| All new TS code must compile without errors | ✅ Required |
| Changes must be additive (no destructive rewrites) | ✅ Required |

### 13.2 Success Criteria

| Metric | Target | Measurement |
|---|---|---|
| TypeScript compilation | 0 errors | `npx tsc --noEmit` |
| ESLint | 0 errors | `npx eslint src/ --max-warnings=0` |
| Unit test coverage | ≥ 50% of components | `npm run test:run -- --coverage` |
| E2E smoke tests | All pass | `npm run test:e2e` |
| Critical bugs fixed | All fixed | `selectedSection` crash, invalid imports, mobile endpoints |
| New chat features | Working | ChatGPT-style conversation sidebar, file upload, model selector |

---

## 14. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Large file `real-ai-chat.tsx` (1738 lines) is hard to modify | Medium | High | Refactor incrementally; add file attachment as a wrapper component first |
| `jarvis-remix/` dependencies may fail to install | High | Low | Focus on `frontend/web/` instead; deprecate `jarvis-remix/` |
| Backend endpoints may return unexpected schemas | Medium | Medium | Use `zod` validation on all API responses |
| 3D R3F integration may cause performance issues | Medium | Medium | Use `drei` LOD, frustum culling, `useMemo` for geometry |
| WebSocket reconnection logic may be flaky | Medium | High | Implement exponential backoff reconnection in `websocket.ts` |
| Mobile app has React Native version constraints | Low | Medium | Check Expo SDK compatibility before upgrading |

---

## 15. Appendix

### 15.1 Directory Structure (Production Frontend)

```
frontend/web/
├── package.json          # Next.js 16, React 19, TS 5.4, 47 deps
├── tsconfig.json         # Strict, @/* alias → ./src/*
├── tailwind.config.js    # Glassmorphism, custom keyframes
├── next.config.mjs       # Rewrites /api/v1/* → backend, standalone
├── src/
│   ├── app/             # Next.js App Router routes
│   │   ├── dashboard/   # 12 route segments (admin, agents, cognitive, etc.)
│   │   ├── login/
│   │   ├── register/
│   │   ├── voice/
│   │   ├── image-generation/
│   │   ├── monitoring/
│   │   ├── desktop/
│   │   ├── holographic/
│   │   ├── omega/
│   │   └── stark-control/
│   ├── components/        # ~150 component files
│   │   ├── ui/          # 24 shadcn/ui components
│   │   ├── voice/        # 4 voice components
│   │   ├── widgets/      # 6 widget components
│   │   ├── shells/       # 4 shell components
│   │   ├── dashboard/    # 4 sub-dashboard components
│   │   ├── control-center/ # 5 tab components
│   │   ├── embedded-browser/
│   │   ├── advanced-*.tsx
│   │   ├── jarvis-*.tsx
│   │   ├── real-ai-chat.tsx (1738 lines)
│   │   ├── dashboard-shell.tsx (386 lines)
│   │   ├── holographic-ui.tsx
│   │   └── neural-activity-map.tsx
│   ├── features/         # 18 feature folders (each: api.ts, store.ts, types.ts)
│   │   ├── agents/
│   │   ├── auth/
│   │   ├── automation/
│   │   ├── browser/
│   │   ├── chat/
│   │   ├── memory/
│   │   ├── monitoring/
│   │   ├── search/
│   │   ├── system/
│   │   └── voice/
│   ├── stores/           # Zustand stores
│   │   ├── authStore.ts
│   │   ├── chat-store.ts
│   │   ├── platform-store.ts
│   │   ├── monitoring-store.ts
│   │   ├── system-store.ts
│   │   └── (more)
│   ├── lib/              # Utility libraries
│   │   ├── api-client.ts (291 lines)
│   │   ├── api.ts (1430 lines)
│   │   ├── websocket.ts
│   │   ├── websocket-client.ts
│   │   ├── design-system.ts
│   │   ├── design-tokens.ts (95 lines)
│   │   ├── i18n.ts
│   │   ├── offline-first-system.ts
│   │   ├── autonomous-dashboard.ts
│   │   └── (more)
│   └── types/            # Global TypeScript types
│       └── index.ts
├── public/
└── node_modules/         # ✅ Installed
```

### 15.2 Environment Configuration

**File:** `frontend/web/.env.local`

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=
NEXT_PUBLIC_SOCKET_URL=http://localhost:8000
```

**Backend `.env` (verified working):**
```env
JARVIS_ADMIN_EMAIL=ndichiv@gmail.com
JARVIS_ADMIN_PASSWORD=videlis@254
# (redacted — full .env verified in place)
```

### 15.3 Running the System

```bash
# Start everything (from F:\AI\Jarvis-super-intelligence-):
#   - Backend: uvicorn on :8000
#   - Silverwing runtime: :8010
#   - Frontend: npm run dev on :3000
powershell -File start_all.ps1

# Run auth tests:
python -m pytest tests/test_auth.py -v  # → 18 passed

# Frontend dev:
cd frontend/web && npm run dev

# Frontend typecheck:
cd frontend/web && npx tsc --noEmit

# Run all phase verification:
cd F:\AI\Jarvis-super-intelligence- && python _verify_phases.py
```

---

## 16. Conclusion

The JARVIS production frontend (`frontend/web/`) is already a sophisticated Next.js 16 application with real API integration, streaming chat, voice controls, image generation, and a comprehensive component library. The primary gaps versus leading AI platforms are:

1. **Polish & interaction design** — Missing conversation sidebar, file attachments, model selector, per-chat settings, conversation branching
2. **3D visualization** — Holographic UI uses raw Canvas; needs R3F for proper 3D rendering
3. **Code interpreter** — Backend sandbox exists (`sandbox.py`) but no frontend integration
4. **Test coverage** — No unit or E2E test infrastructure
5. **Secondary frontend** — `jarvis-remix/` is broken and should be deprecated or migrated

The upgrade plan is organized into 10 phases, from critical bug fixes (Phase 1) through advanced features (Phase 6), testing infrastructure (Phase 7), and the secondary frontend/mobile remediation. Each phase references specific backend endpoints, component files, and competitor features, enabling incremental, verifiable implementation.
