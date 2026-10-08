import os, sys, time, json

ROOT = r"F:\AI"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# load .env into process env
for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ[k.strip()] = v.strip().strip('"').strip("'")

from providers.bootstrap import build_adapters
from providers.base import ProviderRequest

adapters = build_adapters()

def probe_openai():
    a = adapters.get("openai")
    if not a or not a.configured:
        return {"provider": "openai", "configured": False, "result": "NOT CONFIGURED"}
    out = {
        "provider": "openai",
        "configured": True,
        "api_key_present": bool(a.api_key),
        "default_model": (a.default_model or "gpt-4o-mini"),
    }
    # health
    t0 = time.monotonic()
    try:
        h = a.health()
        out["health_status"] = h.status.value
        out["health_detail"] = h.detail
        out["models_found"] = getattr(h, "models_found", None)
    except Exception as e:
        out["health_error"] = f"{type(e).__name__}: {e}"
    out["health_latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    # chat
    t0 = time.monotonic()
    try:
        req = ProviderRequest(
            messages=[{"role": "user", "content": "Reply with exactly: PONG_OPENAI"}],
            model="gpt-4o-mini",
            max_tokens=20, temperature=0.0,
        )
        r = a.chat(req)
        out["chat_status"] = "success"
        out["response"] = r.text.strip()
        out["model"] = r.model
        out["latency_ms"] = round(r.latency_ms or (time.monotonic() - t0) * 1000, 1)
        u = r.usage
        out["usage"] = {"prompt": u.prompt_tokens, "completion": u.completion_tokens} if u else None
    except Exception as e:
        out["chat_status"] = "error"
        out["chat_error"] = f"{type(e).__name__}: {str(e)[:300]}"
        out["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    return out


def probe_google():
    a = adapters.get("google")
    if not a or not a.configured:
        return {"provider": "google", "configured": False, "result": "NOT CONFIGURED"}
    out = {"provider": "google", "configured": True}
    t0 = time.monotonic()
    try:
        h = a.health()
        out["health_status"] = h.status.value
        out["health_detail"] = h.detail
    except Exception as e:
        out["health_error"] = f"{type(e).__name__}: {e}"
    out["health_latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    t0 = time.monotonic()
    try:
        req = ProviderRequest(
            messages=[{"role": "user", "content": "Reply with exactly: PONG_GOOGLE"}],
            model="gemini-2.5-flash",
            max_tokens=20, temperature=0.0,
        )
        r = a.chat(req)
        out["chat_status"] = "success"
        out["response"] = r.text.strip()
        out["model"] = r.model
        out["latency_ms"] = round(r.latency_ms or (time.monotonic() - t0) * 1000, 1)
        u = r.usage
        out["usage"] = {"prompt": u.prompt_tokens, "completion": u.completion_tokens} if u else None
    except Exception as e:
        out["chat_status"] = "error"
        out["chat_error"] = f"{type(e).__name__}: {str(e)[:300]}"
        out["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    return out


def probe_nvidia():
    a = adapters.get("nvidia")
    if not a or not a.configured:
        return {"provider": "nvidia", "configured": False, "result": "NOT CONFIGURED"}
    out = {"provider": "nvidia", "configured": True}
    try:
        h = a.health()
        out["health_status"] = h.status.value
    except Exception as e:
        out["health_error"] = f"{type(e).__name__}: {e}"
    return out


def probe_aws():
    a = adapters.get("aws")
    if not a or not a.configured:
        return {"provider": "aws", "configured": False, "result": "NOT CONFIGURED"}
    out = {"provider": "aws", "configured": True}
    try:
        h = a.health()
        out["health_status"] = h.status.value
    except Exception as e:
        out["health_error"] = f"{type(e).__name__}: {e}"
    return out


def probe_hf():
    a = adapters.get("hf")
    out = {"provider": "hf", "configured": bool(a and a.configured), "inference_ready": bool(a and a.inference_ready)}
    if not a or not a.configured:
        return out
    t0 = time.monotonic()
    try:
        h = a.health()
        out["health_status"] = h.status.value
        out["health_detail"] = h.detail
    except Exception as e:
        out["health_error"] = f"{type(e).__name__}: {e}"
    out["health_latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    # repository access (list models the user owns)
    t0 = time.monotonic()
    try:
        models = a.list_models_remote()
        out["repo_models"] = models[:10]
        out["repo_model_count"] = len(models)
    except Exception as e:
        out["repo_error"] = f"{type(e).__name__}: {str(e)[:200]}"
    out["repo_latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    return out


def probe_brain():
    ep = os.environ.get("JARVIS_BRAIN_ENDPOINT")
    key = os.environ.get("JARVIS_BRAIN_API_KEY")
    out = {"provider": "jarvis_brain", "endpoint": ep, "api_key_present": bool(key)}
    if not ep:
        out["result"] = "NOT CONFIGURED"
        return out
    import requests
    base = ep.rstrip("/")
    if not base.endswith("/v1"):
        base_full = base + "/v1"
    else:
        base_full = base
    if not base.endswith("/v1"):
        base_full = base.rstrip("/") + "/v1"
    # strip trailing /v1 from ep if double
    base_full = ep.rstrip("/")
    if base_full.endswith("/v1"):
        base_full = base_full[:-3].rstrip("/")
    base_full = base_full.rstrip("/")
    hdr = {"Authorization": f"Bearer {key}"} if key else {}
    t0 = time.monotonic()
    try:
        r = requests.get(f"{base_full}/health", timeout=10)
        out["health_status_code"] = r.status_code
        out["health_body"] = r.json() if r.headers.get("content-type","").startswith("application/json") else r.text[:200]
    except Exception as e:
        out["health_error"] = f"{type(e).__name__}: {str(e)[:200]}"
    out["health_latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    return out


results = {}
for name, fn in [("openai", probe_openai), ("google", probe_google),
                 ("nvidia", probe_nvidia), ("aws", probe_aws), ("hf", probe_hf),
                 ("brain", probe_brain)]:
    print(f"=== {name.upper()} ===")
    r = fn()
    results[name] = r
    print(json.dumps(r, indent=2, default=str))
    print()

with open(os.path.join(ROOT, "phase6_provider_smoke2.json"), "w") as f:
    json.dump(results, f, indent=2, default=str)
print("Saved => F:\\AI\\phase6_provider_smoke2.json")
