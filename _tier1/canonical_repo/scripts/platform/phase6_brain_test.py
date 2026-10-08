import os, sys, time, json

ROOT = r"F:\AI"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

# load .env
for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ[k.strip()] = v.strip().strip('"').strip("'")

from brain_runtime.config import BrainConfig
from brain_runtime.service import BrainService
from brain_runtime.model_registry import BrainCatalog
from brain_runtime.generation import BrainGenerationConfig

# Build config in REMOTE mode pointing to Google OpenAI-compatible endpoint.
# This never downloads weights locally (spec section 5).
cfg = BrainConfig(
    host="127.0.0.1",
    port=8011,
    api_key=os.environ.get("JARVIS_BRAIN_API_KEY", ""),
    model=os.environ.get("JARVIS_BRAIN_MODEL", "jarvis-brain-qwen3-4b-v1"),
    backend="remote",          # <-- remote: forwards to JARVIS_BRAIN_REMOTE_ENDPOINT
    device="auto",
    remote_endpoint="https://generativelanguage.googleapis.com/v1beta",
    remote_api_key=os.environ.get("GOOGLE_API_KEY", ""),
    remote_timeout=120.0,
    remote_model="gemini-2.5-flash",
    request_timeout=120.0,
)
print("BrainConfig:")
print("  backend_type:", cfg.backend_type)
print("  is_remote:", cfg.is_remote)
print("  remote_endpoint:", cfg.remote_endpoint)
print("  model:", cfg.model)
print("  api_key_present:", bool(cfg.api_key))
print("  remote_api_key_present:", bool(cfg.remote_api_key))

cat = BrainCatalog(cfg.model_repo)
svc = BrainService(config=cfg, catalog=cat)

print("\n=== Preparing BrainService (remote backend, no local download) ===")
t0 = time.monotonic()
ok = svc.prepare()
print("prepare() =>", ok, " (took", round((time.monotonic()-t0)*1000, 1), "ms)")

st = svc.health.current()
print("health:", st.status, "available=", st.available, "production_health=", st.production_health)
print("backend:", st.backend, "device:", st.device, "revision:", st.revision)
print("model_info:", svc.model_info())

if ok:
    print("\n=== Real inference via remote Brain ===")
    t0 = time.monotonic()
    result = svc.chat(
        [{"role": "user", "content": "Reply with exactly: PONG_BRAIN"}],
        BrainGenerationConfig(model="jarvis-brain-qwen3-4b-v1", max_tokens=20, temperature=0.0),
    )
    lat = round((time.monotonic() - t0) * 1000, 1)
    print("response:", result.text.strip())
    print("model:", result.model)
    print("revision:", result.revision)
    print("backend:", result.backend)
    print("device:", result.device)
    print("tokens_input:", result.tokens_input, "tokens_generated:", result.tokens_generated)
    print("latency_ms:", lat)

svc.shutdown()
print("\nBrainService shut down cleanly.")
