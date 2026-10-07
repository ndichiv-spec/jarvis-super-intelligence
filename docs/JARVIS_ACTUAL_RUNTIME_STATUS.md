# JARVIS Runtime Status

## Verification status

Last checked: 2026-10-07. The local Next.js application and FastAPI backend
responded during this implementation session, and `/voice` rendered the shared
chat interface. The backend health endpoint returned `ok`, and
`/silverwing/health` reported the Silverwing app as mounted. The voice status
endpoint reported ASR and TTS as `NOT_CONFIGURED`; the AI status endpoint
reported zero configured providers and `degraded`. No provider inference,
image generation, live database persistence, or production deployment was
verified. Provider execution and production readiness are therefore **not
available/verified**, despite the local API being reachable.

## Active application

- Backend entry point: `jarvis_backend.main:app` (FastAPI).
- Browser client: `frontend/web` (Next.js).
- Canonical conversation orchestration: `jarvis_backend.chat_service.ChatService`
  and `ProviderGateway`.
- Production deployment: immutable backend/frontend images, PostgreSQL,
  migration job, and separate worker/beat services as defined in
  `deployment/production/docker-compose.prod.yml`.

For local development, from the application directory:

```powershell
python -m uvicorn jarvis_backend.main:app --host 127.0.0.1 --port 8000
```

From `frontend/web`, use the existing `npm run dev`, `npm run typecheck`,
`npm run test`, and `npm run build` scripts. Production image and Compose
verification require Docker and are not covered by this local command.

## Authentication and conversation behavior

Browser authentication uses server-managed `HttpOnly`, `SameSite=Lax` cookies;
the authentication stores do not persist access or refresh tokens in browser
storage. Shared API clients and audited direct calls send cookies, and the
refresh endpoint rotates them server-side. A repository-wide inventory of every
legacy direct `fetch` call is still required before claiming complete cookie
coverage.

`POST /api/chat` and `POST /api/chat/stream` require authentication and route
through `ChatService`. Session ownership is checked server-side. Provider
streaming is forwarded as received; when a provider cannot stream, the backend
uses its buffered result rather than synthesizing chunks. A client Stop action
aborts the HTTP stream; `ChatService` persists an interrupted lifecycle state
when the stream is cancelled. The browser requires an explicit terminal frame;
if the transport ends early, the partial assistant turn is marked interrupted
with the backend error details instead of appearing as a completed response.

The backend stores conversation messages and provider/model attribution in its
configured persistence layer. The actual database selected and the persistence
of a live conversation must be checked in the running deployment.

## Capability truth

| Capability | Current implementation state |
|---|---|
| Text chat | Routed through the existing chat service and provider gateway; live provider execution was not verified. |
| Streaming | Provider stream is forwarded when supported; frontend Stop aborts the request. Live end-to-end streaming was not verified. |
| Knowledge/memory | Reads used by the cognitive search and chat context now filter by owner; shared unowned knowledge must explicitly be public. |
| Image generation | Replicate, Stability, and OpenAI handlers validate provider image bytes before persisting owner-scoped files and artifact metadata with authenticated retrieval. When attached to a user-owned chat session, the prompt and generated artifacts are added as a conversation turn and displayed in history; standalone generation remains available without a chat session. Provider credentials and live generation were not verified. |
| Voice | Chat composer uses browser SpeechRecognition when supported; recognized text enters the same authenticated ChatService streaming/history path. Completed responses can use browser SpeechSynthesis on demand. Browser support and device permissions are runtime-dependent. Authenticated audio uploads delegate to VoiceCapability and require a configured OpenAI Whisper or local Whisper provider; these providers were not live-tested. The legacy server voice WebSocket now reports unavailable instead of acknowledging fabricated transcripts. |
| Video | Decode, frame extraction, and analysis are not implemented; the legacy endpoints now return `CAPABILITY_NOT_CONFIGURED` rather than reporting success. |
| Agent tasks | Manual runs use the chat service and are user-scoped. Dynamic scheduling is not connected; scheduled task registration and scheduler control are unavailable. |
| MCP | Optional HTTP mount authenticates each request with the JARVIS session cookie or bearer credential and derives tool grants from server-side RBAC. Stdio clients have no authenticated principal and receive no tool permissions; tool arguments cannot claim a JARVIS identity. |
| Legacy embedded browser | In-memory simulation endpoints are disabled and return `CAPABILITY_NOT_CONFIGURED`; use the authenticated browser capability where available. |
| Silverwing / JARVIS Brain | Silverwing's FastAPI app is mounted and its health endpoint reports `integrated`; model inference and JARVIS Brain provider availability were not verified. |

Only advertise a capability as ready when the running system's readiness check
confirms its configuration and availability.
