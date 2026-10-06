# Phase 36 — OpenAI-Compatible API

The authenticated compatibility router is mounted in the unified FastAPI app.
It reuses JARVIS model, provider, embedding, media, voice, and persistence
services. It does not claim a provider is available merely because a model is
listed.

## Available endpoints

| Method | Path | Behavior |
|---|---|---|
| `GET` | `/v1/models` | Approved/deployed registry models and the JARVIS embedding model; private registry fields are omitted |
| `GET` | `/v1/models/{model_id}` | Public-safe model metadata |
| `POST` | `/v1/chat/completions` | Gateway chat with provider-delta streaming and validated JSON/JSON Schema response formats |
| `POST` | `/v1/completions` | Text-prompt adapter over chat completions |
| `POST` | `/v1/embeddings` | 384-dimensional `jarvis-embedding-v1`, float or base64 output |
| `POST` | `/v1/images/generations` | Image generation through the existing image providers; generated local images are owner-scoped URLs |
| `GET` | `/v1/images/{image_id}` | Authenticated retrieval of locally stored generated image bytes |
| `POST` | `/v1/audio/transcriptions` | Whisper-compatible transcription using the configured voice provider |
| `POST` | `/v1/audio/speech` | MP3 speech synthesis using the configured voice provider |
| `POST` | `/v1/files` | Validated file upload with a 50 MiB limit and owner-bound metadata |
| `GET` | `/v1/files` | Owner-scoped file listing with cursor pagination |
| `GET` | `/v1/files/{file_id}` | Owner-scoped file metadata |
| `GET` | `/v1/files/{file_id}/content` | Owner-scoped file download |
| `DELETE` | `/v1/files/{file_id}` | Owner-scoped file deletion |
| `POST` | `/v1/moderations` | OpenAI moderation when an OpenAI moderation key is configured; otherwise returns unavailable |
| `POST` | `/v1/messages/count_tokens` | Anthropic-shaped input token estimate; authenticates with a JARVIS bearer key or `x-api-key` |
| `POST` | `/v1/chat/completions/count_tokens` | JARVIS chat input token estimate |

All compatibility responses include `Jarvis-Version` and `X-Request-ID`.
Authentication, validation, and provider failures use an OpenAI-style error
object. Chat usage is included only when the provider reports token counts;
embedding usage uses JARVIS's tokenizer. OpenAI token counts use a supported
`tiktoken` model encoding. The Anthropic-shaped count endpoint uses
`cl100k_base` because Anthropic's tokenizer is not exposed locally; its
`input_tokens` value is an estimate, not an Anthropic billing-token guarantee.

Streaming forwards actual provider deltas. A buffered-only provider response
is emitted as one chunk rather than being split into fabricated incremental
tokens. Unsupported sampling controls, tool execution, and structured JSON
streaming are rejected instead of silently ignored. JSON Schema outputs are
validated before success is returned.

Uploaded files are persisted under an isolated compatibility directory and
bound to their authenticated owner. Fine-tuning jobs and batch execution are
not exposed as successful operations here: their durable execution lifecycle
is assigned to Phase 37, and queuing a job without a worker would be misleading.
