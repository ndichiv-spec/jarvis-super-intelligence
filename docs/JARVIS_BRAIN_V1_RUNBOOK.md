# JARVIS BRAIN v1 - Execution Runbook (S1-S26)

> ENVIRONMENT RESTORATION -> Qwen3-4B BASELINE -> KAGGLE SFT. Everything that can
> be verified locally without your GPU/secret Brain endpoint is DONE & green. What
> requires your GPU-host URL + API key is scaffolded as a RUNNABLE path that
> currently reports an honest "unconfigured" status. No benchmark or training
> numbers are fabricated.

## Verified pre-flight (as of this build)

| item | status | evidence |
|---|---|---|
| S1 admin identity | DONE | core.admin_email() reads JARVIS_ADMIN_EMAIL from env; dev default admin@jarvis.local; prod fail-fast RuntimeError. Live: ndichiv@gmail.com. 11/11 tests pass. |
| S2 admin login via email | DONE | email is identity, not credential; no password in KV. |
| S3 env load at runtime | DONE | start_all.ps1 lines 42-45 source F:\AI/.env into $env; _env.apply() setdefaults. Verified live. |
| S5 Brain Bearer auth | DONE | gateway._jarvis_brain_api_key() via vault SecretsManager.get_or_none("brain_api_key"); Bearer header only when non-empty. /ai/status returns masked brain_api_key_configured bool. |
| S5 honest brain probe | DONE | probe_brain() -> unconfigured/healthy/unhealthy (never the raw key). Live: configured=False. |
| S7 vault | DONE | Env->os.environ / DotenvBackend->.env / FileBackend enc-decrypt. docs/brain_api_key_security.md. |
| Silverwing-120M / r2000 evals | REAL | silverwing-120m/evaluation_report.json + r2000_eval.json (identical schema). math 0/8, logic 4/6, knowledge 0/8, coding 0/3. |
| Test suite | GREEN | 278 passed, 1 skipped (includes 19 brain + 11 admin + 13 api-key-at-rest). |
| S23 Qwen weights under F:\AI | BLOCKED (by design) | not stored locally; base pulled from HF on Kaggle only. |

## S1 Restore the canonical environment file

- F:\AI/_env.py is the canonical env (complete, matches the .pyc symbol table).
  _env.apply() setdefaults; is_production() = JARVIS_ENV in {production,prod};
  require_production() fail-fast if prod and JARVIS_ADMIN_EMAIL empty or Brain
  endpoint set without key.
- start_all.ps1:42-45 sources F:\AI/.env into the process env. No load_dotenv() call
  exists in platform Python by design (would break dev-fallback tests).
- The live F:\AI/.env (redacted on read):
  - JARVIS_ADMIN_EMAIL=ndichiv@gmail.com  <- your identity, env-driven
  - JARVIS_BRAIN_ENDPOINT=  (empty)        <- SET YOURS
  - JARVIS_BRAIN_API_KEY=  (empty)        <- SET YOURS
  - JARVIS_BRAIN_MODEL=jarvis-brain-qwen3-4b-sft-v1
  - OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY / HF_TOKEN / JARVIS_SECRET_KEY / N8N_* preserved.
- .env.example has the same blocks with placeholders (no real secrets). Never commit
  JARVIS_BRAIN_API_KEY.

## S2 / S5 Admin identity + Brain Bearer auth + redaction (DONE + verified)

- jarvis_backend/core.py:72 admin_email() reads JARVIS_ADMIN_EMAIL (dev default
  admin@jarvis.local; prod raises).
- jarvis_backend/gateway.py:130-145 _jarvis_brain_api_key()/_jarvis_brain_api_key_configured()/
  _jarvis_brain_endpoint() read the key via the vault (infrastructure.vault.manager
  get_secrets_manager().get_or_none("brain_api_key")).
- jarvis_backend/gateway.py:428-431: auth_token = _jarvis_brain_api_key();
  headers["Authorization"] = Bearer {auth_token} ONLY when non-empty.
