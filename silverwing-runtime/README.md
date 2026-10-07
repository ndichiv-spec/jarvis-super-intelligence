# Silverwing Runtime (layer 2) - deployment layout

This directory (`silverwing-runtime/`) holds the runtime **deployment** files:

* `requirements.txt` - runtime dependencies. `torch` and the cloud storage
  SDKs (`boto3`, `google-cloud-storage`, `azure-storage-blob`) are listed but
  commented out; install them on the inference machine only.

The actual importable package lives in the sibling directory
[`silverwing_runtime/`](../silverwing_runtime) (underscore), because a hyphen
directory is not a valid Python package name.

## Run

    python -m silverwing_runtime.server

Configuration is via environment variables (`SILVERWING_ENDPOINT`,
`SILVERWING_MODEL_REPO`, `SILVERWING_MODEL_CACHE`, `SILVERWING_API_KEY`,
`SILVERWING_PORT`, ...). See `silverwing_runtime/config.py`.

## API

    GET  /v1/health              runtime health (healthy only after warmup)
    GET  /v1/models              registered models (+ capabilities)
    POST /v1/chat/completions    OpenAI-compatible chat (incl. SSE streaming)
    POST /v1/generate            generation endpoint
    GET  /v1/telemetry           per-request telemetry (Observatory feed)

Weights are never stored in this repo; the runtime downloads and SHA-256
verifies them into the model cache on the inference machine only.