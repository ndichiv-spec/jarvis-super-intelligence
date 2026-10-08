import os, sys, time, json, asyncio

ROOT = r"F:\AI"
sys.path.insert(0, ROOT)
# platform repo
PLATFORM = r"F:\AI\Jarvis-super-intelligence-"
sys.path.insert(0, PLATFORM)

# load .env
for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ[k.strip()] = v.strip().strip('"').strip("'")

# Ensure the Brain endpoint points to our local stub runtime
os.environ["JARVIS_BRAIN_ENDPOINT"] = "http://127.0.0.1:8011/v1"
os.environ["JARVIS_BRAIN_MODEL"] = "jarvis-brain-qwen3-4b-v1"
if not os.environ.get("JARVIS_BRAIN_API_KEY"):
    # Loaded from .env above; never hardcode the value.
    raise SystemExit(
        "JARVIS_BRAIN_API_KEY is not set. Add it to .env or export it before running."
    )

from jarvis_backend.gateway import ProviderGateway
from jarvis_backend.errors import ChatError

gw = ProviderGateway()

async def main():
    print("=== End-to-end routing test ===")
    print("JARVIS_BRAIN_ENDPOINT:", os.environ.get("JARVIS_BRAIN_ENDPOINT"))
    print("SILVERWING_ENDPOINT:", os.environ.get("SILVERWING_ENDPOINT", "<unset>"))
    print()

    # 1. Brain health probe (real)
    print("--- Brain health probe ---")
    t0 = time.monotonic()
    try:
        brain_health = await gw.probe_brain(timeout=10)
        print(json.dumps(brain_health, indent=2, default=str))
    except Exception as e:
        print("probe_brain error:", type(e).__name__, str(e)[:200])
    print(f"(probe latency: {round((time.monotonic()-t0)*1000,1)} ms)")
    print()

    # 2. Full chat through ProviderGateway (Brain primary -> fallback chain)
    print("--- ProviderGateway.chat() ---")
    t0 = time.monotonic()
    try:
        result = await gw.chat(
            [{"role": "user", "content": "What is 2+2? One word."}],
            timeout=15,
        )
        print(json.dumps(result, indent=2, default=str))
    except ChatError as exc:
        print("ChatError:", exc.category, exc.message if hasattr(exc, "message") else str(exc))
        print("retryable:", getattr(exc, "retryable", None))
        print("detail:", getattr(exc, "detail", None))
    except Exception as exc:
        print("ERROR:", type(exc).__name__, str(exc)[:300])
    lat = round((time.monotonic() - t0) * 1000, 1)
    print(f"(total latency: {lat} ms)")
    print()

asyncio.run(main())
