import os, sys, time, json, requests

ROOT = r"F:\AI"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)
for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ[k.strip()] = v.strip().strip('"').strip("'")

# Google re-test with cleaner prompt
key = os.environ["GOOGLE_API_KEY"]
model = "gemini-2.5-flash"
t0 = time.monotonic()
url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
body = {"contents": [{"role": "user", "parts": [{"text": "What is 2+2? Please give a one-word answer."}]}]}
r = requests.post(url, json=body, timeout=90)
lat = round((time.monotonic() - t0) * 1000, 1)
if r.status_code == 200:
    d = r.json()
    txt = ""
    for c in d.get("candidates", []):
        for p in c.get("content", {}).get("parts", []):
            txt += p.get("text", "")
    u = d.get("usageMetadata", {})
    print("GOOGLE chat OK")
    print("response:", txt.strip())
    print("model:", model)
    print("latency_ms:", lat)
    print("usage:", {"prompt": u.get("promptTokenCount"), "candidates": u.get("candidatesTokenCount"), "total": u.get("totalTokenCount")})
else:
    print("GOOGLE chat FAILED:", r.status_code, r.text[:300])
