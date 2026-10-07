import os, sys, requests
ROOT = r"F:\AI"
sys.path.insert(0, ROOT)
for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ[k.strip()] = v.strip().strip('"').strip("'")

key = os.environ["OPENAI_API_KEY"]
r = requests.get("https://api.openai.com/v1/models",
                 headers={"Authorization": f"Bearer {key}"}, timeout=30)
print("status:", r.status_code)
if r.status_code == 200:
    d = r.json()
    ids = [m["id"] for m in d.get("data", [])]
    print("count:", len(ids))
    print("all:", ids)
else:
    print("body:", r.text[:400])
