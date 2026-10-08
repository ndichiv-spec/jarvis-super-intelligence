import os, sys, asyncio, traceback

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

os.environ["SILVERWING_ENDPOINT"] = "http://127.0.0.1:8010"
os.environ["SILVERWING_MODEL"] = "silverwing-120m-base-v1"
os.environ["SILVERWING_TIMEOUT"] = "120"
os.environ["SILVERWING_API_KEY"] = ""  # no auth

from backend.model_gateway.client import SilverwingClient

async def main():
    sw = SilverwingClient()
    print("SilverwingClient config:")
    print("  endpoint:", sw.endpoint)
    print("  model:", sw.model)
    print("  api_key:", repr(sw.api_key))
    print("  is_remote:", sw.is_remote)
    print("  timeout:", sw.timeout)
    print()

    # Direct health check
    print("--- Health ---")
    h = await sw.health(refresh=True)
    print(f"  status: {h.status}, is_healthy: {h.is_healthy}")
    print(f"  model: {h.model}, warmup_ok: {h.warmup_ok}")
    print()

    # Direct chat via SilverwingClient
    print("--- SilverwingClient.chat() ---")
    try:
        resp = await sw.chat(
            [{"role": "user", "content": "The capital of France is"}],
            max_tokens=8,
            temperature=0.7,
        )
        print("  content:", repr(resp.content))
        print("  model:", resp.model)
        print("  provider:", resp.metadata.get("provider"))
        print("  latency_ms:", resp.latency_ms)
        print("  usage:", resp.usage)
    except Exception:
        traceback.print_exc()

asyncio.run(main())
