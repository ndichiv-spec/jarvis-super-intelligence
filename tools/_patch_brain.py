"""Patch gateway.py + ai.py + .env.example for Brain API-key via vault + §6 indicator.

Exactly matches existing strings; asserts each replacement count == 1.
"""
from pathlib import Path

root = Path(".")

# ---- gateway.py ----
g = (root / "jarvis_backend/gateway.py").read_text(encoding="utf-8")

g1_old = "from .errors import ChatError, ErrorCategory, from_provider_exception\n"
g1_new = (
    "from .errors import ChatError, ErrorCategory, from_provider_exception\n"
    "from infrastructure.vault.manager import get_secrets_manager\n"
)
assert g.count(g1_old) == 1, ("gateway import", g.count(g1_old))
g = g.replace(g1_old, g1_new)

g2_old = (
    '    return os.environ.get("JARVIS_BRAIN_ENDPOINT", "").strip()\n'
    '\n'
    '\n'
    'def _endpoint(url: str, path: str = "/chat/completions") -> str:\n'
)
g2_new = (
    '    return os.environ.get("JARVIS_BRAIN_ENDPOINT", "").strip()\n'
    '\n'
    '\n'
    'def _jarvis_brain_api_key() -> str:\n'
    '    """JARVIS Brain API key loaded through the project secret vault.\n'
    '\n'
    '    Resolved via ``SecretsManager`` (env variables / ``.env`` / an encrypted\n'
    '    vault file in production) -- never read as a raw env var and never\n'
    '    persisted to the application KV store. Never logged.\n'
    '    """\n'
    '    try:\n'
    '        return (get_secrets_manager().get_or_none("brain_api_key") or "").strip()\n'
    '    except Exception:  # noqa: BLE001\n'
    '        return ""\n'
    '\n'
    '\n'
    'def _jarvis_brain_api_key_configured() -> bool:\n'
    '    """True iff a JARVIS Brain API key is present (safe to expose as a boolean)."""\n'
    '    return bool(_jarvis_brain_api_key())\n'
    '\n'
    '\n'
    'def _endpoint(url: str, path: str = "/chat/completions") -> str:\n'
)
assert g.count(g2_old) == 1, ("gateway helpers", g.count(g2_old))
g = g.replace(g2_old, g2_new)

g3_old = '        auth_token = os.environ.get("JARVIS_BRAIN_API_KEY", "").strip()\n'
g3_new = '        auth_token = _jarvis_brain_api_key()\n'
assert g.count(g3_old) == 1, ("gateway auth_token", g.count(g3_old))
g = g.replace(g3_old, g3_new)

(root / "jarvis_backend/gateway.py").write_text(g, encoding="utf-8")
print("gateway.py patched")

# ---- ai.py (/api/v1/ai/status masked indicator) ----
a = (root / "jarvis_backend/routers/ai.py").read_text(encoding="utf-8")

a1_old = (
    '    if brain_endpoint:\n'
    '        from ..gateway import ProviderGateway\n'
    '        probe = await ProviderGateway().probe_brain()\n'
    '        data["brain"] = probe\n'
)
a1_new = (
    '    from ..gateway import ProviderGateway, _brain_api_key_configured\n'
    '    data["brain_api_key_configured"] = _brain_api_key_configured()\n'
    '    if brain_endpoint:\n'
    '        probe = await ProviderGateway().probe_brain()\n'
    '        data["brain"] = probe\n'
)
assert a.count(a1_old) == 1, ("ai status", a.count(a1_old))
a = a.replace(a1_old, a1_new)

(root / "jarvis_backend/routers/ai.py").write_text(a, encoding="utf-8")
print("ai.py patched")

# ---- .env.example (placeholders only) ----
e = (root / ".env.example").read_text(encoding="utf-8")
brain_section = (
    '\n'
    '# --- Remote JARVIS Brain (spec §5) ---\n'
    '# The remote OpenAI-compatible Brain endpoint (the GPU host serving\n'
    '# Qwen3-4B / the SFT adapter). The JARVIS PC talks to it over HTTP; model\n'
    '# weights stay on the GPU host. This key is a SECRET: loaded only through\n'
    '# the platform secret vault (env / .env), never hardcoded, never returned\n'
    '# by any /api route, never written to logs/telemetry/audit, and never sent\n'
    '# to the browser. Set it in your local ".env" (NEVER commit a real value);\n'
    '# in production inject it via the deployment secret manager / encrypted\n'
    '# vault file.\n'
    'JARVIS_BRAIN_ENDPOINT=\n'
    'JARVIS_BRAIN_API_KEY=\n'
    'JARVIS_BRAIN_MODEL=jarvis-brain-qwen3-4b-sft-v1\n'
)
e_anchor = "JARVIS_API_KEY=use-the-same-value-as-N8N_BASIC_AUTH_PASSWORD\n"
assert e.count(e_anchor) == 1, (".env.example anchor", e.count(e_anchor))
if "JARVIS_BRAIN_API_KEY" not in e:
    e = e.replace(e_anchor, e_anchor + brain_section, 1)
(root / ".env.example").write_text(e, encoding="utf-8")
print(".env.example patched")
