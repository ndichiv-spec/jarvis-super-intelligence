import os, sys, time, json, asyncio

ROOT = r"F:\AI"
sys.path.insert(0, ROOT)
PLATFORM = r"F:\AI\Jarvis-super-intelligence-"
sys.path.insert(0, PLATFORM)

for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ[k.strip()] = v.strip().strip('"').strip("'")

os.environ["JARVIS_BRAIN_ENDPOINT"] = "http://127.0.0.1:8011/v1"
os.environ["JARVIS_BRAIN_MODEL"] = "jarvis-brain-qwen3-4b-v1"
if not os.environ.get("JARVIS_BRAIN_API_KEY"):
    # Loaded from .env above; never hardcode the value.
    raise SystemExit(
        "JARVIS_BRAIN_API_KEY is not set. Add it to .env or export it before running."
    )
os.environ["SILVERWING_ENDPOINT"] = "http://127.0.0.1:8010"
os.environ["SILVERWING_MODEL"] = "silverwing-120m-base-v1"
os.environ["SILVERWING_TIMEOUT"] = "300"

from jarvis_backend.gateway import ProviderGateway
from jarvis_backend.errors import ChatError

gw = ProviderGateway()

async def main():
    print("=== End-to-end routing test (Brain :8011 -> Silverwing :8010) ===")
    print("JBRAIN_ENDPOINT:", os.environ["JARVIS_BRAIN_ENDPOINT"])
    print("SILVERWING_ENDPOINT:", os.environ["SILVERWING_ENDPOINT"])
    print()

    # 1. Brain health probe
    print("--- Brain health probe (stub on :8011) ---")
    t0 = time.monotonic()
    brain_health = await gw.probe_brain(timeout=10)
    print(json.dumps(brain_health, indent=2, default=str))
    print(f"(probe latency: {round((time.monotonic()-t0)*1000,1)} ms)")
    print()

    # 2. Full chat: Brain is stub (unavailable) -> falls back to Silverwing runtime
    print("--- ProviderGateway.chat() (Brain stub -> Silverwing fallback) ---")
    t0 = time.monotonic()
    try:
        result = await gw.chat(
            [{"role": "user", "content": "The capital of France is"}],
            timeout=60,
        )
        print(json.dumps(result, indent=2, default=str))
    except ChatError as exc:
        print("ChatError:", exc.category, str(exc)[:300])
        print("retryable:", getattr(exc, "retryable", None))
    lat = round((time.monotonic() - t0) * 1000, 1)
    print(f"(total latency: {lat} ms)")

asyncio.run(main())