- jarvis_backend/gateway.py:507-544 probe_brain() honesty: empty ->
  {configured:False, healthy:False, endpoint:None, detail:"JARVIS_BRAIN_ENDPOINT not set"};
  real inference required for healthy:True.
- jarvis_backend/routers/ai.py:149-150: /api/v1/ai/status returns masked
  brain_api_key_configured bool + brain_endpoint + brain_model + probe. Never the raw key.
- Verified: grep for the key near gateway lines 409-460 finds no logging of the token.
- docs/brain_api_key_security.md documents storage + redaction.

## S3 Verify env loading at runtime (DONE)

From F:\AI/Jarvis-super-intelligence- (platform root):
    $env:PYTHONPATH = "F:\AI;F:\AI/Jarvis-super-intelligence-"
    python -c "import _env; _env.apply(); import os, jarvis_backend.core as core, jarvis_backend.gateway as gw; print('admin=',core.admin_email()); print('brain_ep=',gw._jarvis_brain_endpoint()); print('key_cfg=',gw._jarvis_brain_api_key_configured())"
Expected (live, your .env):
    admin= ndichiv@gmail.com
    brain_ep= (unset)
    key_cfg= False
## S5 Qwen3-4B baseline benchmark + S6 fair comparison (DONE)

F:\AI/jarvis_brain_baseline.py (compile-checked + RUN). It executes the REAL r2000
benchmark (math/logic/knowledge/coding, identical scorers to stage3a_evaluate.py)
against the remote Brain via OpenAI /v1/chat/completions with Bearer <JARVIS_BRAIN_API_KEY>
resolved through the vault, and reuses the existing Silverwing-120M + r2000 reports
for those columns (identical schema).

    cd F:\AI
    python jarvis_brain_baseline.py            # default -> Qwen unconfigured until key set
    python jarvis_brain_baseline.py --compare-only   # reuse existing reports, no Brain call
    python jarvis_brain_baseline.py --brain     # force Qwen column (needs configured Brain)

Outputs:
- F:\AI/qwen3_4b_baseline.json        (status = unconfigured until key set)
- F:\AI/qwen3_4b_baseline.md
- F:\AI/jarvis_brain_comparison.json  (real Silverwing/r2000 numbers + honest Qwen slot)

> Gen params (locked, mirror stage3a): FIXED 0.8/0.9/64; math/logic/knowledge 0.5/0.95/40;
> coding 0.5/0.95/120. Coding answers are exec-checked in a sandboxed subprocess (15s) -
> never in-process.

## S6 Admin Console actions

The backend exposes the wiring; the key itself is never stored in app KV (key stays
in the vault / deployment secrets; see docs/brain_api_key_security.md).

| action | implementation | never exposes |
|---|---|---|
| Test Connection | GET /api/v1/ai/status -> brain.probe_brain() (configured/healthy/detail) | the raw key |
| Configure | write JARVIS_BRAIN_ENDPOINT + JARVIS_BRAIN_API_KEY to secret store (Kaggle env or vault FileBackend), not app KV | raw key in logs/trace |
| Rotate | re-set both secrets in the store; restart backend (key loaded per-request via get_or_none) | key in state files / git |
| Revoke | delete JARVIS_BRAIN_API_KEY from the secret store + invalidate at the Brain host | stale key reuse |

Backend surface (already live): brain_api_key_configured bool + probe_brain() dict (no raw key).
## S7 / S8 / S9 SFT dataset build + format + leakage (DONE)

F:\AI/build_sft_dataset.py (compile-checked + RUN). Builds the dataset REGISTRY from
F:\AI/01_normalized.jsonl (292 passages: wikipedia 231 / gutenberg 45 / wikibooks 16).
It does NOT fabricate assistant turns (see S7 note).

    cd F:\AI
    python build_sft_dataset.py

