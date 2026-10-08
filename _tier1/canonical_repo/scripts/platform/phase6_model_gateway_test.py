import os, sys, asyncio, traceback

ROOT = r"F:\AI"
sys.path.insert(0, ROOT)
PLAT = r"F:\AI\Jarvis-super-intelligence-"
sys.path.insert(0, PLAT)

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

async def run():
    mg = ModelGateway()
    try:
        resp, dec = await asyncio.wait_for(
            mg.chat([{"role": "user", "content": "capital of France is"}], task="chat", timeout=60),
            timeout=90,
        )
        print("ModelGateway result:")
        print("  content:", resp.content)
        print("  model:", resp.model)
        print("  provider:", resp.metadata.get("provider"))
        print("  revision:", resp.revision)
        print("  backend:", resp.metadata.get("backend"))
        print("  device:", resp.metadata.get("device"))
        print("  latency_ms:", resp.latency_ms)
        print("  usage:", resp.usage)
    except Exception as e:
        print("ModelGateway ERROR:")
        traceback.print_exc()

asyncio.run(run())
