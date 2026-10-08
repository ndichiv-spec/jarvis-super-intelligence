import os, sys, time, json, traceback

ROOT = r"F:\AI"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# load .env
for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ[k.strip()] = v.strip().strip('"').strip("'")

results = {}

# ---------- raw probes ----------
import requests


def raw_openai():
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return {"provider": "openai", "note": "OPENAI_API_KEY not set", "configured": False}
    base = "https://api.openai.com/v1"
    hdr = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    out = {"provider": "openai", "configured": True, "key_prefix": key[:12] + "***"}
    t0 = time.monotonic()
    try:
        r = requests.get(base + "/models", headers=hdr, timeout=30)
        out["models_status"] = r.status_code
        if r.status_code == 200:
            data = r.json()
            ids = [m.get("id") for m in data.get("data", [])]
            out["models_found"] = len(ids)
            out["models_sample"] = ids[:6]
        else:
            out["models_body"] = r.text[:200]
    except Exception as e:
        out["models_error"] = f"{type(e).__name__}: {e}"
    out["models_latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    # chat
    t0 = time.monotonic()
    try:
        body = {"model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Reply with exactly: PONG_OPENAI"}],
                "max_tokens": 20, "temperature": 0.0}
        r = requests.post(base + "/chat/completions", headers=hdr, json=body, timeout=30)
        out["chat_status"] = r.status_code
        if r.status_code == 200:
            d = r.json()
            out["chat_response"] = d["choices"][0]["message"]["content"].strip()
            out["chat_model"] = d.get("model")
            u = d.get("usage", {})
            out["chat_usage"] = {"prompt": u.get("prompt_tokens"), "completion": u.get("completion_tokens")}
        else:
            out["chat_body"] = r.text[:200]
    except Exception as e:
        out["chat_error"] = f"{type(e).__name__}: {e}"
    out["chat_latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    return out


def raw_google():
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        return {"provider": "google", "configured": False, "note": "GOOGLE_API_KEY not set"}
    model = "gemini-2.5-flash"
    out = {"provider": "google", "configured": True, "key_prefix": key[:12] + "***", "model": model}
    t0 = time.monotonic()
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        body = {"contents": [{"role": "user", "parts": [{"text": "Reply with exactly: PONG_GOOGLE"}]}]}
        r = requests.post(url, json=body, timeout=30)
        out["status"] = r.status_code
        if r.status_code == 200:
            d = r.json()
            txt = ""
            for c in d.get("candidates", []):
                for p in c.get("content", {}).get("parts", []):
                    txt += p.get("text", "")
            out["response"] = txt.strip()[:120]
            u = d.get("usageMetadata", {})
            out["usage"] = {"prompt": u.get("promptTokenCount"), "candidates": u.get("candidatesTokenCount")}
        else:
            out["body"] = r.text[:200]
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    out["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    return out


def raw_hf():
    key = os.environ.get("HF_TOKEN")
    if not key:
        return {"provider": "hf", "configured": False, "note": "HF_TOKEN not set"}
    out = {"provider": "hf", "configured": True, "key_prefix": key[:12] + "***"}
    t0 = time.monotonic()
    try:
        r = requests.get("https://huggingface.co/api/whoami-v2",
                         headers={"Authorization": f"Bearer {key}"}, timeout=30)
        out["whoami_status"] = r.status_code
        if r.status_code == 200:
            d = r.json()
            out["whoami"] = {"name": d.get("name"), "type": d.get("type")}
    except Exception as e:
        out["whoami_error"] = f"{type(e).__name__}: {e}"
    out["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    # inference endpoint
    ep = os.environ.get("JARVIS_HF_INFERENCE_ENDPOINT")
    if ep:
        t0 = time.monotonic()
        try:
            r = requests.get(ep.rstrip("/") + "/v1/models",
                             headers={"Authorization": f"Bearer {key}"}, timeout=30)
            out["inference_status"] = r.status_code
        except Exception as e:
            out["inference_error"] = f"{type(e).__name__}: {e}"
        out["inference_latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    else:
        out["inference_note"] = "JARVIS_HF_INFERENCE_ENDPOINT not set"
    return out


def raw_brain():
    ep = os.environ.get("JARVIS_BRAIN_ENDPOINT")
    key = os.environ.get("JARVIS_BRAIN_API_KEY")
    out = {"provider": "jarvis_brain", "endpoint": ep, "key_present": bool(key)}
    if not ep:
        out["note"] = "JARVIS_BRAIN_ENDPOINT not set"
        return out
    base = ep.rstrip("/")
    hdr = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"} if key else {"Content-Type": "application/json"}
    t0 = time.monotonic()
    try:
        r = requests.get(base + "/v1/models", headers=hdr, timeout=15)
        out["models_status"] = r.status_code
        out["models_body"] = (r.text[:300] if r.status_code != 200 else r.json())
    except Exception as e:
        out["models_error"] = f"{type(e).__name__}: {e}"
    out["models_latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    # chat
    t0 = time.monotonic()
    try:
        body = {"model": os.environ.get("JARVIS_BRAIN_MODEL", "jarvis-brain-qwen3-4b-sft-v1"),
                "messages": [{"role": "user", "content": "Reply with exactly: PONG_BRAIN"}],
                "max_tokens": 20, "temperature": 0.0}
        r = requests.post(base + "/v1/chat/completions", headers=hdr, json=body, timeout=20)
        out["chat_status"] = r.status_code
        if r.status_code == 200:
            d = r.json()
            out["chat_response"] = d["choices"][0]["message"]["content"].strip()
            u = d.get("usage", {})
            out["chat_usage"] = {"prompt": u.get("prompt_tokens"), "completion": u.get("completion_tokens")}
        else:
            out["chat_body"] = r.text[:200]
    except Exception as e:
        out["chat_error"] = f"{type(e).__name__}: {e}"
    out["chat_latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    return out


results["openai"] = raw_openai()
print("=== OPENAI ===")
print(json.dumps(results["openai"], indent=2))
print()
results["google"] = raw_google()
print("=== GOOGLE ===")
print(json.dumps(results["google"], indent=2))
print()
results["hf"] = raw_hf()
print("=== HUGGINGFACE ===")
print(json.dumps(results["hf"], indent=2))
print()
results["brain"] = raw_brain()
print("=== JARVIS BRAIN ===")
print(json.dumps(results["brain"], indent=2))

print()
print("=== SUMMARY ===")
for pid, r in results.items():
    ok = r.get("chat_response") or r.get("response") or r.get("models_status") == 200
    print(f"{pid}: key={'yes' if r.get('configured') or r.get('key_present') else 'no'} ok={bool(ok)}")

with open(os.path.join(ROOT, "phase6_provider_smoke.json"), "w") as f:
    json.dump(results, f, indent=2)
print("\nSaved => F:\\AI\\phase6_provider_smoke.json")
