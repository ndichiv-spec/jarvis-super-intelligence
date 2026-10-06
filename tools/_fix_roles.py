from pathlib import Path

p = Path("jarvis_backend/core.py")
c = p.read_text(encoding="utf-8")
old = '    principal.setdefault("roles", [])\n    principal["is_admin"] = "admin" in (key_record.get("scopes") or [])\n'
new = '    principal["roles"] = []  # keys derive authority from scopes, not owner roles\n    principal["is_admin"] = "admin" in (key_record.get("scopes") or [])\n'
assert c.count(old) == 1, f"roles line count={c.count(old)}"
c = c.replace(old, new)
p.write_text(c, encoding="utf-8")
print("roles-forcing fix applied")
