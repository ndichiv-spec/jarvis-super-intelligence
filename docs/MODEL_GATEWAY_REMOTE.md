# JARVIS Model Gateway — Remote Inference (Qwen3-4B / Kaggle GPU)

JARVIS BRAIN v1 runs Qwen/Qwen3-4B (Apache-2.0, revision
`1cfa9a7208912126459214e8b04321603b3df60c`) on a **Kaggle GPU** and exposes an
OpenAI-compatible endpoint. The JARVIS PC (7.9 GB RAM, no GPU) never hosts or
trains Qwen3-4B — it only *talks HTTP* to the remote GPU host. Weights are never
committed to the JARVIS repository; Hugging Face / the Kaggle workspace is the
durable home.

## Routing policy (implemented in `jarvis_backend/gateway.py`)

1. **JARVIS Brain (remote)** — used first for general chat when
   `JARVIS_BRAIN_ENDPOINT` is set. Provider label `jarvis-brain`, backend
   `remote-openai-compatible`, device `gpu-remote`.
2. **Silverwing (offline)** — the local trained model
   (`silverwing-120m-base-v1`, :8010) is the offline fallback when the Brain is
   confirmed unreachable. The reply records `fallback`, so a Silverwing answer
   is never presented as a JARVIS Brain answer.
3. **Cloud / no-fake** — if neither is available and no real cloud provider key
   is configured, the gateway raises `PROVIDER_UNAVAILABLE`. It NEVER returns a
   deterministic echo as a "real" answer.

## Environment (.env)

```
# JARVIS_BRAIN_ENDPOINT=https://<kaggle-host>            # or https://<host>/v1
JARVIS_BRAIN_MODEL=jarvis-brain-qwen3-4b-sft-v1
# JARVIS_BRAIN_API_KEY=<optional bearer token>
```

If the endpoint URL already ends in `/v1`, the gateway appends
`/chat/completions`; otherwise it appends `/v1/chat/completions`.

## Health & latency

`GET /ai/status` now includes a `brain` block:

- `configured: false` — `JARVIS_BRAIN_ENDPOINT` not set.
- `configured: true, healthy: false` — endpoint set but a **real** probe
  failed. Health is never assumed: the probe is an actual tiny inference
  (user role → "Reply with the single word: ok") against `/v1/chat/completions`.
- `configured: true, healthy: true` — probe succeeded; `latency_ms` is the
  measured round-trip of that real inference.

## Triggering the pipeline (Kaggle)

1. Publish the SFT dataset to Hugging Face: `videlisndichi/jarvis-brain-qwen3-4b-sft-v1`.
2. Run `kaggle_kernel/jarvis_brain_qwen3_4b.ipynb` in a GPU session with Kaggle
   secret `JARVIS_HF_TOKEN` (HF write token). Section 7 benchmarks the **untuned**
   baseline first; section 13 runs small LoRA/QLoRA SFT; sections 14-15 publish
   adapter + artifacts only.
3. The Kaggle-hosted inference endpoint becomes `JARVIS_BRAIN_ENDPOINT` for
   the JARVIS PC.

## Honesty contract (unchanged, extended)

- An empty or `local`/`local-rule`/`sw-echo` response is never returned as an answer.
- Silverwing fallback replies carry `fallback.from`/`fallback.to`/`reason`.
- SFT candidate `jarvis-brain-qwen3-4b-sft-v1` is not promoted in the model
  registry until the baseline + SFT evaluation gate passes.