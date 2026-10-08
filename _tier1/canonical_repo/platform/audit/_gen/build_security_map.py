"""Builder for security-map.json (sec 8/14 - auth boundary, credential flow, risks)."""
import json, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "security-map.json")

doc = {
    "artifact": "security-map",
    "generated_by": "JARVIS Platform X-Ray - sec 8/14",
    "method": "rg import/usage scan of backend routers (jarvis_backend/routers/*.py) for Depends(get_current_user|get_optional_user); rg scan of credential sinks; live curl probes of auth-gated vs public endpoints.",

    "auth_boundary": {
        "description": "Per-router authentication posture. core.get_current_user / core.get_optional_user are the two auth gates.",
        "authenticated_routers": [
            "agents.py", "browser.py", "developer.py", "connectors.py", "automation.py",
            "auth.py", "legacy.py", "search.py", "sandbox.py", "rbac.py", "extensions.py",
        ],
        "unauthenticated_routers": [
            {"router": "system.py", "evidence": "rg imports only ROOT,ai_service,get_store,now_iso (summary); no Depends/get_current_user in file. /system/dashboard, /system/launch, /system/provider-settings, /system/processes, /system/files, /system/screenshot, /system/clipboard, /system/windows all reachable without token."},
            {"router": "health.py", "evidence": "health/public by design (GET /health, /api/health, /api/v1/metrics)."},
            {"router": "platform_identity.py", "evidence": "GET/PUT /platform/identity unauthenticated (verified live 09:28 - GET 200, PUT secret-shaped 400)."},
            {"router": "stark.py", "evidence": "POST /tool no get_current_user dependency."},
            {"router": "misc.py", "evidence": "misc endpoints (notes/reminders etc.) no auth gate."},
            {"router": "ai.py", "evidence": "ai.py has NO get_current_user (only provider-key honesty guard at gateway tier); AI endpoint reachable without session token."},
            {"router": "media.py", "evidence": "no auth gate."},
            {"router": "voice.py", "evidence": "no auth gate."},
            {"router": "codegen.py", "evidence": "no auth gate."},
            {"router": "billing.py", "evidence": "no auth gate."},
            {"router": "global_knowledge.py", "evidence": "no auth gate (global, public knowledge)."},
            {"router": "monitoring.py", "evidence": "monitoring surface no auth gate."},
            {"router": "multimodal.py", "evidence": "no auth gate."},
        ],
        "classification": "SECURITY-RISK - 11 of 15 auditable routers expose endpoints with no authentication; system.py is the most severe (host-launch + provider-settings + processes + files).",
        "live_probe": {
            "system_dashboard": "GET /api/v1/system/dashboard -> 200 without Authorization header (verified).",
            "rbac_users": "GET /rbac/users -> 200 without token.",
            "rbac_audit_logs": "GET /rbac/audit-logs -> 401 Not authenticated (admin-gated via _require_admin).",
        },
    },

    "credential_flow": {
        "summary": "Credentials are handled with THREE inconsistent schemes. Connectors use Fernet encryption; API keys are PBKDF2-hashed; provider settings are stored PLAINTEXT. This is a SECURITY-RISK.",
        "connector_credentials": {
            "store": "REAL - secure",
            "evidence": "jarvis_backend/connectors/registry.py persists jarvis_data/connectors/<kind>.json; jarvis_backend/connectors/crypto.py Fernet encrypt/decrypt; public_config.MASK redacts on read; registry.audit JSONL logs actions with timestamp/user/id. rg confirms crypto.py imported by registry.",
        },
        "api_keys": {
            "store": "REAL - hashed",
            "evidence": "core.py L458-486 hashes API keys (API_KEY_PREFIX='jarvis_', _API_KEY_HEX_LEN=32, PBKDF2-style); kv in 'api_keys' store. Not plaintext.",
        },
        "provider_settings_plaintext": {
            "store": "SECURITY-RISK - plaintext",
            "evidence": "system.py update_provider_settings L284-296 stores openai_api_key/anthropic_api_key/google_gemini_api_key/huggingface_api_key/stability_api_key/replicate_api_key/aws_secret_access_key/tavily_api_key/serper_api_key/news_api_key/openweathermap_api_key into get_store('misc') UNENCRYPTED via settings[field]=value. RG-proven: update_provider_settings has no crypto import; db.py kv_store.value is raw Text. Contrast with encrypted connector keys -> inconsistency is the risk.",
            "frontend_exposure": "src/lib/api.ts L327-339 ProviderApiKeys type enumerates the secret field names (openai_api_key,google_gemini_api_key,antrhopic_api_key,huggingface_api_key,stability_api_key,replicate_api_key,aws_secret_access_key,tavily_api_key,serper_api_key,news_api_key,openweathermap_api_key); dashboard/settings/page.tsx placeholders expose key SHAPE (sk-...,google_gemini_api_key,sk-ant-...,hf_...,r8_...,AKIA...,tvly_...,serper_...,newsapi_...,OWM key).",
        },
        "oauth_tokens": {
            "store": "PARTIAL",
            "evidence": "connectors/oauth.py _backend_base() builds callback URL (localhost:3000); oauth flow via connectors/oauth.py; tokens persisted by connector registry (Fernet). OAuth is capability-gated (email/imap) not a standalone router.",
        },
    },

    "host_command_sandboxing": {
        "description": "Destructive host commands are deny-listed at both the backend and the sandbox executor.",
        "backend": {
            "file": "jarvis_backend/routers/system.py",
            "deny_commands": "_DENY_COMMANDS=('shutdown','reboot','halt','poweroff','tsshutdown','stop-computer','init 0','init 6','wsl --shutdown','powercfg /h') L376-380",
            "launch_endpoint": "POST /system/launch refuses app in _DENY_COMMANDS -> 403 {'detail':'Refusing destructive host command matching ...'} L408-429",
            "live_probe": "POST /system/launch {'app':'shutdown','args':'/s /t 0'} -> 403 (verified). Every launch audited via _audit_system_launch -> audit_logs store.",
            "whitelist": "cmd.exe /c echo ok -> 200 (verified).",
        },
        "sandbox": {
            "file": "infrastructure/sandbox/executor.py",
            "deny_list": "L63-67 deny-list (reboot/shutdown/halt/poweroff) - DISCONNECTED from any live backend path; executor.py is infrastructure, not wired into system.py /launch.",
            "classification": "DISCONNECTED - deny-list exists but the sandbox executor is not in the live launch path (system.py uses its own _DENY_COMMANDS).",
        },
    },

    "ipv6_localhost_self_callback": {
        "description": "Backend constructs self-callback base URLs from localhost literal strings that resolve to ::1 (IPv6) in some environments, risking loopback bypass / SSRF-style self-calls when 127.0.0.1 is expected.",
        "locations": [
            "routers/system.py:38 start http://localhost:3000",
            "connectors/oauth.py:202-203 _backend_base()",
            "routers/extensions.py:596 and :922",
            "routers/connectors.py:270",
            "core.py:593 ollama localhost default",
            "core.py:677 CORS allowlist [http://localhost:3000, http://localhost:5173, http://localhost:5003]",
        ],
        "classification": "SECURITY-RISK - hardcoded localhost; not host:port-pinned to 127.0.0.1; CORS allowlist uses localhost literal.",
    },

    "rbac_object_level_gap": {
        "description": "RBAC enforces tenant-isolation at the ROLE level via _require_admin/_require_auth, but there is no object-level / per-resource ownership check.",
        "evidence": "rbac.py /rbac/users returns {users,total,page,per_page} (default 20, NO upper bound clamp -> unbounded page param -> resource-exhaustion vector). /roles -> {roles}. /permissions -> {permissions}. /rbac/audit-logs -> 401 (admin gate).",
        "gap": "Any authenticated user can enumerate all users/roles/permissions; no row-level 'resource owner' authorization. Classification: PRODUCTION-INCOMPLETE.",
    },

    "notifications": {
        "description": "No dedicated notifications security surface.",
        "finding": "ABSENT - no /api/v1/notifications router. Notifications are delivered via the email connector capability (get_store('mail') / connector test()) + platform_identity.py notification_configuration (GET/PUT identity.notification_configuration L66-69). So 'notifications' = a field on platform identity, not a secured endpoint.",
    },

    "identity_endpoint_risks": {
        "description": "platform_identity.py is the public identity surface and is the ONLY guarded-by-semantics endpoint on the no-auth surface.",
        "guards": [
            "PUT /platform/identity rejects secret-shaped field names (api_key, secret, token, password, key, *_api_key, aws_secret_access_key, etc.) -> 400 'Refusing secret-shaped field X via identity API' L100-101. Verified live 09:28: PUT {'api_key':'sk-...'} -> 400.",
            "env-derived transport (L34-36) - reads from environment, not request body.",
        ],
        "residual_risk": "GET /platform/identity is unauthenticated -> returns developer_identity + verification_status (non-secret). Verified live: GET -> 200 developer_identity:'dev-001', verification_status:'verified'.",
    },

    "audit_surface": {
        "description": "Audit logging exists for launches and connectors but is incomplete.",
        "stores": [
            "audit_logs (SQL KV via get_store) - system.py _audit_system_launch appends.",
            "jarvis_data/audit/connectors.jsonl - connectors/registry.py appends per-action with timestamp/user/id + provenance in ActionSpec.",
        ],
        "gap": "Most unauthenticated routers (system.py reads, health, ai.py generation, stark tool, media/voice/codegen) leave NO audit trail -> SECURITY-RISK/PARTIAL.",
    },

    "risk_register": {
        "CRITICAL": [
            "system.py unauthenticated /launch + provider-settings + processes + files (host-RCE adjacent).",
            "Provider settings stored plaintext in misc KV (system.py L284-296).",
            "Frontend ProviderApiKeys type + settings placeholders expose secret SHAPE.",
            "localhost (not 127.0.0.1) self-callbacks + CORS allowlist.",
            "ai.py reachable without auth token (generation endpoint).",
        ],
        "HIGH": [
            "11/15 routers unauthenticated.",
            "rbac no object-level / per-resource ownership; unbounded page param.",
            "Plugin Registry dead; APP_REGISTRY frontend-only (no authority).",
        ],
        "MEDIUM": [
            "Three inconsistent credential schemes (Fernet / PBKDF2 / plaintext).",
            "Sandbox executor deny-list disconnected from live path.",
            "Silverwing backend path absent -> brain endpoint unset (integrity/availability).",
        ],
        "LOW": [
            "GET /platform/identity unauthenticated (non-secret data only).",
            "search.py public (no get_current_user) by design gap.",
        ],
    },
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2, ensure_ascii=False)
    f.write("\n")
print("WROTE", OUT, os.path.getsize(OUT), "bytes; risks:", len(doc["risk_register"]["CRITICAL"]), "critical")
