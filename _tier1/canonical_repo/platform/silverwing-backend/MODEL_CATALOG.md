# Silverwing Model Catalogue

This document catalogs the modern foundation models available to Silverwing,
their canonical API IDs, context windows, capabilities, and where they can be
served. The canonical, machine-readable source of truth is
`backend/model_catalog.py` (`MODEL_CATALOG`).

Last researched: September 2026.

---

## 1. Provider Overview

| Provider | SDK | Auth env var | Key model IDs | Self-hostable? |
|----------|-----|-------------|---------------|-----------------|
| **openai** | `openai` | `OPENAI_API_KEY` | `gpt-5.6-sol`, `gpt-5.5`, `gpt-oss-120b` | Some (GPT-OSS) |
| **anthropic** | `anthropic` | `ANTHROPIC_API_KEY` | `claude-fable-5-1`, `claude-opus-5`, `claude-sonnet-5` | No |
| **google** | `google.genai` | `GEMINI_API_KEY` | `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-3.8-flash` | Some (Gemma) |
| **groq** | `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b` | No (hosted) |
| **deepseek** | `openai` (custom base) | `DEEPSEEK_API_KEY` | `deepseek-v4-pro`, `deepseek-chat`, `deepseek-reasoner` | R1 via HF |
| **ollama** | `ollama` | `OLLAMA_HOST` | `llama3.3:70b`, `llama4:scout`, `qwen3:32b` | Yes |
| **llamacpp** | `openai` (custom base) | `LLAMACPP_API_BASE` | `Qwen3-32B-Q4_K_M.gguf`, `Llama-4-Scout-Q4_K_M.gguf` | Yes |
| **bedrock** | `boto3` | `AWS_PROFILE` | `anthropic.claude-opus-5-v1:0`, `openai.gpt-5.6-sol-v1:0` | No (hosted) |
| **vertex** | `google-cloud-aiplatform` | `GOOGLE_APPLICATION_CREDENTIALS` | `publishers/google/models/gemini-2.5-pro` | Some (open models) |
| **local** | none | none | `local-rule` | Yes |

---

## 2. Model Families

### 2.1 OpenAI GPT-5.x Series

| Model | Context | Max Out | Pricing (1M tok) | Open Weights | Notes |
|-------|---------|---------|-------------------|-------------|-------|
| **GPT-5.6 Sol** | 2 M | 32 K | $15 / $60 | No | Frontier reasoning |
| **GPT-5.6 Terra** | 2 M | 32 K | $3 / $12 | No | Cost-optimised |
| **GPT-5.6 Luna** | 2 M | 16 K | $4 / $16 | No | Multilingual-specialised |
| **GPT-5.5** | 1 M | 16 K | $6 / $24 | No | Previous flagship |
| **GPT-5.4** | 1 M | 16 K | $2.5 / $10 | No | High-throughput |
| **GPT-OSS 120B** | 131 K | 16 K | $0.15 / $0.60 | **Yes** | Open-weight |
| **GPT-OSS 20B** | 131 K | 16 K | $0.075 / $0.30 | **Yes** | Open-weight, lightweight |

**Serving options:** OpenAI API, AWS Bedrock, Vertex AI (for GPT-5.x)

### 2.2 Anthropic Claude 5 Series

| Model | Context | Max Out | Pricing (1M tok) | Open Weights | Notes |
|-------|---------|---------|-------------------|-------------|-------|
| **Claude Fable 5.1** | 1 M | 128 K | $10 / $50 | No | Most capable |
| **Claude Opus 5** | 1 M | 128 K | $5 / $25 | No | High-end reasoning |
| **Claude Sonnet 5** | 1 M | 128 K | $2 / $10 | No | Best price/perf |
| **Claude Haiku 4.5** | 200 K | 64 K | $1 / $5 | No | Fastest, cheapest |
| Claude 3.5 Sonnet (legacy) | 200 K | 8 K | $0.30 / $1.50 | No | Deprecated |

