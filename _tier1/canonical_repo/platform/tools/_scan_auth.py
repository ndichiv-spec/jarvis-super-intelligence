import re
from pathlib import Path

root = Path("jarvis_backend")
pat = re.compile(r"get_current_user|is_admin|require_admin|user\[.roles.\]")
for f in root.rglob("*.py"):
    t = f.read_text(encoding="utf-8", errors="replace")
    for i, l in enumerate(t.splitlines(), 1):
        if pat.search(l):
            print(f"{f}:{i}: {l.strip()}")
