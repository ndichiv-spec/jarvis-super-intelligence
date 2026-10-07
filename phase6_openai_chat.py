import os, sys, requests, json
ROOT = r"F:\AI"
sys.path.insert(0, ROOT)
for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ[k.strip()] = v.strip().strip('"').strip("'")

key = os.environ["OPENAI_API_KEY"]
hdr = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

for model in ["gpt-3.5-turbo", "gpt-4o-mini", "gpt-5-nano"]:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: PONG_OPENAI"}],
        "max_tokens": 20, "temperature": 0.0,
    }
    r = requests.post("https://api.openai.com/v1/chat/completions", headers=hdr, json=body, timeout=30)
    print(f"{model}: HTTP {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        print("  response:", d["choices"][0]["message"]["content"].strip())
        print("  usage:", d.get("usage"))
    else:
        # show the error type
        try:
            err = r.json().get("error", {})
            print("  error type:", err.get("type"), "| code:", err.get("code"), "| message:", err.get("message", "")[:120])
        except Exception:
            print("  body:", r.text[:200])
