import os, sys
os.environ.setdefault("JARVIS_TEST_MODE", "1")
os.environ.setdefault("JARVIS_ENV", "dev")
ROOT = r"F:\AI\Jarvis-super-intelligence-"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from jarvis_backend.routers import system as s
from jarvis_backend.main import app

print("=== ProviderSettingsIn model_fields (", len(s.ProviderSettingsIn.model_fields), ") ===")
for name in s.ProviderSettingsIn.model_fields:
    f = s.ProviderSettingsIn.model_fields[name]
    print(f"  {name}: required={f.is_required()} annotation={f.annotation}")

print("\n=== System router routes (method path) ===")
for r in s.router.routes:
    if hasattr(r, "methods") and hasattr(r, "path"):
        print(f"  {','.join(sorted(r.methods))}  {r.path}  -> {r.name}")

print("\n=== app.routes matching 'file' or 'system' or 'kill' ===")
for r in app.routes:
    p = getattr(r, "path", None)
    if p and ("file" in p or "system" in p or "kill" in p):
        meth = getattr(r, "methods", None)
        print(f"  {meth} {p}  {getattr(r,'name',None)}")