**Serving options:** Anthropic API, AWS Bedrock

### 2.3 Google Gemini 2.5/3.x Series

| Model | Context | Max Out | Pricing (1M tok) | Free Tier | Open Weights | Notes |
|-------|---------|---------|-------------------|-----------|-------------|-------|
| **Gemini 3.8 Flash** | 2 M | 64 K | $1.00 / $4.00 | No | No | Latest Flash, agentic |
| **Gemini 3.7 Flash** | 1 M | 64 K | $0.75 / $3.00 | No | No | Previous-gen Flash |
| **Gemini 2.5 Pro** | 1 M | 64 K | $1.75 / $7.00 | Yes | No | Most advanced |
| **Gemini 2.5 Flash** | 1 M | 64 K | $0.60 / $2.40 | Yes | No | Best price/perf |
| **Gemini 2.5 Flash-Lite** | 1 M | 8 K | $0.20 / $0.80 | Yes | No | Most budget-friendly |
| **Gemma 4 27B** | 128 K | 8 K | Free | Yes | **Yes** | Open lightweight |

**Serving options:** Google AI Studio API, AWS Bedrock, Vertex AI

### 2.4 DeepSeek

| Model | Context | Max Out | Pricing (1M tok) | Free Tier | Open Weights | Notes |
|-------|---------|---------|-------------------|-----------|-------------|-------|
| **DeepSeek V4 Pro** | 64 K | 8 K | $0.14 / $0.28 | Yes | No | Agent-focused, Responses API |
| **DeepSeek V3 Chat** | 128 K | 8 K | $0.14 / $0.28 | Yes | No | General-purpose |
| **DeepSeek R1** | 128 K | 8 K | $0.28 / $2.10 | Yes | **Yes** | Reasoning-specialised |
| **DeepSeek Coder** | 128 K | 8 K | $0.14 / $0.28 | No | No | Code-specialised |

**Serving options:** DeepSeek API, AWS Bedrock, Groq, Hugging Face

### 2.5 Meta Llama 4

| Model | Parameters | Experts | Context | Max Out | Open Weights | Notes |
|-------|-----------|--------|---------|---------|-------------|-------|
| **Llama 4 Scout** | 109 B | 16 | 512 K | 16 K | **Yes** | Efficient reasoning |
| **Llama 4 Maverick** | 402 B | 128 | 1 M | 16 K | **Yes** | Highest Llama-4 quality |
| Llama 4 Behemoth | 128 B | — | — | — | **Yes** | (Blog only, not in catalog) |

**Serving options:** Hugging Face, Ollama, llama.cpp, AWS Bedrock, Vertex AI, Groq

### 2.6 Qwen 3.x Series

| Model | Parameters | Context | Max Out | Pricing (1M tok) | Open Weights | Notes |
|-------|-----------|---------|---------|-------------------|-------------|-------|
| **Qwen3.8 27B** | 2.4 T | 131 K | 16 K | $0.80 / $4.00 | Partial | Latest multimodal |
| **Qwen3.6 27B** | — | 131 K | 16 K | $0.60 / $3.00 | Partial | Previous-gen |
| **Qwen3 235B A22B** | 235 B (MoE) | 128 K | 8 K | $1.20 / $4.80 | **Yes** | Largest open MoE |
| **Qwen3 Coder 480B** | 480 B (MoE) | 128 K | 8 K | — | **Yes** | Code-specialised |
| Qwen3 32B | 32 B | 128 K | 8 K | — | **Yes** | General-purpose |

**Serving options:** Alibaba Cloud API, AWS Bedrock, Ollama, Hugging Face, llama.cpp, Groq

### 2.7 GPT-OSS (OpenAI Open-Weight)

