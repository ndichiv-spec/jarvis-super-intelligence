"""Builder for truthfulness-report.json (sec 9 - simulated/hardcoded frontend-only data)."""
import json, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "truthfulness-report.json")

doc = {
    "artifact": "truthfulness-report",
    "generated_by": "JARVIS Platform X-Ray - sec 9",
    "method": "rg -n 'Math.random' over frontend/web/src (excluding node_modules); rg -n 'Math.floor|Date.now' for fake telemetry; cross-check against live backend data sources (/system/dashboard, /capabilities, /agents, /knowledge).",

    "categories": {
        "math_random_simulated_data": {
            "classification": "MOCKED - simulated telemetry in ~10 dashboards",
            "evidence": [
                "src/app/dashboard/jarvis-v10-chambers.tsx L117-121, L313",
                "src/app/dashboard/jarvis-smart-home.tsx:105",
                "src/app/dashboard/analytics-dashboard.tsx L210-221, L362-414",
                "src/app/dashboard/supreme/page.tsx:448 (placeholder only)",
                "src/app/dashboard/holographic/page.tsx L61-239",
                "src/app/dashboard/neural-background.tsx L48-56",
                "src/app/dashboard/cascade-codeviewer.tsx:173-178",
                "src/app/dashboard/real-time-monitoring.tsx L148-184",
                "src/app/dashboard/modern-dashboard-system.tsx L225-228",
                "src/app/dashboard/omega/page.tsx:320-339",
                "src/app/dashboard/knowledge-hub/page.tsx:491 ({Math.floor(Math.random()*1000+100)} views)",
                "src/app/dashboard/neural-activity-map.tsx L95-100, L207",
            ],
            "impact": "Dashboard widgets show fabricated numbers indistinguishable from real metrics; operator trust degraded.",
        },
        "hardcoded_frontend_only_state": {
            "classification": "HARDCODED / frontend-only state not synchronized to backend",
            "evidence": [
                {
                    "component": "APP_REGISTRY (desktop window manager)",
                    "file": "frontend/web/src/components/desktop/DesktopProvider.tsx L111",
                    "detail": "Static array of window/app definitions; no backend authority; lost on refresh; no auth (no get_current_user dependency).",
                },
                {
                    "component": "Frontend backup_registry",
                    "file": "frontend/web/src/lib/autonomous-state-manager.ts",
                    "detail": "stateManager.get('backup_registry') hardcoded in browser localStorage; per-browser only; no cross-device sync; no real authz.",
                },
                {
                    "component": "Agent scheduler stub",
                    "file": "jarvis_backend/routers/agents.py:207",
                    "detail": "returns {running:true,interval:60,next_run:None} - scheduler_running is a static stub, not a live scheduler. /automation scheduler_running=false (system.py dashboard).",
                },
                {
                    "component": "n8n automation",
                    "file": "jarvis_backend/routers/automation.py",
                    "detail": "_n8n_headers() returns empty headers when no N8N_API_KEY (no key configured) -> automation is a passthrough stub.",
                },
            ],
        },
        "backend_static_stub_data": {
            "classification": "HARDCODED - backend serves static seed data with no live source",
            "evidence": [
                {"component": "Agent roster", "file": "agents.py _DEFAULT_AGENTS L15-23", "detail": "Static [jarvis-core/coordinator, researcher/research, analyst/analysis, engineer/engineering]; list_or_default_agents falls back to these. Matches /system/dashboard agents.by_role but is NOT live-discovered."},
                {"component": "Provider settings", "file": "system.py provider-settings endpoint", "detail": "providers.configured=[] and ai_enabled=False - seeded/empty, no live provider state."},
            ],
        },
        "frontend_bypassing_backend_truth": {
            "classification": "DUPLICATED / bypass - frontend maintains 3 API clients with overlapping truth sources",
            "evidence": [
                "src/lib/api.ts (jarvisAPI): getSystemDashboard L666, getCapabilities L533, getIdentity/updateIdentity, login L1180 - the canonical client.",
                "src/api-client.ts (apiClient): setAuthToken L47, refresh-token L158-167, _authToken in localStorage - SEPARATE auth state from SystemMonitor's SystemMonitor."
                "src/features/system/api.ts:10 calls getCapabilities; src/features/system/store.ts:73 consumes - THIRD copy of capability truth.",
                "Duplicated types: src/types.ts L46 AND src/features/system/types.ts L84 both define SystemCapability + registry?: SystemCapability[].",
            ],
        },
    },

    "verified_real_data_paths": {
        "description": "Components already repointed to backend truth (NOT simulated):",
        "evidence": [
            {"component": "SystemMonitor.tsx", "file": "frontend/web/src/components/desktop/apps/SystemMonitor.tsx", "detail": "Fetches /system/dashboard every 5s + /platform/identity once; no psutil; no Math.random; dropped useMonitoringStore/recharts; CAPABILITIES panel via jarvisAPI.getCapabilities(); PLATFORM chip via jarvisAPI.getIdentity()."},
            {"component": "dashboard/monitoring/page.tsx", "file": "src/app/dashboard/monitoring/page.tsx:326", "detail": "Explicit comment 'real data, no Math.random'.",
            },
            {"component": "knowledge page getCategoryColor", "file": "src/app/dashboard/knowledge/page.tsx:94", "detail": "Fixed: category?:string|null -> (category||'').toLowerCase(); tsc=0.",
            },
        ],
    },

    "frontend_secret_shape_exposure": {
        "classification": "SECURITY-RISK - secret field names exposed in type defs + settings placeholders",
        "evidence": [
            "src/lib/api.ts L327-339 ProviderApiKeys type lists: openai_api_key, google_gemini_api_key, anthropic_api_key, huggingface_api_key, stability_api_key, replicate_api_key, aws_secret_access_key, tavily_api_key, serper_api_key, news_api_key, openweathermap_api_key.",
            "src/app/dashboard/settings/page.tsx placeholder strings expose prefix shapes: sk-..., google_gemini_api_key, sk-ant-..., hf_..., r8_..., AKIA..., tvly_..., serper_..., newsapi_..., OWM key.",
            "src/components/control-center-api.ts:6 claims 'No raw secrets' - contradicted by the type enum above.",
        ],
    },

    "summary": {
        "simulated_data_locations": 10,
        "frontend_only_hardcoded_components": 3,
        "backend_static_stubs": 2,
        "frontend_duplicated_clients": 3,
        "secret_shape_exposure_locations": 3,
        "overall": "PARTIAL - ~10 dashboards simulate data with Math.random; SystemMonitor/knowledge/monitoring have been repointed to backend truth; the remaining simulated dashboards must be migrated to /system/dashboard or explicit provider endpoints, and the 3-way frontend client/type duplication must be collapsed to a single source.",
    },
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2, ensure_ascii=False)
    f.write("\n")
print("WROTE", OUT, os.path.getsize(OUT), "bytes; fakes:", doc["summary"]["simulated_data_locations"])
