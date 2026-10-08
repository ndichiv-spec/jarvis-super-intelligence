import os, sys, json, urllib.request, urllib.error
os.environ.setdefault("JARVIS_TEST_MODE", "1")
os.environ.setdefault("JARVIS_ENV", "dev")
ROOT = r"F:\AI\Jarvis-super-intelligence-"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from jarvis_backend.routers import system as s
print("=== ReadFileIn / ProcessKillIn fields ===")
print("ReadFileIn:", list(s.ReadFileIn.model_fields.keys()))
print("ProcessKillIn:", list(s.ProcessKillIn.model_fields.keys()))

TOKEN = open(r"F:/AI/_token.txt").read().strip()
BASE = "http://127.0.0.1:8000"

def req(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Accept": "application/json"}
    if body is not None:
        h["Content-Type"] = "application/json"
    h["Authorization"] = f"Bearer {TOKEN}"
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"_raw": raw[:300]}

code, body = req("/api/v1/system/files/read", method="POST", body={"path": "."})
print("\n=== POST /files/read body={\"path\":\".\"} (urllib) ===")
print("HTTP", code)
print(json.dumps(body, indent=2)[:600])

code, fr = req("/api/v1/system/files")
print("\n=== GET /files (first 3 entries) ===")
print("HTTP", code)
print("files count:", len(fr.get("files", [])), "| sample:", json.dumps(fr.get("files", [{}])[0], indent=2)[:200])
