import os, sys, asyncio, json

ROOT = r"F:\AI"
sys.path.insert(0, ROOT)

for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ[k.strip()] = v.strip().strip('"').strip("'")

os.environ["SILVERWING_ENDPOINT"] = "http://127.0.0.1:8010"
os.environ["SILVERWING_MODEL"] = "silverwing-120m-base-v1"
os.environ["SILVERWING_TIMEOUT"] = "120"
os.environ["SILVERWING_API_KEY"] = ""

from backend.model_gateway.client import SilverwingClient

async def main():
    sw = SilverwingClient()

    # 1. Health BEFORE chat
    print("=== Health BEFORE chat ===")
    h = await sw.health(refresh=True)
    print(f"  status: {h.status}, healthy: {h.is_healthy}, model: {h.model}, detail: {h.detail}")

    # 2. Models
    print("\n=== Models ===")
    models = await sw.models()
    for m in models:
        print(f"  {m.id}: caps={m.capabilities}, status={m.status}")

    # 3. Chat
    print("\n=== Chat ===")
    try:
        resp = await sw.chat(
            [{"role": "user", "content": "The capital of France is"}],
            max_tokens=8,
            temperature=0.7,
        )
        print(f"  content: {repr(resp.content)}")
        print(f"  model: {resp.model}")
        print(f"  provider: {resp.metadata.get('provider')}")
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")

    # 4. Health AFTER chat
    print("\n=== Health AFTER chat ===")
    h = await sw.health(refresh=True)
    print(f"  status: {h.status}, healthy: {h.is_healthy}, model: {h.model}, detail: {h.detail}")

asyncio.run(main())
