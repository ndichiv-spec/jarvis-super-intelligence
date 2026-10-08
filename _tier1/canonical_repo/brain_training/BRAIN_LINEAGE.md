# JARVIS Brain v1 — Training Lineage

Authoritative record of the **training** lineage for JARVIS Brain v1 (mirrors
`silverwing-stage3a/run_manifest.json` layout). The runtime identity lives in
`brain_runtime/BRAIN_LINEAGE.md` + `brain_runtime/model_registry.py`; this file
documents the **training** lineage (base → method → dataset → publish → registry).
All values are real and currently observed (spec S30).

## 1. Base model (frozen)

| field        | value                                                 |
|--------------|-------------------------------------------------------|
| model_id     | `Qwen/Qwen3-4B-Base`                                  |
| revision     | `1cfa9a7208912126459214e8b04321603b3df60c` (pinned)   |
| parameters   | 4,004,667,392                                         |
| architecture | `Qwen3ForCausalLM`                                    |
| sha256       | (verified on Kaggle via `hf_model_info` — not re-downloaded on dev box) |

The base is **frozen**; the SFT does NOT overwrite `Qwen/Qwen3-4B` (per the SFT
manifest `archive_note`).

## 2. SFT candidate

| field            | value                                                |
|------------------|------------------------------------------------------|
| model_id         | `jarvis-brain-qwen3-4b-sft-v1`                       |
| registry full_id | `jarvis-brain-qwen3-4b-sft-v1`                       |
| base             | `Qwen/Qwen3-4B-Base`                                 |
| method           | `sft` → LoRA adapter + QLoRA 4-bit nf4 (r=64, alpha=128) |
| training_method  | `sft` (registry label)                               |
| status           | `training` (NOT published)                           |
| storage          | remote-safetensors-sharded-hf → `hf://videlisndichi/jarvis-brain-qwen3-4b-sft-v1` |
| merged           | false (adapter; NOT a merged model)                  |
| weights on disk? | NO — weights never in the JARVIS source tree         |

## 3. Training recipe (reused from `jarvis_brain_sft.py`, spec S6)

```
Quantization: BitsAndBytesConfig(load_in_4bit=True,
                  bnb_4bit_quant_type='nf4',
                  bnb_4bit_compute_dtype=fp16,
                  bnb_4bit_use_double_quant=True)
LoRA:         LoraConfig(r=64, lora_alpha=128,
                  target_modules=[q_proj,k_proj,v_proj,o_proj],
                  lora_dropout=0.1, bias='none', task_type='CAUSAL_LM')
Training:     per_device_train_batch_size=1, gradient_accumulation_steps=8,
                  num_train_epochs=1, lr=2e-4, fp16 (=not no_qlora),
                  logging_steps=10, save_steps=200, save_total_limit=2,
                  eval_strategy='no'
Eval:         r2000 inline scorers (MATH/LOGIC/KNOW/CK); NaN/Inf abort
Output:       adapter LoRA -> /kaggle/working/jarvis-brain-qwen3-4b-sft-v1
Manifest:     run_manifest.json with weights_on_kaggle_only=True
```

## 4. Dataset lineage

- Corpus repo: `videlisndichi/jarvis-brain-v1-sft` (HF dataset; local copy
  `videlisndichi-jarvis-brain-v1-sft/01_normalized.jsonl`)
- Examples: 292 passages (wikipedia 231 / gutenberg 45 / wikibooks 16)
- Splits: train 238 / validation 22 / test 32 (deterministic `sha256 % 80/90/10`)
- Token count: 10,273,691 (manifest, Kaggle-produced w/ Qwen tokenizer);
  offline estimate 10,118,350 (char `/3.8`).
- Corpus sha256 (manifest): `9cbcfb3c551bfac137cce9fa9a26b6c9049277c3060a87b42db28dc42100c2cf`
- **Integrity NOTE:** the locally-staged `01_normalized.jsonl` sha256 is
  `81703f346fb3d0f5cc742909a68e3f20a1ba7cc6d3106aff212d98fb17b05728` — the
  re-staged copy's bytes differ from the manifest, though counts/splits/sources
  all match. Re-stage the canonical Kaggle corpus to clear.

## 5. Publish → registry flow (planned; gated)

```
Kaggle checkpoint
  -> brain_training/hf.py:save_publish_intent()  (PublishIntent, merged=False)
  -> HF Hub upload (model_base / model_sft / training-data)
  -> commit/revision
  -> BrainCatalog entry update (status: candidate -> validated -> promoted)
```

Current registry state:

| model_id                        | status     | source             |
|---------------------------------|------------|--------------------|
| `jarvis-brain-qwen3-4b-v1`      | experimental | silverwing-models/ |
| `jarvis-brain-qwen3-4b-sft-v1`  | training   | silverwing-models/ (not published) |

No publish has occurred. `promotion_gate` current stage = `experimental`.

## 6. Promotion history

- `experimental` (current): SFT candidate defined; not published/evaluated.
- `candidate`: awaits SFT metrics + baseline.
- `validated`: awaits comparison + security scan + artifact-load smoke.
- `promoted`: MANUAL gate only (§18); never auto.
