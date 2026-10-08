"""Append a safe Remote JARVIS Brain section to /AI/.env.example (placeholders only)."""
from pathlib import Path

p = Path("/AI/.env.example")
e = p.read_text(encoding="utf-8")

anchor = "JARVIS_API_KEY=use-the-same-value-as-N8N_BASIC_AUTH_PASSWORD\n"
assert e.count(anchor) == 1, ("anchor", e.count(anchor))

brain = (
    "\n"
    "# --- Remote JARVIS Brain (spec §5) ---\n"
    "# Remote OpenAI-compatible Brain endpoint (GPU host serving Qwen3-4B / the\n"
    "# SFT adapter). The JARVIS PC speaks to it over HTTP; model weights stay on\n"
    "# the GPU host. This key is a SECRET: loaded only through the platform secret\n"
    "# vault (env / .env), never hardcoded, never returned by any /api route, never\n"
    "# written to logs/telemetry/audit, and never sent to the browser. Set it in\n"
    "# your local .env (NEVER commit a real value); in production inject it via\n"
    "# the deployment secret manager / encrypted vault file.\n"
    "JARVIS_BRAIN_ENDPOINT=\n"
    "JARVIS_BRAIN_API_KEY=\n"
    "JARVIS_BRAIN_MODEL=jarvis-brain-qwen3-4b-sft-v1\n"
)

if "JARVIS_BRAIN_API_KEY" not in e:
    e = e.replace(anchor, anchor + brain, 1)

p.write_text(e, encoding="utf-8")
print("patched; has brain:", "JARVIS_BRAIN_API_KEY" in e,
      "lines:", len(e.splitlines()))
