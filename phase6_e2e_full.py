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

# Configure the full chain:
#   JARVIS_BRAIN_ENDPOINT -> local stub Brain on :8011 (honest: stub, not production-healthy)
#   SILVERWING_ENDPOINT   -> local Silverwing runtime on :8010 (real 120M torch backend)
os.environ["JARVIS_BRAIN_ENDPOINT"] = "http://127.0.0.1:8011/v1"
os.environ["JARVIS_BRAIN_MODEL"] = "jarvis-brain-qwen3-4b-v1"
os.environ["JARVIS_BRAIN_API_KEY"] = os.environ.get(
    "JARVIS_BRAIN_API_KEY"
) or os.environ.get("JARVIS_API_KEY")  # already loaded from .env above; never hardcoded here
if not os.environ.get("JARVIS_BRAIN_API_KEY"):
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
    print("=== End-to-end routing test (full chain) ===")
    print("JBRAIN_ENDPOINT:", os.environ.get("JARVIS_BRAIN_ENDPOINT"))
    print("SILVERWING_ENDPOINT:", os.environ.get("SILVERWING_ENDPOINT"))
    print()

    # 1. Brain health probe
    print("--- Brain health probe (via :8011 stub) ---")
    t0 = time.monotonic()
    brain_health = await gw.probe_brain(timeout=10)
    print(json.dumps(brain_health, indent=2, default=str))
    print(f"(probe latency: {round((time.monotonic()-t0)*1000,1)} ms)")
    print()

    # 2. Chat through full ProviderGateway
    # Brain is stub (unavailable) -> gateway falls back to Silverwing runtime (:8010)
    print("--- ProviderGateway.chat() (Brain down -> Silverwing fallback) ---")
    t0 = time.monotonic()
    try:
        result = await gw.chat(
            [{"role": "user", "content": "The capital of France is"}],
            timeout=60,
        )
        print(json.dumps(result, indent=2, default=str))
    except ChatError as exc:
        print("ChatError:", exc.category, str(exc)[:200])
        print("retryable:", getattr(exc, "retryable", None))
    lat = round((time.monotonic() - t0) * 1000, 1)
    print(f"(total latency: {lat} ms)")
    print()

    # 3. Also test Google directly through the fabric (since OpenAI has no credits)
    print("--- Direct provider smoke: Google (via fabric) ---")
    from providers.bootstrap import build_adapters
    from providers.base import ProviderRequest
    adapters = build_adapters()
    g = adapters.get("google")
    if g and g.configured:
        req = ProviderRequest(
            messages=[{"role": "user", "content": "Reply with exactly: PONG_GOOGLE"}],
            model="gemini-2.5-flash", max_tokens=20, temperature=0.0,
        )
        t0 = time.monotonic()
        r = g.chat(req)
        print("response:", r.text.strip())
        print("model:", r.model)
        print("latency_ms:", round(r.latency_ms or (time.monotonic()-t0)*1000, 1))
        u = r.usage
        print("usage:", {"prompt": u.prompt_tokens, "completion": u.completion_tokens} if u else None)
    print()

asyncio.run(main())
