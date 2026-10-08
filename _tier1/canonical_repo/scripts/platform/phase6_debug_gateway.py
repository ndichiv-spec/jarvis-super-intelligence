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
os.environ["SILVERWING_TIMEOUT"] = "300"

from backend.model_gateway.routing import ModelGateway
from backend.model_gateway.client import SilverwingClient

async def main():
    mg = ModelGateway()
    # Check SilverwingClient health
    sw = SilverwingClient()
    print("SilverwingClient:")
    print("  endpoint:", sw.endpoint)
    print("  model:", sw.model)
    print("  is_remote:", sw.is_remote)
    print("  timeout:", sw.timeout)
    print()
    print("Probing Silverwing health (refresh=True)...")
    h = await sw.health(refresh=True)
    print("  health:", h)
    print("  is_healthy:", h.is_healthy)
    print()
    # List models from runtime
    print("Listing models from runtime...")
    try:
        models = await sw.models()
        for m in models:
            print("  model:", m)
    except Exception as e:
        print("  models ERROR:", type(e).__name__, str(e)[:200])
    print()
    # Now try chat
    print("Trying ModelGateway.chat()...")
    try:
        resp, dec = await asyncio.wait_for(
            mg.chat([{"role": "user", "content": "The capital of France is"}], task="chat", timeout=60),
            timeout=90,
        )
        print("SUCCESS:")
        print("  content:", resp.content)
        print("  model:", resp.model)
        print("  provider:", resp.metadata.get("provider"))
        print("  revision:", resp.revision)
        print("  latency_ms:", resp.latency_ms)
        print("  usage:", resp.usage)
    except Exception:
        traceback.print_exc()

asyncio.run(main())