| Model | Parameters | Context | Max Out | Pricing (1M tok) | Open Weights | Notes |
|-------|-----------|---------|---------|-------------------|-------------|-------|
| **GPT-OSS 120B** | 120 B | 131 K | 16 K | $0.15 / $0.60 | **Yes** | Also free on HF |
| **GPT-OSS 20B** | 20 B | 131 K | 16 K | $0.075 / $0.30 | **Yes** | Fastest |

**Serving options:** OpenAI API, AWS Bedrock, Groq, Hugging Face

### 2.8 Amazon Nova

| Model | Context | Max Out | Notes |
|-------|---------|---------|-------|
| Nova Pro | 300 K | 8 K | Multimodal flagship |
| Nova Micro | 300 K | 8 K | Text-only, low-cost |
| Nova Lite | 200 K | 8 K | Lightweight multimodal |

**Serving options:** AWS Bedrock

---

## 3. Free / Tier Options Summary

| Model | Free tier? | Self-hostable? | Best for |
|-------|-----------|----------------|----------|
| GPT-OSS 120B | Yes | Yes | Open-weight reasoning |
| GPT-OSS 20B | Yes | Yes | Lightweight inference |
| Gemma 4 27B | Yes | Yes | Multimodal, open |
| Llama 4 Scout | Yes | Yes | Efficient agentic coding |
| Llama 4 Maverick | Yes | Yes | High-quality open model |
| Qwen3 235B A22B | Yes | Yes | Largest open MoE |
| DeepSeek R1 | Yes | Yes | Open-weight reasoning |
| Claude Haiku 4.5 | No (paid) | No | Cost-efficient tasks |
| Gemini 2.5 Flash-Lite | Yes | No | Budget-friendly cloud |

---

## 4. Serving Architecture

### 4.1 Cloud APIs (Hosted)
- **OpenAI API** — `api.openai.com/v1` (requires `OPENAI_API_KEY`)
- **Anthropic API** — `api.anthropic.com` (requires `ANTHROPIC_API_KEY`)
- **Google AI Studio** — `generativelanguage.googleapis.com` (requires `GEMINI_API_KEY`)
- **GroqCloud** — `api.groq.com` (requires `GROQ_API_KEY`)
- **DeepSeek API** — `api.deepseek.com/v1` (requires `DEEPSEEK_API_KEY`)
- **AWS Bedrock** — `bedrock-runtime.<region>.amazonaws.com` (requires AWS creds)
- **Vertex AI** — `aiplatform.googleapis.com` (requires GCP creds)

### 4.2 Local / Self-hosted
- **Ollama** — Local server at `OLLAMA_HOST` (default `http://127.0.0.1:11434`)
- **llama.cpp server** — Local server at `LLAMACPP_API_BASE` (default `http://127.0.0.1:8080/v1`)
- **Own trained models** — Serve via llama.cpp, Ollama, or the LocalProvider fallback

### 4.3 Training Your Own
Silverwing's own trained models (e.g., `local-rule`) are served through
`LocalProvider`, which provides a deterministic echo + rule fallback when no
external provider is configured. For full model serving, use llama.cpp or
Ollama with a GGUF-converted checkpoint.

---

## 5. Model Routing in Silverwing

Models are addressed by `<provider>:<model-id>` strings:

```
openai:gpt-5.6-sol         → OpenAI API
anthropic:claude-opus-5    → Anthropic API
google:gemini-2.5-pro      → Google AI Studio API
groq:llama-3.3-70b-versatile → GroqCloud
deepseek:deepseek-v4-pro   → DeepSeek API
bedrock:anthropic.claude-opus-5 → AWS Bedrock
vertex:gemini-2.5-pro      → Vertex AI
ollama:llama3.3:70b        → Local Ollama
llamacpp:Qwen3-32B-Q4_K_M  → Local llama.cpp server
local-rule                 → Deterministic local fallback
```

When a provider is unavailable (no key/SDK/server), Silverwing automatically
falls back to `LocalProvider` so the system stays operational.
