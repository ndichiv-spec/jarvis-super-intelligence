# JARVIS Platform — Preservation Manifest

Generated: read-only survey of `F:\AI`. Nothing was deleted, committed, pushed, or rotated.

Machine: Windows. Scope: complete JARVIS platform recoverability if this PC fails.

---

## A. Complete project inventory

`F:\AI` totals **39.04 GB**, 351 top-level entries, ~47,300 files inside the nested repo alone.

### A.1 Classification summary

| Class | Approx. size | Top-level paths |
|---|---|---|
| 1 SOURCE | ~25 MB | `backend/`, `jarvis_brain/`, `brain_runtime/`, `silverwing_runtime/`, `research_engine/`, `providers/`, `identity/`, `teacher_node/`, `teacher_mesh/`, `learning_arena/`, `jarvis_compute/`, `model_lifecycle/`, `docs/`, `tests/`, `eval*` suites, all `phase*.py`, `silverwing*.py`, `start_*.py`, `*.md` |
| 2 LARGE ARTIFACT | 34.18 GB (245 files) | `silverwing*/`, `_kout5/6/7`, `.sw_cache`, `_kaggle_ds_model`, `brain_training/artifacts` |
| 3 DATASET | ~780 MB | `videlisndichi-jarvis-brain-v1-sft/`, `_kaggle_silverwing_r2/corpus_build/`, `Dataset/`, `_kaggle_ds_corpus/`, `data/`, `kaggle_live_logs.txt` |
| 4 GENERATED OUTPUT | ~250 MB | `kaggle_full_output/`, `kaggle_kernel/`, `*_p7_*.txt`, `*_p8_*.py`, `_eval_*.txt`, `*_report.json`, all `*.log` |
| 5 CACHE | ~1.9 GB | `.sw_cache/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `__pycache__/`, `*.tsbuildinfo` |
| 6 SECRET | <1 MB | `.env`, `.env.bak`, `.env.bak2`, `_kaggle_auth.txt`, `.mcp.json`, `Jarvis-super-intelligence-/.env`, `frontend/web/.env.local`, `memory/data/*.key` |
| 7 DUPLICATE | 5.92 GB reclaimable | see A.4 |
| 8 MACHINE/ENV | ~2.0 GB | `Jarvis-super-intelligence-/frontend/web/node_modules` (470 MB), `.../.next` (1,371 MB), `silverwing-backend/venv` (47 MB), `.idea/` |
| 9 UNKNOWN | review needed | `Jarvis-super-intelligence-_/` (0 files), `Jarvis-super-intelligence-_fix_engine.py` (0 bytes), `50`, `Continue`, `-null`, `36b_full_suite.txt`, `silverwing-120m-gpgpu/` (0 files) |

### A.2 Model / artifact census

245 artifact files, 34.18 GB.

| Type | Files | Size |
|---|---|---|
| torch weights (`.pt`) | 98 | 18.79 GB |
| safetensors | 109 | 14.40 GB |
| numpy arrays (`.npy`) | 12 | 0.82 GB |
| DB blobs (`.db`) | 19 | 0.13 GB |
| other binary | 3 | ~0.01 GB |
| archives (`.zip`, `.sqlite`, `.idx`) | 4 | ~0.03 GB |

The dominant cost is **optimizer state**, not weights. `silverwing-120m` alone holds 12 `optimizer.pt` files at 916.3 MB each = 11.0 GB, plus 12 `model.safetensors` at 490.1 MB = 5.9 GB. Intermediate checkpoints are not needed for recovery.

### A.3 Recommended canonical artifacts + checksums

These are the files that actually constitute the platform's trained state. Everything else in the artifact set is regenerable.

| Path | Size | SHA-256 | Project |
|---|---|---|---|
| `silverwing-120m/final/model.safetensors` | 490.1 MB | `7a2fd08e85432aad73cac6911b67d9b9167077d981076d28106f606c4231a333` | Silverwing 120M |
| `silverwing-120m/final/optimizer.pt` | 916.3 MB | `7bd74e1e0da3418a5d264eeec382ee0459ae0a05500e06c41ef4cad82d310168` | Silverwing 120M (resume-capable) |
| `silverwing-r2000/final/model.safetensors` | 59.5 MB | `2c2775a7a7fe30359ce2c085e3278c69c99bac0452eb45e2cd007a91ffb724d2` | Silverwing r2000 |
| `baselines/silverwing-12m-v1-r2000/model.safetensors` | 59.5 MB | `2c2775a7a7fe30359ce2c085e3278c69c99bac0452eb45e2cd007a91ffb724d2` | baseline (dup of r2000) |
| `silverwing/final/model.safetensors` | 59.5 MB | `d1cf8889527146e6d8b0e18f8996eccdf55174bac1b41cc8737f8bd04a152bd0` | Silverwing 12M |
| `silverwing-stage3a/final/model.safetensors` | 59.5 MB | `9a142b46d2eece780193cc9c04ef0d9a06c53c4dddf2eecc7dbfe3ae663bb9aa` | Silverwing stage3a |
| `brain_training/artifacts/publish/model_snapshots/0567cbd1…/adapter/adapter_model.safetensors` | 180.0 MB | `c5d8998d6d66a7a758c7313818f663143a6bb18235918250ba0dfdaaa6ba6149` | JARVIS Brain LoRA |
| `videlisndichi-jarvis-brain-v1-sft/01_normalized.jsonl` | 37.8 MB | `81703f346fb3d0f5cc742909a68e3f20a1ba7cc6d3106aff212d98fb17b05728` | Brain SFT dataset |
| `_kaggle_silverwing_r2/corpus_build/corpus/train.npy` | 683.4 MB | `8d1d3e526935865b8da5cb599a4fbcd50f35b93cb404004713f11ecde5e5d168` | Silverwing 120M corpus (regenerable) |

Also required for recovery, small: `r2000_tokenizer.json`, `tokenizer.json`, `silverwing_120m_config.json`, `Dataset/silverwing-config/step-1000/config.json`, `videlisndichi-jarvis-brain-v1-sft/dataset-metadata.json`.

### A.4 Duplicates (5.92 GB reclaimable, all sha256-verified)

Largest groups:

| Copies | Each | Canonical | Reclaim |
|---|---|---|---|
| 4 | 490.1 MB | `silverwing-120m/final/model.safetensors` | 1,470 MB (but see note) |
| 2 | 916.3 MB | `silverwing-120m/final/optimizer.pt` | 916 MB |
| 6 | 95.0 MB | `silverwing/final/model.safetensors` | 475 MB |
| 8 | 59.5 MB | `silverwing/final/model.safetensors` | 416 MB |
| 3 | 180.0 MB | `brain_training/…/adapter/adapter_model.safetensors` | 360 MB |
| 3 | 95.0 MB | `silverwing-stage3a/final/optimizer.pt` | 190 MB |

Note on the 490.1 MB group: `_kaggle_ds_model`, `.sw_cache/silverwing-120m-base/r1`, `_kout6/…/best`, and `_kout7/…/best` share hash `da8604…`, which differs from `silverwing-120m/final` (`7a2fd0…`). These are **two distinct models**, not one — the first four are the Kaggle-published `silverwing-120m-base-r1`, the latter is the local `final`. Both must be kept.

---

## B. Proposed canonical Git repository structure

One private repo, `Jarvis-super-intelligence`, ~25-30 MB of source. History **starts fresh** — the public repo's compromised history is not carried over.

```
Jarvis-super-intelligence/          # private, fresh history
├─ backend/                        # FastAPI gateway + routers
├─ jarvis_backend/                 # provider gateway, errors
├─ brain_runtime/                  # JARVIS Brain serving
├─ silverwing_runtime/             # Silverwing inference runtime
├─ silverwing/                     # Silverwing lib: model/, training/, evaluation/,
│                                  #   kaggle/, tokenizer/, configs/, manifests/,
│                                  #   phase1_freeze.py, phase2_continue_pretrain.py
├─ jarvis_brain/                   # Brain orchestrator + clients
├─ brain_training/                 # training/eval pipeline (code only)
├─ silverwing_train.py, silverwing_120m_*.py, stage3*.py
├─ research_engine/                # data/capability/document/geography tools
├─ providers/                      # provider adapters (59 files)
├─ learning_arena/                 # problem generator
├─ identity/, teacher_node/, teacher_mesh/
├─ jarvis_compute/, model_lifecycle/
├─ frontend/                       # from nested repo, source only
│  ├─ web/                         # Next.js app (src/, public/, configs, package.json)
│  ├─ dashboard/, mobile/, static/, templates/, jarvis-remix/, jarvis-native/
│  └─ *.py, package.json, tsconfig*.json, pnpm-workspace.yaml
├─ infrastructure/, deployment/, monitoring/, scripts/, lib/, tools/, voice/
├─ drive_engine/, marketplace/, training/
├─ notebooks/                      # .ipynb (4 staged)
├─ docs/                           # all .md + audit JSON maps
├─ datasets_manifest/              # dataset metadata + checksums, NO bulk data
├─ configs/                        # .env.example only
├─ tests/
├─ scripts/ops/                    # start_all.ps1, stop_all.ps1, resume_*.cmd
└─ .gitignore                      # consolidated (see section I)
```

Excluded by rule: `node_modules`, `.next`, `venv`, `__pycache__`, `.mypy_cache`, `*.log`, all weight extensions, `.env*` except `.env.example`, `*.key`, `*.pem`, `*_auth.txt`.

Reconciling the nested repo means **flattening** `Jarvis-super-intelligence-/{frontend,lib,infrastructure,jarvis_backend,silverwing-backend,tests,drive_engine,…}` into the paths above, since two roots cannot coexist cleanly under one repo.

---

## C. Proposed artifact/model repository structure

Not Git. Content-addressed artifact storage (HF Hub private repo, S3, or NAS), with a manifest committed to the Git repo.

```
jarvis-artifacts/                  # storage root, NOT a git repo
├─ manifest/
│  ├─ artifacts.sha256             # every file below, path + sha256
│  └─ models.json                 # model name → revision → recipe → metrics
├─ silverwing/
│  ├─ silverwing-120m-final/
│  │  ├─ model.safetensors        # 490.1 MB  7a2fd08e…
│  │  ├─ optimizer.pt             # 916.3 MB  7bd74e1e…  (optional; enables resume)
│  │  ├─ config.json, tokenizer.json, model_manifest.json
│  │  └─ README.md                # lineage, eval scores, train command
│  ├─ silverwing-120m-base-r1/    # 490.1 MB  da860489…  (Kaggle-published)
│  ├─ silverwing-r2000/           # 59.5 MB   2c2775a7…
│  ├─ silverwing-stage3a/         # 59.5 MB   9a142b46…
│  └─ silverwing-12m/             # 59.5 MB   d1cf8889…
├─ jarvis-brain/
│  └─ qwen3-4b-sft-v1-lora/
│     ├─ adapter/adapter_model.safetensors   # 180.0 MB  c5d8998d…
│     ├─ config/, tokenizer/
│     └─ README.md                # base model, rank, alpha, merge instructions
└─ datasets/
   ├─ jarvis-brain-v1-sft/01_normalized.jsonl   # 37.8 MB  81703f34…
   ├─ silverwing-120m-corpus/                    # regenerable; store checksum only
   └─ silverwing-120m-corpus-recipe.md           # gutenberg source list + build cmd
```

Estimated: **~3.4 GB** for the canonical set, **~2.6 GB** without optimizer state.

---

## D. Proposed backup structure

Three tiers. Tier 1 is what makes a total PC loss survivable.

```
Tier 1 — Offsite (survives PC failure)
├─ git/jarvis-super-intelligence.git      # bare mirror, private
├─ git/jarvis-artifacts-manifest.git     # manifests + configs, private
├─ artifacts/jarvis-artifacts/           # object storage, versioned, private
├─ backup/secrets/                       # encrypted, separate credentials
│  └─ jarvis-secrets.age                 # age/sops bundle, key stored OFF this PC
└─ backup/db/                            # nightly
   ├─ jarvis.db                          # 160 KB
   └─ n8n/                               # 55.3 MB workflow DB

Tier 2 — Local cold (fast restore, same disk)
└─ F:/JARVIS_VAULT/                      # separate physical disk
   ├─ artifacts-canonical/              # the ~3.4 GB set
   ├─ datasets-canonical/
   └─ CHECKSUMS.sha256

Tier 3 — Full snapshot (last resort; 39 GB, post-migration only)
└─ F:/JARVIS_VAULT/full-YYYYMMDD/        # robocopy /restic of F:\AI post-cleanup
```

The full snapshot is a migration safety net, not the recovery plan. It must not be the only copy — that recreates the single-disk-failure problem.

Encrypted `jarvis-secrets.age` is mandatory and the age key must live off this PC. A backup of `.env` in plaintext on another disk is not a backup, it is a second exposure.

---

## E. Recovery procedure — new Windows PC

Phase 0 — prerequisites (30 min)
1. Install Git, Python 3.11+, Node 20 LTS, CUDA 12.x + cuDNN if GPU needed, 7-Zip.
2. Restore the age private key from the offline escrow (not from this PC).
3. `git clone` the private `jarvis-super-intelligence` mirror.
4. `git clone` the private `jarvis-artifacts-manifest` mirror.

Phase 1 — source (15 min)
5. Verify clone: `git log --oneline`, expect clean tree.
6. `pip install -r requirements.txt` (nested) and any backend requirements.
7. `npm ci` in `frontend/web` to rebuild `node_modules` (470 MB, not backed up).
8. `npm run build` to regenerate `.next` (1,371 MB, not backed up).

Phase 2 — artifacts (30 min)
9. `artifacts-pull` per `artifacts.sha256`, or `huggingface-cli download` from the private artifact repo.
10. Verify: `sha256sum -c artifacts.sha256`. Every line must report OK.
11. Place weights at the exact canonical paths listed in section A.3. Path layout is part of the contract — loader configs reference relative paths.

Phase 3 — secrets (10 min)
12. Decrypt `jarvis-secrets.age` → `.env` (root) and `.env` (platform).
13. **Re-rotate every credential before first use** — see section G. Restoring a backup does not un-expose a key.
14. Re-create `.env.local` for the frontend from `.env.example`.

Phase 4 — data & services (30 min)
15. Restore `jarvis.db` and `n8n/` from `backup/db`.
16. Seed Redis / vector store if used; these hold derived state, not source of truth.
17. Verify health: run `start_all.ps1`, then hit the platform health endpoint and the Brain health endpoint.

Phase 5 — verification (20 min)
18. `pytest tests/ -q` — must match the recorded baseline count.
19. Load each canonical model in its runtime and run one inference; compare output shape, not exact text.
20. Run one end-to-end chat through Brain → gateway → provider.

Total realistic restore: **~2 hours**, assuming artifact store and secrets escrow are reachable. Without tier 1, recovery is not possible at all.

---

## F. Files to retain locally until migration verified

Do not delete, move, or exclude from backup until a restore has been tested end-to-end on a second machine.

**Critical**
- `.env`, `.env.bak`, `.env.bak2` — only source of current credentials
- `_kaggle_auth.txt`
- `.mcp.json`
- `Jarvis-super-intelligence-/.env`
- `Jarvis-super-intelligence-/frontend/web/.env.local`
- `Jarvis-super-intelligence-/jarvis_data/n8n/.cache/n8n/public/types/credentials.json` (608 KB; contains private-key blocks and DB URLs — **encrypt before backing up**, never commit)
- `Jarvis-super-intelligence-/memory/data/audit_secret.key`, `encryption.key`

**Trained state**
- The 9 artifacts in section A.3 with checksums
- `r2000_tokenizer.json`, `tokenizer.json`
- All `dataset-metadata.json` / `dataset_manifest.json`

**Data**
- `Jarvis-super-intelligence-/jarvis_data/jarvis.db` (160 KB)
- `Jarvis-super-intelligence-/jarvis_data/n8n/` (55.3 MB)
- `videlisndichi-jarvis-brain-v1-sft/01_normalized.jsonl`
- `_kaggle_silverwing_r2/corpus_build/corpus/train.npy` until the gutenberg rebuild recipe is confirmed reproducible

**Git history**
- `F:\AI\.git` — 2.31 GB, currently 92% orphan objects (see section I). Contains no commits; the staged index is the only content. Recoverable from disk, but do not delete until the first commit exists.
- `Jarvis-super-intelligence-/.git` — 15.89 MB, 5 commits. **Copy the bundle to encrypted offline storage before doing anything else**, even though the secrets in it are compromised. The non-secret history is worth keeping.

---

## G. Credentials requiring rotation

Rotation is still outstanding. No credential was read, printed, altered, or revoked during this survey.

| Credential class | Live location | Already public? |
|---|---|---|
| `memory/data/audit_secret.key` | nested repo, commit `7cc02e4` | **YES** — repo is PUBLIC |
| `memory/data/encryption.key` | nested repo, commit `7cc02e4` | **YES** |
| OpenAI key | `.env`, `.env.bak` | no |
| Anthropic key | `.env` | no |
| Google API key | `.env` | no |
| HuggingFace token | `.env`, `.env.bak`, `.env.bak2` | no |
| NVIDIA NIM key | `.env` | no |
| JWT (session/signing) | `.env` | no |
| `JARVIS_BRAIN_API_KEY` | `.env` (literals removed from 3 phase6 scripts) | no |
| `JARVIS_ADMIN_PASSWORD` | `.env`, 16 nested scripts (scrubbed) | no |
| `JARVIS_SECRET_KEY` | `.env` | no |
| Kaggle token | `_kaggle_auth.txt` | no |
| n8n credentials + DB URLs | `jarvis_data/n8n/.cache/…/credentials.json` | no |
| SMTP, DB, N8N API keys | `.env` | no |

Priority: the two `memory/data/*.key` files first. They are public **now** and remain exposed until rotated, independent of anything in this plan.

The 608 KB n8n credentials file is a live secret store that no `.gitignore` currently covers by a content rule — it matched by filename only and is untracked in the nested repo. Verify it stays out of any commit.

---

## H. Estimated storage requirements

| Tier | Content | Size |
|---|---|---|
| Canonical Git repo (fresh) | source, docs, tests, manifests | 25-30 MB |
| Canonical Git repo (full history of nested repo, sanitized) | +5 commits, no secrets | ~+16 MB |
| Artifact set (canonical) | 9 model files + tokenizer/config | **~3.4 GB** |
| Artifact set (no optimizer state) | weights only | ~2.6 GB |
| Datasets | Brain SFT + Silverwing corpus | ~721 MB |
| DB backup | `jarvis.db` + n8n | ~56 MB |
| Secrets bundle (encrypted) | envs, keys, auth | <1 MB |
| **Tier 1 total (offsite)** | | **~4.2 GB** |
| | | |
| Local vault (cold) | artifacts + datasets + db | ~4.2 GB |
| Full snapshot (Tier 3, post-migration) | entire cleaned `F:\AI` | ~5-6 GB after cleanup |
| | | |
| Reclaimable now | duplicate artifacts | 5.92 GB |
| Reclaimable now | `node_modules` + `.next` + `venv` + caches | ~2.0 GB |
| Reclaimable now | orphan `.git` objects | ~2.3 GB |
| Reclaimable now | intermediate checkpoints | ~25 GB |
| **Total reclaimable** | | **~35 GB** |

`F:\AI` today is 39.04 GB. A correct preserved footprint is **~4.2 GB**. The 34.75 GB difference is intermediate checkpoints, build output, caches, and duplicates — all reproducible or duplicated.

GitHub free private storage is 500 MB. Source fits easily. The 3.4 GB artifact set does not; it needs HF private repos, S3, Backblaze, or a NAS.

---

## I. Files safely discardable only after verified backup

Precondition for **every** item below: tier-1 offsite backup complete, checksums verified, and one successful restore performed on a second machine. None of these are deleted now.

**Tier I-1 — verified regenerable, lowest risk**
```
Jarvis-super-intelligence-/frontend/web/node_modules/       470 MB   npm ci
Jarvis-super-intelligence-/frontend/web/.next/            1,371 MB   npm run build
Jarvis-super-intelligence-/frontend/web/tsconfig.tsbuildinfo  240 KB
Jarvis-super-intelligence-/silverwing-backend/venv/         47 MB   pip install -r
Jarvis-super-intelligence-/.mypy_cache/                    136 MB
.mypy_cache/, .pytest_cache/, .ruff_cache/, __pycache__/    ~1 MB
.sw_cache/                                                  506 MB   re-downloadable
```

**Tier I-2 — duplicate artifacts, canonical copy verified by sha256**
```
_kout5/                 59 MB
_kout6/                491 MB      490.1 MB  da860489…  dup of _kaggle_ds_model
_kout7/               3,230 MB      916.3 MB 7bd74e1e…  dup of silverwing-120m/final
_kaggle_ds_model/       491 MB      verified dup; recover from published repo
Dataset/silverwing-checkpoints*/       120 MB
kaggle_full_output/                    214 MB   Kaggle-synced
kaggle_kernel/, kaggle_download/        79 MB
```

**Tier I-3 — intermediate checkpoints (keep `final/` and `best/` only)**
```
silverwing-120m/checkpoints/step-{2,3,25,50,100,200,300,400,500}/   ~16.8 GB
silverwing-120m/{best,checkpoints}/*.safetensors  (keep one copy)    ~5.4 GB
silverwing/checkpoints/  silverwing-10m/checkpoints/
silverwing-10m-instr-probe/checkpoints/  silverwing-r2000/checkpoints/
silverwing-stage3a/checkpoints/                                       ~25 GB total
Jarvis-super-intelligence-/silverwing/local_run/exp_*/checkpoints/    ~3.2 GB
```

Retain per family: `final/model.safetensors`, `final/optimizer.pt` (only if resume matters), `best/model.safetensors`, plus `config.json` and tokenizer.

**Tier I-4 — transient and scratch**
```
_probe_out/            218 MB
_kaggle_ds_corpus/      37 MB
*.log, *_p7_*.txt, *_p8_*.py, _eval_*.txt, *_report.json
.git/objects/tmp_pack_V0jpof      1,307 MB   orphan
.git/objects/b6/90c17d4…          456 MB   orphan blob, 490 MB model.safetensors
.git/objects/f7/tmp_obj_Lnv8aJ    326 MB   orphan
.git/objects/3f5789fd…             88 MB   orphan blob, optimizer.pt
.git/objects/0e34c90f…             55 MB   orphan blob, model.safetensors
```

The 2.3 GB of `.git/objects` contains three model-weight blobs written by an aborted `git add --force`. I confirmed none is referenced by the staged index, and no staged blob exceeds 10 MB. With zero commits, `git gc --prune=now` reclaims it. There are also two `git count-objects` warnings for garbage temp files.

**Tier I-5 — empty and malformed**
```
Jarvis-super-intelligence-_/     0 files
Jarvis-super-intelligence-_fix_engine.py    0 bytes
silverwing-120m-gpgpu/           0 files
-null, 50, Continue
36b_full_suite.txt              malformed filename, needs manual review
._kcreate                        146 KB Kaggle API output capture
```

`._kcreate` was already excluded from the staged index.

---

## Verification status

| Check | Result |
|---|---|
| Staged index clean of credentials | yes — 492 files, 3.55 MB, 0 suspected real credentials |
| Staged index clean of weights | yes — no blob >10 MB |
| Gitlinks in index | none |
| Nested repo secrets covered by ignore rules | yes, verified via `git check-ignore` |
| n8n credentials file tracked | no — untracked in nested repo |
| Compensated history carried forward | no — proposed fresh history only |
| Working tree modified | no — read-only survey |
