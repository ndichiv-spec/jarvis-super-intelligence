"""Builder for frontend-architecture-map.json (sec 6 - clients/stores/types/duplication)."""
import json, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend-architecture-map.json")

doc = {
    "artifact": "frontend-architecture-map",
    "generated_by": "JARVIS Platform X-Ray - sec 6",
    "method": "rg -n of imports/usages over frontend/web/src; Get-ChildItem of store files; tsc --noEmit baseline (0).",

    "clients": {
        "description": "Three named client modules. Of these, two are real transport clients and one is a thin per-feature facade.",
        "jarvisAPI": {
            "file": "src/lib/api.ts",
            "class": "JarvisAPI",
            "instance": "jarvisAPI = new JarvisAPI() (L1368)",
            "exports": "getApiBaseUrl (L15), getWsBaseUrl (L32), SystemDashboard/PlatformIdentity/ProviderSettings/ProviderApiKeys/LoginResponse interfaces (L154-418), getSystemDashboard (L666), getCapabilities (L533), getIdentity/updateIdentity, login (L1180), setToken (L464), Bearer header (L481).",
            "consumers": [
                "app/login/page.tsx (jarvisAPI.login)", "app/workflows/page.tsx", "app/voice/page.tsx",
                "app/knowledge-hub/page.tsx", "app/image-generation/page.tsx", "app/supreme/page.tsx",
                "app/forgot-password/page.tsx", "app/register/page.tsx", "app/omega/page.tsx",
                "app/dashboard/system/page.tsx", "app/dashboard/sessions/page.tsx", "app/dashboard/advanced/page.tsx",
                "app/dashboard/cognitive/page.tsx", "app/dashboard/admin/page.tsx", "app/dashboard/api-keys/page.tsx",
                "components/desktop/apps/SystemMonitor.tsx (getSystemDashboard/getCapabilities/getIdentity)",
                "components/desktop/apps/ChatApp.tsx, FileManager.tsx, AgentsApp.tsx",
                "components/connection-banner.tsx (getApiBaseUrl)", "stores/authStore.ts",
            ],
            "classification": "REAL - canonical client.",
        },
        "apiClient": {
            "file": "src/lib/api-client.ts (10166 bytes; NOT src/api-client.ts as earlier summary stated)",
            "shape": "Default-exported `ax` (axios instance); setAuthToken (L47), getAuthToken, refresh-token (L158-167), _authToken in localStorage, AuthError, ApiClientError, onAuthError, clearAuthToken.",
            "consumers": [
                "features/browser/api.ts (19 calls), features/search/api.ts (11 calls), features/automation/api.ts, features/monitoring/api.ts, features/memory/api.ts, features/auth/api.ts (login/register/logout/me/apiKeys/sessions), features/auth/store.ts",
                "app/dashboard/extensions/page.tsx, app/dashboard/search/page.tsx, app/dashboard/connections/page.tsx, app/dashboard/developer/capabilities/page.tsx",
                "components/sub-dashboards/security-dashboard.tsx, control-center/{security,permissions,diagnostics,developer,connections}-tab.tsx",
                "components/jarvis-notes.tsx, jarvis-reminders.tsx, real-ai-chat.tsx, app/dashboard/layout.tsx (onAuthError/clearAuthToken)",
            ],
            "classification": "REAL - transport client, auth-token manager. Used by the feature-per-feature api.ts facades.",
        },
        "systemApi": {
            "file": "src/features/system/api.ts (export const systemApi = { ... } L5, default export L35)",
            "shape": "Thin facade: getStatus/getCapabilities/getProcesses/getProviderSettings/updateProviderSettings/listFiles/killProcess - delegates to apiClient with /api/v1/system/* URLs.",
            "consumers": "features/system/store.ts ONLY (useSystemStore uses systemApi.getStatus/getCapabilities/getProcesses/getProviderSettings/updateProviderSettings/listFiles/killProcess).",
            "classification": "DUPLICATED - wraps apiClient; its only consumer (features/system/store.ts) DUPLICATES src/stores/system-store.ts useSystemStore. Two parallel 'system' store+client stacks.",
        },
        "duplication_note": "jarvisAPI vs apiClient both hit /api/v1/* (jarvisAPI likely wraps an internal fetch/axios; apiClient uses axios `ax`). CAPABILITIES truth is fetched via jarvisAPI.getCapabilities by SystemMonitor AND via systemApi.getCapabilities by features/system/store.ts — 2 code paths, 1 backend endpoint. No single frontend source of truth.",
    },

    "stores": {
        "description": "Zustand stores. 4 hook names are DUPLICATED across src/stores/ and src/features/*/store.ts.",
        "canonical_stores_src_stores": [
            {"file": "src/stores/authStore.ts", "hook": "useAuthStore", "notes": "imports jarvisAPI from @/lib/api"},
            {"file": "src/stores/platform-store.ts", "hook": "usePlatformStore", "selectors": "useBackend, useSystemUsage, useProviders, useActivity, useNotifications, useWorkspace, useSilverwing, useUser (L383-391)"},
            {"file": "src/stores/monitoring-store.ts", "hook": "useMonitoringStore"},
            {"file": "src/stores/chat-store.ts", "hook": "useChatStore"},
            {"file": "src/stores/system-store.ts", "hook": "useSystemStore"},
        ],
        "feature_stores_src_features": [
            {"file": "src/features/agents/store.ts", "hook": "useAgentsStore"},
            {"file": "src/features/auth/store.ts", "hook": "useAuthStore", "imports": "setAuthToken from @/lib/api-client"},
            {"file": "src/features/automation/store.ts", "hook": "useAutomationStore"},
            {"file": "src/features/browser/store.ts", "hook": "useBrowserStore"},
            {"file": "src/features/chat/store.ts", "hook": "useChatStore"},
            {"file": "src/features/memory/store.ts", "hook": "useMemoryStore"},
            {"file": "src/features/monitoring/store.ts", "hook": "useMonitoringStore"},
            {"file": "src/features/search/store.ts", "hook": "useGlobalSearchStore"},
            {"file": "src/features/system/store.ts", "hook": "useSystemStore", "consumes": "systemApi facade"},
            {"file": "src/features/voice/store.ts", "hook": "useVoiceStore"},
        ],
        "duplicated_store_hooks": [
            "useSystemStore: src/stores/system-store.ts AND src/features/system/store.ts",
            "useMonitoringStore: src/stores/monitoring-store.ts AND src/features/monitoring/store.ts",
            "useChatStore: src/stores/chat-store.ts AND src/features/chat/store.ts",
            "useAuthStore: src/stores/authStore.ts AND src/features/auth/store.ts",
        ],
        "desktop_provider_store": {
            "file": "src/components/desktop/DesktopProvider.tsx:197",
            "hook": "useDesktop (create)",
            "note": "Co-located with APP_REGISTRY (L111) - the hardcoded window-manager registry.",
        },
        "classification": "DUPLICATED - 4 hook names exported from two locations; reader must guess which is canonical.",
    },

    "hooks": {
        "websocket_duplicate": {
            "a": "src/lib/websocket.ts: useWebSocket (L21), useHealthWebSocket (L141), useAgentWebSocket (L157), useMonitoringWebSocket",
            "b": "src/hooks/useWebSocket.ts: useWebSocketSubscription (L7), useHealthWebSocket (L44), useAgentWebSocket (L53), useMonitoringWebSocket (L62)",
            "classification": "DUPLICATED - two websocket hook modules with overlapping names (useHealthWebSocket/useAgentWebSocket/useMonitoringWebSocket exist in BOTH).",
        },
        "generic_fetch": "src/hooks/useApi.ts: useApi (L18), useApiLazy (L70).",
        "other": "src/hooks/useNavigationContext.ts (L20/L49), src/lib/neural-theme-engine.tsx useNeuralTheme (L400), src/components/autonomous-dashboard-provider.tsx useAutonomousDashboard (L141), src/lib/i18n.ts useTranslation (L501), src/components/advanced-theme-system.tsx useAdvancedTheme (L124).",
    },

    "types": {
        "duplicated_SystemCapability": {
            "a": "src/types.ts:26 export interface SystemCapability; registry?: SystemCapability[] at types.ts:46",
            "b": "src/features/system/types.ts:64 export interface SystemCapability; registry?: SystemCapability[] at features/system/types.ts:84",
            "classification": "DUPLICATED - identical interface name + shape in two files; no single source.",
        },
        "shared_interfaces_in_jarvisAPI": [
            "SystemDashboard (L154)", "PlatformIdentity (L178)", "AgentStats (L221)",
            "ProviderSettings (L324)", "ProviderApiKeys (L327-339)", "LoginResponse (L359)",
            "SessionInfo (L383)", "AuditLogEntry (L270)",
        ],
    },

    "endpoint_url_map": {
        "description": "Frontend URL configuration.",
        "config_api_ts": "src/config/api.ts: API_PREFIX='/api/v1', per-resource URL map (per-page).",
        "env_ts": "src/config/env.ts:1 process.env.NEXT_PUBLIC_API_URL (base URL source).",
        "runtime_derive": "lib/api.ts getApiBaseUrl (L15) + getWsBaseUrl (L32) derive from NEXT_PUBLIC_API_URL with localhost fallback.",
        "env_files": ["frontend/web/.env.local", "frontend/web/.env.example"],
    },

    "desktop_layer": {
        "shell": "src/components/desktop/{Desktop,DesktopProvider,Window,Taskbar,StartMenu,index}.tsx",
        "apps": "src/components/desktop/apps/{SystemMonitor,TerminalApp,SettingsApp,KnowledgeGraphApp,FileManager,ChatApp,BrowserApp,EnhancedBrowserApp,CascadeAIApp,AgentsApp}.tsx",
        "window_manager": "APP_REGISTRY hardcoded in DesktopProvider.tsx L111 (HUShCED/frontend-only) - maps APP_REGISTRY[id].component to a window.",
        "routes": ["app/desktop", "app/holographic", "app/workflows", "app/omega", "app/stark-control", "app/image-generation", "app/voice", "app/login", "app/register", "app/oauth/callback/[extension_id]", "app/enterprise-sso"],
        "backend_router_for_desktop": "ABSENT - no dedicated backend router for desktop/holographics/IDE/workflows. Desktop apps talk only to existing routers (system, knowledge, agents, browser, connectors).",
    },

    "data_flow_capabilities_and_platform": {
        "CAPABILITIES": {
            "producer": "jarvis_backend/routers/system.py GET /api/v1/system/capabilities (17 entries)",
            "transport": "jarvisAPI.getCapabilities() (lib/api.ts L533)",
            "consumer_real": "SystemMonitor.tsx CAPABILITIES panel (L145) - verified fetching live.",
            "consumer_duplicate": "features/system/store.ts via systemApi.getCapabilities() -> app/dashboard/system/page.tsx",
        },
        "PLATFORM_IDENTITY": {
            "producer": "jarvis_backend/routers/platform_identity.py GET /platform/identity",
            "transport": "jarvisAPI.getIdentity() (lib/api.ts)",
            "consumer_real": "SystemMonitor.tsx PLATFORM panel (L157) - verified live 09:28.",
        },
        "SYSTEM_DASHBOARD": {
            "producer": "system.py GET /api/v1/system/dashboard (L157-244)",
            "transport": "jarvisAPI.getSystemDashboard() (lib/api.ts L666)",
            "consumer_real": "SystemMonitor.tsx (L126, poll every 5s) - verified live.",
        },
    },

    "temp_junk": [
        "src/_temp_bstore_iface.txt (3552 bytes, 20-Sep 11:23) - non-source artifact in src/.",
    ],

    "summary": {
        "client_modules": 3,
        "real_transport_clients": 2,
        "feature_facade_wrappers": 1,
        "zustand_stores_count": 16,
        "duplicated_store_hooks": 4,
        "duplicated_SystemCapability_type": 1,
        "duplicated_websocket_hook_modules": 1,
        "overall": "PARTIAL - functional but fragmented. 3 client modules (2 real + 1 thin facade), 16 zustand stores with 4 duplicated hook names, duplicated SystemCapability type, and duplicated websocket hook modules. CAPABILITIES/PLATFORM/SYSTEM_DASHBOARD data flows are clean and live, but capacity/capabilities truth fans out through 2 parallel store+client stacks.",
    },
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2, ensure_ascii=False)
    f.write("\n")
print("WROTE", OUT, os.path.getsize(OUT), "bytes; dup_hooks:", doc["summary"]["duplicated_store_hooks"])