Outputs:
- F:\AI/jarvis_brain_sft_dataset_manifest.json  (and .md mirror)
  - splits: train 238 / val 22 / test 32 (sha256 % 100 -> 80/10/10)
  - tokens (Qwen3 BPE, tokenizer from _qwen_stage/.../v1/tokenizer.json):
    train 8,449,295 / val 456,005 / test 1,368,391 (total ~10.27M)
  - eval_excluded_count: 0 (no corpus passage overlaps any r2000 eval prompt)
  - no_fabrication: True  (corpus stats + synthesis plan only)
- SFT chat format: {"messages":[{"role","content"},...]} with system/user/assistant.
- S9 leakage check: the r2000 prompt set + r2000/silverwing "generations" keys are
  hashed; any overlapping passage is excluded from train/val/test.
  integrity.benchmark_examples_excluded=True, eval_prompt_set_sha256=...

> S7 truth: assistant turns are synthesized by the KAGGLE kernel using the JARVIS Brain
> as the teacher LM (your JARVIS_BRAIN_API_KEY on Kaggle). When the Brain is unavailable,
> the kernel falls back to a clearly-flagged extractive seed (low quality, pilot-only).

## S10 / S11 / S12 / S13 / S14 Kaggle LoRA/QLoRA SFT kernel (DONE, scaffold)

F:\AI/_knl/jarvis_brain_sft.py (compile-checked, dry-run clean) + _knl/kernel-metadata.json.

    cd F:\AI
    python _knl/jarvis_brain_sft.py               # dry-run: build 20 examples, no training
    python _knl/jarvis_brain_sft.py --train        # GPU only -> LoRA/QLoRA SFT (Kaggle)
    python _knl/jarvis_brain_sft.py --train --no-qlora   # 16-bit LoRA instead of 4-bit QLoRA

Design:
- S11 base FROZEN: only PEFT adapters trained (target_modules q/k/v/o).
- S12 pilot-first: small TrainingArguments; NaN/Inf loss check aborts the pilot.
- S13 generation smoke test (adapter save -> reload -> generate) before declaring done.
- S14 artifact jarvis-brain-qwen3-4b-sft-v1 (matches JARVIS_BRAIN_MODEL); outputs land
  in /kaggle/working/jarvis-brain-qwen3-4b-sft-v1 only.
- S23: Qwen3-4B base pulled from Qwen/Qwen3-4B-Base on HF ON KAGGLE; never stored under F:\AI.
  (Local CPU inference of 4B is infeasible for a real benchmark; baseline goes via the
  remote Brain.)

Kaggle run:
1. Upload jarvis_brain_sft_dataset_manifest.json + 01_normalized.jsonl as dataset
   (ndichiv/jarvis-brain-v1-sources).
2. Set Kaggle secrets: JARVIS_BRAIN_ENDPOINT, JARVIS_BRAIN_API_KEY, JARVIS_BRAIN_MODEL, JARVIS_HF_TOKEN.
3. Use GPU (T4/P100/L4). Run: python _knl/jarvis_brain_sft.py --train
## S15 / S16 / S25 end-to-end test, capability gate, final report

Sequence after a Kaggle SFT run:
    # 1) baseline (pre-SFT) Qwen scores -> qwen3_4b_baseline.json
    python jarvis_brain_baseline.py
    # 2) SFT run on Kaggle -> /kaggle/working/jarvis-brain-qwen3-4b-sft-v1/*_report.json
    # 3) post-SFT Qwen evaluation (serve the trained adapter via Brain, else re-run --compare-only)
    python jarvis_brain_baseline.py
    # 4) gate (S16): PROMOTE only if ALL hold:
    #    (a) instruction-following improves vs baseline (accuracy up / no regression),
    #    (b) no material regression on any category,
    #    (c) runtime stable (no NaN/Inf; adapter saves/reloads; generation works),
    #    (d) security checks pass (key redacted; no leak in logs/trace).
    # 5) if promoted -> pin jarvis-brain-qwen3-4b-sft-v1 in /AI/.env + deploy.
    # 6) if not -> iterate dataset / hyperparams, do NOT serve.

