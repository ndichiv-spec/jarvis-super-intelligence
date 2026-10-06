from pathlib import Path

c = Path("jarvis_backend/routers/auth.py").read_text(encoding="utf-8").splitlines()
print("=== auth.py: api-key routes + imports ===")
for i, l in enumerate(c, 1):
    if ("def _require_admin" in l or "/api-keys" in l or
            "def create_api_key" in l or "def list_api_keys" in l or
            "def delete_api_key" in l or "def rotate_api_key" in l):
        print(f"{i:4d}: {l}")
print("--- import block (12-28) ---")
for i in range(12, 29):
    print(f"{i:4d}: {c[i-1]}")

print("=== core.py: API-key helpers (grep names) ===")
cc = Path("jarvis_backend/core.py").read_text(encoding="utf-8").splitlines()
for i, l in enumerate(cc, 1):
    if any(k in l for k in ["API_KEY_PREFIX", "def generate_api_key", "def hash_api_key",
                            "def verify_api_key", "def api_key_prefix", "def _api_key_principal",
                            "def find_api_key", "def _strip_key_secrets", "def _audit_api_key",
                            "token.startswith(API_KEY_PREFIX)", "def get_current_user"]):
        print(f"{i:4d}: {l}")
