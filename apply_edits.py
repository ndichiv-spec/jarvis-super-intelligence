import re, sys

sp = r"F:\AI\Jarvis-super-intelligence-\jarvis_backend/routers/system.py"
content = open(sp, encoding="utf-8").read()
lines = content.split("\n")

def find_line(lines, needle, after=0):
    for i in range(after, len(lines)):
        if needle in lines[i]:
            return i
    return -1

def find_end(lines, after):
    """Next top-level (@router / class / def at col 0) token after `after`."""
    for j in range(after + 1, len(lines)):
        line = lines[j]
        if line.startswith("@router") or line.startswith("class ") or line.startswith("def "):
            return j
    return len(lines)

def splice_route(lines, anchor, new_text, sanity):
    start = find_line(lines, anchor, 0)
    assert start >= 0, f"anchor not found: {anchor}"
    end = find_end(lines, start)
    old_block = lines[start:end]
    # join old block to string, assert the sanity substring is present (confirm we grabbed the right region)
    old_str = "\n".join(old_block)
    assert sanity in old_str, f"sanity '{sanity}' not in region [{start}:{end}]"
    new_lines = new_text.split("\n")
    # strip trailing blanks from new text, then add PEP8 2 blanks
    while new_lines and new_lines[-1] == "":
        new_lines.pop()
    new_lines += ["", ""]
    lines[start:end] = new_lines
    return start, end

# ---- NEW /processes (frontend SystemProcess: pid,name,cpu_percent,memory_percent,status,created_at,username?) ----
new_processes = '''@router.get("/processes")
async def list_processes(user: Dict[str, Any] = Depends(_require_auth),
                         limit: int = Query(50), sort: str = Query("cpu")):
    """List running processes. Requires authentication."""
    _audit_system_action("read", "list_processes", "system/processes",
                         user.get("email", ""))
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent", "status", "create_time", "username"]
        ):
            try:
                info = p.info
                ct = info.get("create_time")
                procs.append({
                    "pid": info.get("pid"),
                    "name": info.get("name") or "unknown",
                    "cpu_percent": round(info.get("cpu_percent") or 0, 1),
                    "memory_percent": round(info.get("memory_percent") or 0, 1),
                    "status": info.get("status"),
                    "created_at": _utc_iso(ct) if ct is not None else None,
                    "username": info.get("username"),
                })
            except Exception:  # noqa: BLE001
                continue
        key = {"cpu": lambda x: x["cpu_percent"], "memory": lambda x: x["memory_percent"],
               "name": lambda x: x["name"]}.get(sort, lambda x: x["cpu_percent"])
        procs.sort(key=key, reverse=(sort != "name"))
        return {"processes": procs[:limit], "total": len(procs)}
    except Exception:  # noqa: BLE001
        logger.exception("system:list_processes failed")
        return {"processes": [], "total": 0, "error": "process enumeration unavailable"}'''

# ---- NEW /files (frontend FileInfo: name,path,size,type,modified_at,is_directory; api.ts expects {files:[...]}) ----
new_files = '''@router.get("/files")
async def list_files(user: Dict[str, Any] = Depends(_require_auth),
                     path: str = Query(str(ROOT))):
    """List files in a directory. Requires authentication."""
    _audit_system_action("read", "list_files", f"system/files/{path}",
                         user.get("email", ""))
    try:
        p = _confined_path(path)
        if not p.exists():
            raise HTTPException(status_code=404, detail="Path not found")
        entries = []
        for child in sorted(p.iterdir()):
            try:
                st = child.stat()
                is_dir = child.is_dir()
                entries.append({
                    "name": child.name,
                    "path": str(child),
                    "size": st.st_size,
                    "type": "directory" if is_dir else "file",
                    "modified_at": _utc_iso(st.st_mtime),
                    "is_directory": is_dir,
                })
            except Exception:  # noqa: BLE001
                continue
        return {"path": str(p), "files": entries, "entries": entries}
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("system handler failed")
        raise HTTPException(status_code=400, detail="Request failed")'''

s1, e1 = splice_route(lines, '@router.get("/processes")', new_processes, '"cpu": round(info.get("cpu_percent")')
s2, e2 = splice_route(lines, '@router.get("/files")', new_files, '"is_dir": child.is_dir()')

content = "\n".join(lines)
open(sp, "w", encoding="utf-8").write(content)
print(f"processes region was lines [{s1+1}:{e1}] -> replaced")
print(f"files region was lines [{s2+1}:{e2}] -> replaced")
print("SYS_TOTAL", len(lines))

# Sanity: confirm new strings present + old leaky names gone
checks = {
    '"cpu_percent": round': new_processes.count('"cpu_percent": round'),
    '"is_directory": is_dir': new_files.count('"is_directory": is_dir'),
    'files: entries': new_files.count('"files": entries'),
    'no old "cpu": round': 0,
}
txt = content
print("cpu_percent count:", txt.count('"cpu_percent":'))
print("is_directory count:", txt.count('"is_directory":'))
print("files keys count:", txt.count('"files": entries'))
# ensure old leaky field names are gone from /processes
print("old 'cpu': round present?:", '"cpu": round(info.get("cpu_percent")' in txt)
print("old is_dir present?:", '"is_dir": child.is_dir()' in txt)
