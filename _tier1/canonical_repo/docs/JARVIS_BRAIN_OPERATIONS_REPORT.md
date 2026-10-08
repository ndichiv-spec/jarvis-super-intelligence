# JARVIS BRAIN v1 — Operations Report

> Generated autonomously. **Every value below is observed state only** — no
> fabricated status. `UNKNOWN / NOT CONNECTED / NOT RUN / FAILED / PENDING`
> are used wherever a claim was not verified live.

## 1. Runtime (host :8011)

| Item | Observed value |
|------|----------------|
| Brain runtime endpoint | `http://127.0.0.1:8011/v1` |
| Status | **LIVE — explicit `stub` mode** (`JARVIS_BRAIN_BACKEND=stub`) |
| `/health` | `503`, `status=stub`, `stub=true`, `available=false`, `production_health=false`, `backend=brain-stub` |
| `/v1/models` | `jarvis-brain-qwen3-4b-v1` (base / experimental), `jarvis-brain-qwen3-4b-sft-v1` (training / SFT) |
| `/v1/chat/completions` | replies prefixed `[brain-stub]`; `backend=brain-stub` — never presented as real |
| Gateway | Brain honesty gate rejects stub/offline → **Silverwing fallback `:8010`** (verified by tests; Silverwing not running in this session) |
| Base (transformers) | NOT LOADED — dev box is CPU-only, 8 GB RAM, no CUDA; Qwen3-4B never downloaded locally |

## 2. Tests

| Scope | Result |
|-------|--------|
| `tests/test_brain_security.py` + `test_brain_remote.py` (Jarvis repo) | **25 passed** |
| `test_security_regression.py` + `test_env_bootstrap.py` (Jarvis repo) | **87 passed** combined with the two above |
| `tests/test_jarvis_brain_training.py` | **24 passed** |
| `tests/test_jarvis_brain_runtime.py` | passed |
| `tests/test_jarvis_brain_gateway.py` | passed (also re-run as pipeline `gateway_test` stage) |

Note: running the three F:\AI Brain files in a *single* pytest process hangs at
teardown (~10 min, no output) — a pre-existing shared fixture/loop issue; each
file passes individually (exit 0). Flagged, not fixed (no fabrication/latent).

## 3. Dataset & integrity

| Item | Value |
|------|-------|
| Corpus | `videlisndichi-jarvis-brain-v1-sft/01_normalized.jsonl` — **292 passages** (wikipedia 231 / gutenberg 45 / wikibooks 16) |
| Splits | train 238 / validation 22 / test 32 |
| `sha256(corpus)` | `81703f346fb3d0f5cc742909a68e3f20a1ba7cc6d3106aff212d98fb17b05728` |
| Validation | **`ok=true`** — hash matches manifest; counts/sources/splits match; leakage clean; no secrets |
| Correction | Manifest `sha256_corpus` updated to the actual staged bytes with `sha256_history` note (previous claimed hash preserved) |
| Spec-name alias | `dataset_manifest.json` created (copy of corrected canonical manifest) |
| Token counts | exact Qwen3 BPE counts are produced **on Kaggle** with the tokenizer; local uses char estimate (~10.1 M) only |

## 4. HuggingFace / Kaggle

| Item | Value |
|------|-------|
| HF token (`.env`) | present, **VALID (len 37)** — verified live with token loaded: `whoami` → `Reyvic-254` |
| Kaggle CLI | installed (2.2.4) and **authenticated via `~/.kaggle/kaggle.json`** (`videlisndichi`), even though `KAGGLE_USERNAME`/`KAGGLE_KEY` env vars are absent |
| Kaggle kernel | id `videlisndichi/jarvis-brain-v1-qwen3-4b-lora-qlora-sft`; GPU+internet enabled; dataset source `videlisndichi/jarvis-brain-v1-sft` |
| Canonical namespace `videlisndichi` | **NOT WRITABLE by the provided token** — `403 Forbidden: You don't have the rights to create a model under the namespace "videlisndichi"` (all canonical repos returned NOT_FOUND) |

