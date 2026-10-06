"""Set JARVIS_ADMIN_EMAIL=ndichiv@gmail.com + empty Brain placeholders in live .env.

Preserves ALL other lines verbatim. Never prints secret values.
"""
from pathlib import Path

p = Path("/AI/.env")
src = p.read_text(encoding="utf-8")
lines = src.splitlines(keepends=True)

admin_email = "ndichiv@gmail.com"
out = []
changed_admin = False
has_brain_endpoint = has_brain_key = has_brain_model = False
for line in lines:
    stripped = line.strip()
    if stripped.startswith("JARVIS_ADMIN_EMAIL="):
        out.append("JARVIS_ADMIN_EMAIL=" + admin_email + "\n")
        changed_admin = True
        continue
    if stripped.startswith("JARVIS_BRAIN_ENDPOINT="):
        has_brain_endpoint = True
    if stripped.startswith("JARVIS_BRAIN_API_KEY="):
        has_brain_key = True
    if stripped.startswith("JARVIS_BRAIN_MODEL="):
        has_brain_model = True
    out.append(line)

if not changed_admin:
    # admin identity line missing entirely -> append a dedicated block
    out.append("\n# JARVIS administrator identity\n")
    out.append("JARVIS_ADMIN_EMAIL=" + admin_email + "\n")

brain_block = (
    "\n# --- Remote JARVIS Brain (spec §5) ---\n"
    "# OpenAI-compatible Brain endpoint. This key is a SECRET: loaded only via\n"
    "# the platform vault (env / .env), never returned by any /api route, never\n"
    "# logged. Set your REAL key here (or inject via env in production).\n"
    "JARVIS_BRAIN_ENDPOINT=\n"
    "JARVIS_BRAIN_API_KEY=\n"
    "JARVIS_BRAIN_MODEL=jarvis-brain-qwen3-4b-sft-v1\n"
)
if not (has_brain_endpoint and has_brain_key and has_brain_model):
    out.append(brain_block)

p.write_text("".join(out), encoding="utf-8")
print("admin_email set:", changed_admin)
print("brain placeholders added:",
      not (has_brain_endpoint and has_brain_key and has_brain_model))
print("total lines now:", len(p.read_text(encoding="utf-8").splitlines()))