S25 final report = docs/brain_api_key_security.md (S7) + this runbook +
jarvis_brain_comparison.json + jarvis_brain_sft_dataset_manifest.{json,md}.

S16 capability gate (verbatim): PROMOTE SFT only if instruction-following improves
AND no material regression AND runtime stable AND security checks pass. The kernel
writes evaluation_report.json / comparison_report.json so the gate is checkable from
the artifacts; the pilot (S12) must show loss decreasing with no NaN/Inf before a
full run.

## Monitor wiring (reuse existing)

- F:\AI/monitor_10m.py (existing) + _k* output dirs poll the runtime.
- Brain health: gw.probe_brain() (live status). 10-minute poll:
    while ($true) { python -c "import jarvis_backend.gateway as gw; print(gw.probe_brain())" ; sleep 600 }
- The Silverwing monitor (_kaggle_kernel/silverwing_continue_gpu.py +
  silverwing-10m-monitor.log pattern) is the template; the same pattern applies
  to the Brain endpoint (probe -> healthy/unhealthy/unconfigured).
- Metrics: metrics.jsonl (per-step loss/throughput) + capability_history.json
  (per-epoch category scores) in /kaggle/working/jarvis-brain-qwen3-4b-sft-v1/.

## What is NOT done (blocked by your secrets, by design)

- JARVIS_BRAIN_ENDPOINT / JARVIS_BRAIN_API_KEY are empty in F:\AI/.env (you set them).
  Until then, Qwen is "unconfigured" (honest); Silverwing/r2000 columns are still the
  REAL existing numbers. This is intentional, not a gap.
- Qwen3-4B baseline + SFT on GPU require your remote GPU host / Kaggle + keys. I cannot
  execute GPU/secret-bound steps. Set the two Brain values (and HF_TOKEN + Kaggle account),
  then run the commands above. No results on those steps are fabricated.
## Kaggle publish status (runbook)

- Dataset (PRIVATE, submitted, pending backend processing):
  https://www.kaggle.com/datasets/videlisndichi/jarvis-brain-v1-sft
  contents: jarvis_brain_sft_dataset_manifest.json + 01_normalized.jsonl (292 passages).
- Kernel (PRIVATE, pushed v1):
  https://www.kaggle.com/code/videlisndichi/jarvis-brain-v1-qwen3-4b-lora-qlora-sft
  GPU ON, internet ON, dataset_source = videlisndichi/jarvis-brain-v1-sft.
- To EXECUTE training (I CANNOT inject secrets via CLI):
  Kaggle UI -> notebook -> Add Secret, one each:
    JARVIS_BRAIN_ENDPOINT   (your remote Brain /v1 base URL; needed for teacher synthesis)
    JARVIS_BRAIN_API_KEY    (Bearer teacher key)
    JARVIS_BRAIN_MODEL      (e.g. jarvis-brain-qwen3-4b-sft-v1)
    JARVIS_HF_TOKEN         (pulls Qwen/Qwen3-4B-Base from HF; accept Qwen3 license on HF first)
  then "Commit & Run" (GPU T4/P100/L4). Outputs land in
  /kaggle/working/jarvis-brain-qwen3-4b-sft-v1/ (metrics.jsonl, evaluation_report.json,
  comparison_report.json, capability_history.json, run_manifest.json, adapter).
- Without JARVIS_HF_TOKEN the kernel cannot download Qwen3-4B (it will stop with a
  HF auth/load error - not a fabricated result). Without JARVIS_BRAIN_ENDPOINT the kernel
  falls back to the honest extractive-seed (low quality, pilot-only) and the S16 gate
  will reject promotion.
- No local GPU and no HF token in this shell, so training is run on KAGGLE only.