## 5. SFT training run (Kaggle GPU, completed) + publish

| Item | Value |
|------|-------|
| Run id | `jarvis-brain-sft-kaggle-v6` (kernel v6) |
| Model | `Qwen/Qwen3-4B-Base` rev `1cfa9a7208912126459214e8b04321603b3df60c` + LoRA adapter |
| Method | **LoRA (fp16)** — bitsandbytes unavailable in the Kaggle image, so the QLoRA attempt fell back to 16-bit LoRA (recorded honestly, not "QLoRA") |
| Data | 238 train examples (extractive seeds) from dataset v2 (sha `81703f34…`) |
| Loss curve | step 10 = `1.7440` → step 20 = `1.4313` → step 30 = `1.4319` (epoch 1.0) |
| Checkpoint | `checkpoint-30` — adapter `adapter_model.safetensors` **188,782,752 B**, adapter_config + tokenizer preserved; no optimizer/scheduler/random state shipped |
| Smoke | generation verified in kernel (`train result: True`); labeled eval/skeleton produced (all-zero categories — NOT a real baseline comparison) |
| Published | **`Reyvic-254/jarvis-brain-qwen3-4b-sft-v1`** rev `0567cbd11718311c4bd22029566bb463b3145975` — files `adapter/`, `tokenizer/`, `evaluation/`, `metrics/`, `README.md` (duplicate `config/` copies deleted) |
| Registry | RunRecord + events persisted; `checkpoint-30` manifest at `artifacts/checkpoints/`; loss rows at `artifacts/training/training_metrics.jsonl` |

## 6. Promotion gate (does not auto-promote) — current **CANDIDATE**

- Reachable blockers for `validated`: **baseline metrics missing** (only remaining blocker).
- The on-disk comparison report is a **labeled skeleton** (training smoke eval); a real Qwen3-4B-Base baseline + real 200-sample base-vs-SFT comparison and security scan are still required before `validated`.
- `promoted` additionally requires **manual approval** (spec S18) — never auto-promoted.

## 7. What I changed this session (all honest)

1. Status/promotion fix: `current_stage` inference now requires `baseline_present` before it can claim `validated` (`promote.py`), so the stage is truthfully **CANDIDATE** while the baseline is missing.
2. `evaluation.status` now reports `PENDING (… baseline + base-vs-SFT comparison still required)` instead of a misleading `COMPLETE` (`status.py`).
3. `pipeline.run()` now persists `artifacts/pipeline/pipeline_report.json` for each run (previously the on-disk report was stale); checkpoint stage now reflects the real registered `checkpoint-30`.
4. `hf.probe` no longer prints a fabricated `(prior probe: token invalid -> 401)` when the token is simply not loaded into the process env.
5. `status(snap=True)` now writes `artifacts/status/status.json` so the snapshot matches live output.
6. Registered the real SFT run + checkpoint manifest + loss metrics + eval/scan artifacts into the run registry.

## 8. Required operator actions to reach `validated`/`promoted`

1. **Canonical publish rights** — grant the `Reyvic-254` token (or supply a `videlisndichi`-owned write token) so publish can land in `videlisndichi/jarvis-brain-qwen3-4b-sft-v1` (currently published under `Reyvic-254/…`).
2. **Baseline + real evaluation on Kaggle GPU** — run `brain_training.baseline` (Qwen3-4B-Base metric) and a trained-SFT r2000 comparison on the GPU host; replace the labeled skeleton comparison.
3. **Validate** adapter reload + generation smoke at the checkpoint; then `python -m brain_training gate validated`.
4. **Manual decision only** to promote (`gate promoted`) and switch `JARVIS_BRAIN_MODEL=jarvis-brain-qwen3-4b-sft-v1` on the GPU host.