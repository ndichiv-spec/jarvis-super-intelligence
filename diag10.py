import os, sys, json, inspect, urllib.request, urllib.error
os.environ.setdefault("JARVIS_TEST_MODE", "1")
os.environ.setdefault("JARVIS_ENV", "dev")
ROOT = r"F:\AI\Jarvis-super-intelligence-"
sys.path.insert(0, ROOT); os.chdir(ROOT)
from jarvis_backend.routers import system as s
print("=== read_file source ===")
print(inspect.getsource(s.read_file))
print("\n=== list_files source (first 20 lines) ===")
print("\n".join(inspect.getsource(s.list_files).splitlines()[:20]))

BASE="http://127.0.0.1:8000"
TOKEN=open(r"F:/AI/_token.txt").read().strip()
def req(path,method="GET",body=None):
    data=json.dumps(body).encode() if body is not None else None
    h={"Accept":"application/json","Authorization":f"Bearer {TOKEN}"}
    if body is not None: h["Content-Type"]="application/json"
    r=urllib.request.Request(BASE+path,data=data,headers=h,method=method)
    try:
        with urllib.request.urlopen(r,timeout=20) as resp: return resp.status,json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw=e.read().decode()
        try: return e.code,json.loads(raw)
        except Exception: return e.code,{"_raw":raw[:300]}

for p in ["jarvis_backend/main.py", "F:/AI/Jarvis-super-intelligence-/README.md", "jarvis_backend/routers/system.py"]:
    code,body = req("/api/v1/system/files/read", method="POST", body={"path": p})
    print(f"\nPOST /files/read path={p!r} -> HTTP {code}")
    if code==200:
        print("  keys:", list(body.keys()), "| content len:", len(body.get("content","")), "| content head:", repr(body.get("content","")[:80]))
    else:
        print("  body:", json.dumps(body)[:300])
