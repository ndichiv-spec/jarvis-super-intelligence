# JARVIS BRAIN v1 — Hugging Face Lineage

The Brain runtime (`brain_runtime/`) on `http://127.0.0.1:8011/v1` serves **two
Qwen3-4B variants** selected by `JARVIS_BRAIN_MODEL`. The Base lineage entry is
never overwritten by the SFT candidate (spec section 20).

## Artifact lineage

```
Kaggle (SFT training)
   |  _qwen_stage/jarvis_brain_sft.py  -> fine-tunes Qwen/Qwen3-4B
   v
Hugging Face (durable artifact repository)
   Qwen/Qwen3-4B                                     Base  (rev 1cfa9a7208912126459214e8b04321603b3df60c)
   videlisndichi/jarvis-brain-qwen3-4b-sft-v1        SFT candidate
   ^
   | (validated model)
v
Brain inference server :8011   (JARVIS_BRAIN_ENDPOINT)
```

## Brain models

| Model id (full_id)             | Base model_id            | HF repository                                  | Training   | Revision / commit                              | Params (B) | Status        |
|--------------------------------|--------------------------|------------------------------------------------|------------|------------------------------------------------|------------|---------------|
| `jarvis-brain-qwen3-4b-v1`     | `jarvis-brain-qwen3-4b`  | `Qwen/Qwen3-4B`                                | base       | `1cfa9a7208912126459214e8b04321603b3df60c`    | 4.004667   | experimental  |
| `jarvis-brain-qwen3-4b-sft-v1` | `jarvis-brain-qwen3-4b-sft` | `videlisndichi/jarvis-brain-qwen3-4b-sft-v1` | sft        | `main` (published by Kaggle SFT kernel)        | 4.004667*  | training      |

\* The SFT candidate shares the Qwen3-4B base parameter count; only the
adapter weights differ. Real parameter count is resolved from the published
manifest after the SFT is uploaded to Hugging Face.

## Model selection (`JARVIS_BRAIN_MODEL`)

- `jarvis-brain-qwen3-4b-v1`      → **Base** (the production default per §1)
- `jarvis-brain-qwen3-4b-sft-v1`  → **SFT candidate** (set while evaluating the Kaggle
  fine-tune; the SFT never overwrites the Base repo/identity)

Switching is purely a configuration switch — no server code changes. The
`BrainCatalog` maps every id to its authoritative HF repository; weights are
fetched from Hugging Face through `JARVIS_BRAIN_MODEL_CACHE`, never stored in
the JARVIS source tree (spec section 7).

## Local feasibility

Per the Base manifest's own evaluation metadata, Qwen3-4B local inference on
the JARVIS PC is **not feasible** (7.9 GB RAM, no GPU). The real
`TransformersBackend` therefore loads Qwen3-4B only on a GPU host (Kaggle /
remote). For local API-contract testing the runtime runs in an explicitly-labeled
`stub` mode (`JARVIS_BRAIN_BACKEND=stub`) which:

- enforces real bearer-token auth,
- reports `available=false` / `production_health=false` on `/health` (HTTP 503),
- prefixes every reply with `[brain-stub]`,
- is **never** selected as a silent fallback from the transformers backend.
