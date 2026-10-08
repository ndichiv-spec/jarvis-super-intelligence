"""Live contract assertion: /api/v1/system/* vs frontend/.../system/types.ts

Run AFTER `python3 F:/AI/start_jarvis.py` is live on 127.0.0.1:8000.
Uses urllib (stdlib) over real HTTP. The admin bearer token is read from
F:/AI/_token.txt and is NEVER printed. Spawns a throwaway `ping` process so
the kill endpoint can be exercised on a safe PID.

Asserts every REQUIRED field from types.ts is present with the correct type,
and that secret-shaped provider keys are NOT leaked (SEC-1).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
TOKEN_PATH = r"F:/AI/_token.txt"
ENV = {"JARVIS_TEST_MODE": "1", "JARVIS_ENV": "dev"}
os.environ.update(ENV)

PASS = 0
FAIL = 0


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}  {detail}")


def tok():
    with open(TOKEN_PATH) as fh:
        return fh.read().strip()


def req(path, method="GET", body=None, token=None):
    url = BASE + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}, dict(resp.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"_raw": raw[:200]}
        return e.code, parsed, dict(e.headers)


def main():
    t = tok()
    check("token file non-empty", len(t) > 0, f"len={len(t)}")

    print("\n--- GET /api/v1/system/status (public) ---")
    code, j, _ = req("/api/v1/system/status")
    check("status HTTP 200", code == 200, f"got {code}")
    for k in ["status", "version", "uptime", "start_time", "active_engines",
              "active_connections", "memory_usage", "cpu_usage"]:
        check(f"status.{k} present", k in j, f"missing; keys={list(j.keys())}")
    check("status.version == 3.1.0", j.get("version") == "3.1.0", str(j.get("version")))
    check("status.uptime is float", isinstance(j.get("uptime"), (int, float)))
    check("status.memory_usage is int (>0 real)", isinstance(j.get("memory_usage"), int) and j.get("memory_usage", 0) > 0)
    check("status.cpu_usage == 0.0", j.get("cpu_usage") == 0.0, str(j.get("cpu_usage")))
    check("status.start_time ends with Z", str(j.get("start_time", "")).endswith("Z"))
    check("status.active_engines non-empty list", isinstance(j.get("active_engines"), list) and len(j.get("active_engines")) > 0)

    print("\n--- GET /api/v1/system/capabilities (public) ---")
    code, j, _ = req("/api/v1/system/capabilities")
    check("capabilities HTTP 200", code == 200, f"got {code}")
    for k in ["version", "engines", "features", "tier_level"]:
        check(f"capabilities.{k} present", k in j, f"missing; keys={list(j.keys())}")
    check("capabilities.version == 3.1.0", j.get("version") == "3.1.0", str(j.get("version")))
    check("capabilities.tier_level == 3", j.get("tier_level") == 3, str(j.get("tier_level")))
    check("capabilities.engines list[str]", isinstance(j.get("engines"), list) and all(isinstance(x, str) for x in j.get("engines", [])))
    check("capabilities.features list[str]", isinstance(j.get("features"), list) and all(isinstance(x, str) for x in j.get("features", [])))

    print("\n--- GET /api/v1/system/processes (auth) ---")
    code, j, _ = req("/api/v1/system/processes", token=t)
    check("processes HTTP 200", code == 200, f"got {code}")
    check("processes.processes is list", isinstance(j.get("processes"), list))
    check("processes.total is int", isinstance(j.get("total"), int))
    if j.get("processes"):
        p0 = j["processes"][0]
        for k in ["pid", "name", "cpu_percent", "memory_percent", "status", "created_at"]:
            check(f"process[].{k} present", k in p0, f"missing; keys={list(p0.keys())}")

    print("\n--- GET /api/v1/system/files (auth) ---")
    code, j, _ = req("/api/v1/system/files", token=t)
    check("files HTTP 200", code == 200, f"got {code}")
    check("files.path present", "path" in j)
    check("files.files is list", isinstance(j.get("files"), list))
    if j.get("files"):
        f0 = j["files"][0]
        for k in ["name", "path", "size", "type", "modified_at", "is_directory"]:
            check(f"file[].{k} present", k in f0, f"missing; keys={list(f0.keys())}")
        check("file[].type valid", f0.get("type") in ("directory", "file", "directory", "file"))
        check("file[].is_directory is bool", isinstance(f0.get("is_directory"), bool))
        check("file[].size is int", isinstance(f0.get("size"), int))

    print("\n--- POST /api/v1/system/files/read (auth) ---")
    code, j, _ = req("/api/v1/system/files/read", method="POST", body={"path": "jarvis_backend/main.py"}, token=t)
    check("files/read HTTP 200", code == 200, f"got {code}")
    check("files_read.path present", "path" in j)
    check("files_read.content is str", isinstance(j.get("content"), str), f"type={type(j.get('content')).__name__}")

    print("\n--- GET /api/v1/system/provider-settings (admin) ---")
    code, j, _ = req("/api/v1/system/provider-settings", token=t)
    check("provider-settings HTTP 200", code == 200, f"got {code}")
    check("ps.success == True", j.get("success") is True)
    check("ps.settings present", isinstance(j.get("settings"), dict))
    expected_settings = ["ollama_base_url", "ollama_model", "openai_api_key", "google_gemini_api_key",
                         "anthropic_api_key", "huggingface_api_key", "stability_api_key",
                         "replicate_api_key", "aws_access_key_id", "aws_secret_access_key",
                         "aws_region", "tavily_api_key", "serper_api_key", "news_api_key",
                         "openweathermap_api_key"]
    for k in expected_settings:
        check(f"settings.{k} present", k in j.get("settings", {}), f"missing; keys={list(j.get('settings',{}).keys())}")
    # SEC-1: every secret-shaped field (per _SECRET_SHAPES) must be scrubbed to None
    _secret_shapes = ("key", "secret", "token", "password", "credential", "private_key")
    leaked = [k for k in j.get("settings", {}) if any(s in k for s in _secret_shapes) and j["settings"][k] is not None]
    check("SEC-1 secrets scrubbed to None", not leaked, f"LEAKED: {leaked}")
    check("ps.providers present", isinstance(j.get("providers"), dict))
    check("ps.providers.openai.configured present", j.get("providers", {}).get("openai", {}).get("configured") is not None)
    check("ps.env_file_exists is bool", isinstance(j.get("env_file_exists"), bool))
    check("ps.env_path present", "env_path" in j)
    # 12 provider keys
    check("ps.providers has 12 entries", len(j.get("providers", {})) == 12, f"got {len(j.get('providers', {}))}")

    print("\n--- POST /api/v1/system/processes/kill (admin, safe pid) ---")
    # Spawn a throwaway ping to get a safe PID
    proc = subprocess.Popen(["ping", "-n", "60", "127.0.0.1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pid = proc.pid
    time.sleep(1)
    code, j, _ = req("/api/v1/system/processes/kill", method="POST", body={"pid": pid, "force": True}, token=t)
    check("processes/kill HTTP 200", code == 200, f"got {code}; body={j}")
    check("kill.success == True", j.get("success") is True, str(j))
    check("kill.pid matches", j.get("pid") == pid, str(j))
    try:
        proc.wait(timeout=3)
    except Exception:
        proc.kill()
    # cleanup just in case
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
    except Exception:
        pass

    print(f"\n================ CONTRACT RESULT ================")
    print(f"  PASS={PASS}  FAIL={FAIL}")
    print("  (all responses fetched over live HTTP from 127.0.0.1:8000)")
    print("================================================")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
