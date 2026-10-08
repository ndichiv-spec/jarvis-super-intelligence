# Silverwing Model Repository

Convention for the permanent, versioned home of Silverwing model artifacts.

## Layout

```
silverwing-models/
  README.md
  <model_id>/
    v1/  (or a named revision)
      model_manifest.json
      config.json
      tokenizer.json
      model.safetensors
      evaluation_report.json   (required before promotion beyond EXPERIMENTAL)
```

## Rules

- **Versions are immutable.** Never silently replace a registered revision.
  A changed artifact set gets a new revision/version.
- **Weights never live in the AI platform repository.** The dedicated inference
  runtime (`silverwing-runtime/`) is the only component that downloads and
  caches `.safetensors` files.
- Every directory MUST contain a valid `model_manifest.json` (see the
  `ModelManifest` schema in `silverwing-runtime/model_manifest.py`).
- Every artifact hash in a manifest is verified before the model is served.
- Only manifests are stored in this repository; durable weights referenced by
  `weights.storage_uri` may live in external storage (HF Hub / S3 / GCS /
  Azure / a local path for development).

## Lifecycle

```
TRAINING -> EXPERIMENTAL -> EVALUATED -> APPROVED -> ACTIVE
         -> DEPRECATED -> ARCHIVED
```

Promotion beyond EXPERIMENTAL requires recorded evaluation evidence
(`evaluation_report.json`) and is performed in the registry, not by editing a
manifest in place.