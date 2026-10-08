"""Builder for dependency-map.json (cross-sector imports/calls) and
integration-map.json (§4 chains + where each stops). Python literals ->
json.dump guarantees valid JSON."""
import json, os

DIR = os.path.dirname(os.path.abspath(__file__))
OUTDEP = os.path.join(DIR, "..", "dependency-map.json")
OUTINT = os.path.join(DIR, "..", "integration-map.json")

nodes = [
    {"id": "core", "sector": "shared-kernel", "type": "module", "location": "jarvis_backend/core.py (Store, ai_service, get_current_user, now_iso, ROOT, DATA_DIR)"},
    {"id": "db", "sector": "persistence", "type": "module", "location": "jarvis_backend/db.py (kv_store, kv_load/save/get/delete)"},
    {"id": "gateway", "sector": "ai", "type": "module", "location": "jarvis_backend/gateway.py (ProviderGateway, ChatService)"},
    {"id": "chat_service", "sector": "ai", "type": "service", "location": "jarvis_backend/chat_service.py"},
    {"id": "system", "sector": "system", "type": "router", "location": "jarvis_backend/routers/system.py"},
    {"id": "platform_identity", "sector": "identity", "type": "router", "location": "jarvis_backend/routers/platform_identity.py"},
    {"id": "auth", "sector": "auth", "type": "router", "location": "jarvis_backend/routers/auth.py"},
    {"id": "rbac", "sector": "authz", "type": "router", "location": "jarvis_backend/routers/rbac.py"},
    {"id": "agents", "sector": "agents", "type": "router", "location": "jarvis_backend/routers/agents.py"},
    {"id": "browser", "sector": "browser", "type": "router", "location": "jarvis_backend/routers/browser.py"},
    {"id": "browser_engine", "sector": "browser", "type": "service", "location": "jarvis_backend/browser_engine.py"},
    {"id": "search", "sector": "search", "type": "router", "location": "jarvis_backend/routers/search.py"},
    {"id": "knowledge", "sector": "knowledge", "type": "router", "location": "jarvis_backend/routers/knowledge.py"},
    {"id": "infra_knowledge", "sector": "knowledge", "type": "package", "location": "infrastructure/knowledge/{store,index,retrieval,rag,ingest,context,types,validation,retention,learning,memory_bridge,observability}.py"},
    {"id": "memory", "sector": "memory", "type": "router", "location": "jarvis_backend/routers/memory.py"},
    {"id": "connectors_registry", "sector": "integrations", "type": "module", "location": "jarvis_backend/connectors/registry.py"},
    {"id": "connectors_dispatch", "sector": "integrations", "type": "module", "location": "jarvis_backend/connectors/dispatch.py"},
    {"id": "connectors_oauth", "sector": "integrations", "type": "module", "location": "jarvis_backend/connectors/oauth.py"},
    {"id": "connectors_crypto", "sector": "security", "type": "module", "location": "jarvis_backend/connectors/crypto.py"},
    {"id": "mail_connector", "sector": "integrations", "type": "package", "location": "jarvis_backend/connectors/mail/{connector,smtp_connector,imap_connector,gmail_oauth,outlook_oauth}.py"},
    {"id": "stark", "sector": "tools", "type": "router", "location": "jarvis_backend/routers/stark.py"},
    {"id": "codegen", "sector": "tools", "type": "router", "location": "jarvis_backend/routers/codegen.py"},
    {"id": "sandbox", "sector": "tools", "type": "router", "location": "jarvis_backend/routers/sandbox.py"},
    {"id": "sandbox_executor", "sector": "tools", "type": "service", "location": "infrastructure/sandbox/{executor.py,policy.py}"},
    {"id": "automation", "sector": "automation", "type": "router", "location": "jarvis_backend/routers/automation.py"},
    {"id": "developer", "sector": "developer", "type": "router", "location": "jarvis_backend/routers/developer.py"},
    {"id": "extensions", "sector": "extensibility", "type": "router", "location": "jarvis_backend/routers/extensions.py"},
    {"id": "media", "sector": "media", "type": "router", "location": "jarvis_backend/routers/media.py"},
    {"id": "voice", "sector": "voice", "type": "router", "location": "jarvis_backend/routers/voice.py"},
    {"id": "multimodal", "sector": "multimodal", "type": "router", "location": "jarvis_backend/routers/multimodal.py"},
    {"id": "health", "sector": "ops", "type": "router", "location": "jarvis_backend/routers/health.py"},
    {"id": "monitoring", "sector": "ops", "type": "router", "location": "jarvis_backend/routers/monitoring.py"},
    {"id": "misc", "sector": "ops", "type": "router", "location": "jarvis_backend/routers/misc.py"},
    {"id": "legacy", "sector": "api", "type": "router", "location": "jarvis_backend/routers/legacy.py"},
    {"id": "global_knowledge", "sector": "knowledge", "type": "router", "location": "jarvis_backend/routers/global_knowledge.py"},
    {"id": "websocket", "sector": "realtime", "type": "router", "location": "jarvis_backend/websocket.py"},
    {"id": "observability", "sector": "ops", "type": "module", "location": "jarvis_backend/observability.py + infrastructure/observability/*"},
    {"id": "vault", "sector": "security", "type": "module", "location": "infrastructure/vault/manager.py + infrastructure/security/*"},
    {"id": "phase6_providers", "sector": "ai", "type": "package-external", "location": "F:/AI/providers (providers.bootstrap.ProviderRouter/ModelRegistry/ModelManager)"},
    {"id": "silverwing", "sector": "ai", "type": "package-external", "location": "F:/AI/silverwing-runtime, silverwing_120m, backend/model_gateway (ModelGateway)"},
    {"id": "plugins", "sector": "extensibility", "type": "package", "location": "infrastructure/plugins/* + interfaces/*"},
    {"id": "frontend_api_ts", "sector": "frontend", "type": "client", "location": "frontend/web/src/lib/api.ts (jarvisAPI)"},
    {"id": "frontend_api_client_ts", "sector": "frontend", "type": "client", "location": "frontend/web/src/lib/api-client.ts (apiClient)"},
    {"id": "frontend_system_api_ts", "sector": "frontend", "type": "client", "location": "frontend/web/src/features/system/api.ts (systemApi)"},
    {"id": "frontend_SystemMonitor", "sector": "frontend", "type": "component", "location": "frontend/web/src/components/desktop/apps/SystemMonitor.tsx"},
    {"id": "frontend_DesktopProvider", "sector": "frontend", "type": "component", "location": "frontend/web/src/components/desktop/DesktopProvider.tsx (APP_REGISTRY)"},
    {"id": "store_kv", "sector": "persistence", "type": "store", "location": "db.py kv_store table (all get_store() collections)"},
]

edges = [
    {"from": "gateway", "to": "core", "kind": "import", "evidence": "gateway.py imports core.ai_service/ROOT/get_store/now_iso (gateway.py L153, L335)"},
    {"from": "gateway", "to": "phase6_providers", "kind": "lazy-import", "evidence": "gateway.py L275 `from providers.bootstrap import bootstrap_fabric` (imported sys.path(F:/AI); main.py L198)"},
    {"from": "gateway", "to": "silverwing", "kind": "lazy-import", "evidence": "gateway.py L245 `from backend.model_gateway...ModelGateway`, L288 `from model_provider` (silverwing-backend dir absent -> ImportError fallback)"},
    {"from": "gateway", "to": "vault", "kind": "call", "evidence": "gateway.py L130 `_jarvis_brain_api_key = get_secrets_manager().get_or_none('brain_api_key')`"},
    {"from": "main", "section": "startup", "to": "observability", "kind": "call", "evidence": "main.py L213 install_observability(app)"},
    {"from": "main", "section": "startup", "to": "phase6_providers", "kind": "call", "evidence": "main.py L198 bootstrap_fabric() at _jarvis_startup"},
    {"from": "main", "section": "startup", "to": "db", "kind": "call", "evidence": "main.py create_db_and_tables() (db.create_db_and_tables)"},
    {"from": "system", "to": "core", "kind": "import", "evidence": "system.py L14 imports ONLY ROOT, ai_service, get_store, now_iso (NO get_current_user)"},
    {"from": "system", "to": "ai_service", "kind": "call", "evidence": "system.py uses ai_service.enabled / ai_service (for capabilities)"},
    {"from": "system", "section": "/dashboard", "to": "store_kv", "kind": "read", "evidence": "system.py /dashboard reads agents + misc.provider_settings + audit_logs"},
    {"from": "system", "section": "/launch", "to": "audit_logs", "kind": "write", "evidence": "system.py _audit_system_launch appends (allowed/denied) to audit_logs"},
    {"from": "platform_identity", "to": "store_kv", "kind": "read/write", "evidence": "platform_identity.py GET/PUT platform_identity + audit_logs + misc.provider_settings"},
    {"from": "auth", "to": "core", "kind": "import", "evidence": "auth.py imports core.get_current_user/get_store/verify_password/JWT"},
    {"from": "rbac", "to": "core", "kind": "import", "evidence": "rbac.py imports core.get_current_user/get_store/make_user_payload/hash_password"},
    {"from": "rbac", "to": "audit_logs", "kind": "write", "evidence": "rbac.py audit events appended"},
    {"from": "agents", "to": "core", "kind": "import", "evidence": "agents.py L314 AgentActIn depends get_current_user; uses get_store/ai_service"},
    {"from": "agents", "to": "connectors_dispatch", "kind": "call", "evidence": "agents.py L338 dispatches connector email action via dispatch"},
    {"from": "agents", "to": "sandbox", "kind": "call", "evidence": "agents.py run_code -> sandbox _sandbox_execute"},
    {"from": "agents", "to": "audit_logs", "kind": "write", "evidence": "agents.py task/execution audit"},
    {"from": "browser", "to": "browser_engine", "kind": "import/call", "evidence": "browser.py execute_action L1852 -> browser_engine driver (engine registry L558)"},
    {"from": "browser", "to": "knowledge", "kind": "write", "evidence": "browser.py L2911/L2932 get_store('knowledge').save() (extract-to-knowledge)"},
    {"from": "browser", "to": "memory", "kind": "write", "evidence": "browser.py L3102/L3104 get_store('memory').save() (evidence to memory)"},
    {"from": "browser", "to": "missions", "kind": "write", "evidence": "browser.py L2991/L3006 get_store('missions').save()"},
    {"from": "browser", "to": "connectors_registry", "kind": "call", "evidence": "browser.py L3234 connectors store read/write"},
    {"from": "search", "to": "store_kv", "kind": "read(multistore)", "evidence": "search.py L456-696 reads 15 stores via get_store(store_name); L1352 knowledge_store; L1425 get_store"},
    {"from": "search", "to": "infra_knowledge", "kind": "call", "evidence": "search.py semantic cache via infrastructure.knowledge"},
    {"from": "knowledge", "to": "infra_knowledge", "kind": "import/call", "evidence": "knowledge.py imports infrastructure.knowledge.store (KnowledgeStore); store.py L43/70/89/97/171 _notify"},
    {"from": "memory", "to": "infra_knowledge", "kind": "call", "evidence": "memory.py uses KnowledgeStore (store.py) for search/store + _notify"},
    {"from": "connectors_dispatch", "to": "connectors_registry", "kind": "import/call", "evidence": "dispatch.py L105 execute_connector_action -> L123 registry.load, L161 registry.audit"},
    {"from": "connectors_registry", "to": "connectors_crypto", "kind": "import/call", "evidence": "registry.py L23/47/59-63 encrypt/decrypt SECRET_FIELDS via crypto"},
    {"from": "mail_connector", "to": "connectors_dispatch", "kind": "register", "evidence": "dispatch.py L61 maps 'email': MailConnector"},
    {"from": "stark", "to": "gateway", "kind": "call", "evidence": "stark.py /tool -> ai_service (via gateway/ChatService for provider routing)"},
    {"from": "codegen", "to": "gateway", "kind": "call", "evidence": "codegen /generate -> ai_service.generate (provider)"},
    {"from": "sandbox", "to": "sandbox_executor", "kind": "import/call", "evidence": "sandbox.py L133 -> _sandbox_execute -> policy.py deny-list (reboot/shutdown/halt/poweroff)"},
    {"from": "automation", "to": "store_kv", "kind": "read/write", "evidence": "automation.py misc store (workflows, n8n_workflows); httpx to N8N_URL"},
    {"from": "developer", "to": "core", "kind": "import", "evidence": "developer.py uses core.get_store(ai_access/api_keys) + generate_api_key"},
    {"from": "extensions", "to": "connectors_oauth", "kind": "import/call", "evidence": "extensions.py oauth callback L890; auth via core.get_current_user/get_optional_user"},
    {"from": "legacy", "to": "chat_service", "kind": "call", "evidence": "legacy.py /api/chat -> chat_service -> gateway"},
    {"from": "legacy", "to": "browser_engine", "kind": "call", "evidence": "legacy.py /api/browser/* -> browser_engine"},
    {"from": "legacy", "to": "store_kv", "kind": "read/write", "evidence": "legacy notes/reminders/chat_sessions/chat_history/browser_sessions stores"},
    {"from": "global_knowledge", "to": "store_kv", "kind": "read/write", "evidence": "global_knowledge.py rss_feeds + misc.trends + audit_logs"},
    {"from": "observability", "to": "store_kv", "kind": "read", "evidence": "observability GATEWAY_EVENT_LOG + audit_logs"},
    {"from": "websocket", "to": "store_kv", "kind": "read/write", "evidence": "websocket.py reads sessions/tasks; broadcast to rooms"},
    {"from": "plugins", "to": "?", "kind": "DISCONNECTED", "evidence": "infrastructure/plugins NOT imported by any router in jarvis_backend (rg: no 'from infrastructure.plugins')"},
    {"from": "frontend_SystemMonitor", "to": "frontend_api_ts", "kind": "api-call", "evidence": "SystemMonitor.tsx -> jarvisAPI.getSystemDashboard (5s) + getCapabilities + getIdentity"},
    {"from": "frontend_SystemMonitor", "to": "system", "kind": "api-call", "evidence": "GET /api/v1/system/dashboard, GET /api/v1/system/capabilities, GET /api/v1/platform/identity"},
    {"from": "frontend_DesktopProvider", "to": "?", "kind": "no-backend", "evidence": "APP_REGISTRY hardcoded client-side (DesktopProvider.tsx L111); no /api/v1/desktop router"},
    {"from": "frontend_api_ts", "to": "system", "kind": "api-call", "evidence": "api.ts getSystemDashboard L666 -> /system/dashboard; getCapabilities L533 -> /system/capabilities"},
    {"from": "frontend_system_api_ts", "to": "system", "kind": "api-call", "evidence": "features/system/api.ts:10 getCapabilities -> /system/capabilities"},
    {"from": "frontend_api_client_ts", "to": "auth", "kind": "api-call", "evidence": "api-client.ts login/refresh -> /auth/*"},
]

# Aggregate adjacency
from collections import defaultdict
out_deg, in_deg = defaultdict(set), defaultdict(set)
for e in edges:
    out_deg[e["from"]].add(e["to"])
    in_deg[e["to"]].add(e["from"])
high_in = sorted(((k, len(v)) for k, v in in_deg.items()), key=lambda x: -x[1])
high_out = sorted(((k, len(v)) for k, v in out_deg.items()), key=lambda x: -x[1])

dep_doc = {
    "artifact": "dependency-map",
    "generated_by": "JARVIS Platform X-Ray - §4 dependency tracing",
    "nodes": nodes,
    "edges": edges,
    "centrality": {
        "most_consumed_nodes": [{"node": k, "consumers": v} for k, v in high_in if v >= 3],
        "most_dependent_nodes": [{"node": k, "deps": v} for k, v in high_out if v >= 4],
    },
    "interpretation": {
        "most_consumed": "core (get_current_user/get_store/ai_service) + db + audit_logs + knowledge are the fan-in hubs — everything depends on the shared kernel.",
        "fanout": "system.py, gateway.py, browser.py, search.py, connectors_dispatch are integration hubs with high fan-out.",
        "disconnected": ["plugins (infrastructure/plugins - imported nowhere at runtime)", "silverwing-backend mount (dir absent)", "silverwing tier2 (backend absent at expected path)", "Desktop (no backend router)"],
    },
    "evidence_method": "rg import/call traces + per-router import scans; file:line in 'evidence' fields."
}

# Integration map
chains = [
    {
        "name": "AI execution chain",
        "segments": [
            {"step": 1, "node": "Provider config", "to": "Provider Registry (Phase6 F:/AI/providers)", "evidence": "providers.bootstrap.ProviderRouter/ModelRegistry/ModelManager"},
            {"step": 2, "node": "Model Registry", "to": "Model Router (ProviderRouter)", "evidence": "gateway.py tier3 _chat_via_phase6_fabric"},
            {"step": 3, "node": "Model Router", "to": "ChatService -> ProviderGateway.chat()", "evidence": "chat_service.py -> gateway.py L153"},
            {"step": 4, "node": "ChatService", "to": "Agent (agents.py act / chat)", "evidence": "legacy /api/chat -> chat_service; agents use ai_service"},
            {"step": 5, "node": "Agent", "to": "Tool (stark /tool | browser execute_action | connector actions)", "evidence": "agents.py dispatch run_code|email"},
            {"step": 6, "node": "Tool", "to": "Capability Registry (/system/capabilities)", "evidence": "SystemMonitor renders caps.registry; capability-gated dispatch"},
            {"step": 7, "node": "Capability", "to": "Mission (browser /missions/{id}/browser-task)", "evidence": "browser.py L3060"},
            {"step": 8, "node": "Mission", "to": "Workflow (automation)", "evidence": "automation.py workflows"},
            {"step": 9, "node": "Workflow", "to": "Memory (memory store)", "evidence": "memory.py; browser evidence->memory"},
            {"step": 10, "node": "Memory", "to": "Audit (audit_logs)", "evidence": "audit_logs store"},
            {"step": 11, "node": "Audit", "to": "UI (SystemMonitor/agents page)", "evidence": "/system/dashboard surfaces audit tail; SystemMonitor CHARTS/AUDIT"}
        ],
        "stops_at": [
            "Provider Registry / Model Registry: no provider API keys configured (env unset) -> ai_enabled=False -> honesty guard raises PROVIDER_UNAVAILABLE; Brain endpoint unset; Silverwing backend absent; Phase6 fabric importable but inactive.",
            "Tool layer: 3 DISCONNECTED tool surfaces (stark/browser/connector), NO central ToolDef registry (rg 'ToolDef|register_tool' = 0 hits).",
            "Mission: only the browser-mission binding exists (no standalone /missions orchestration/planning/lifecycle).",
            "Workflow: scheduler stub (scheduler_running=false, engine='local'); n8n proxy inactive (N8N_API_KEY unset)."
        ]
    },
    {
        "name": "Platform Identity chain",
        "segments": [
            {"step": 1, "node": "Platform Identity (platform_identity.py)", "to": "Authentication (core JWT)", "evidence": "platform_identity returns developer_identity, verification_status"},
            {"step": 2, "node": "Authentication", "to": "Session (sessions store + refresh_tokens)", "evidence": "auth.py session CRUD, core create_refresh_token"},
            {"step": 3, "node": "Session", "to": "Device (???)", "evidence": "no device registry found; browser sessions are browser-engine sessions, not device registry"},
            {"step": 4, "node": "Device", "to": "Authorization/RBAC (rbac.py)", "evidence": "rbac role/permission checks"},
            {"step": 5, "node": "Authorization", "to": "Integration (connectors)", "evidence": "connector actions capability-gated"},
            {"step": 6, "node": "Integration", "to": "Capability (/system/capabilities)", "evidence": "capabilities include connector/email/imap/smtp"},
            {"step": 7, "node": "Capability", "to": "Notification (email via connector + identity notification_configuration)", "evidence": "connector email.send + platform_identity.notification_configuration"}
        ],
        "stops_at": [
            "Device: NO device registry / device identity sector (only browser sessions exist, different concept).",
            "Authorization: role-based guards exist but NO object-level/per-resource authorization (can-this-user-edit-user-X not enforced).",
            "Notification: NOT a first-class service — email is a connector capability gated by consent; no queue/templating/push. notification_configuration is env-derived config only."
        ]
    },
    {
        "name": "Data persistence chain (write path)",
        "segments": [
            {"step": 1, "node": "Any router/service", "to": "core.get_store(name)", "evidence": "~190 call-sites"},
            {"step": 2, "node": "Store", "to": "db.kv_save", "evidence": "core.py Store.save -> db.kv_save"},
            {"step": 3, "node": "db.kv_save", "to": "SQLite/Postgres jarvis_kv", "evidence": "db.py L190-220 atomic replace-all per collection"}
        ],
        "stops_at": ["Single persistence spine is solid; the gap is that SOME secrets bypass it: connectors use on-disk jars (registry) but provider keys use the SAME kv store PLAINTEXT."]
    }
]

cross_sector_writes = [
    {"from": "browser.py", "to": "knowledge store", "evidence": "L2911/L2932 (extract-to-knowledge -> get_store('knowledge').save())"},
    {"from": "browser.py", "to": "memory store", "evidence": "L3102/L3104 (evidence -> memory)"},
    {"from": "browser.py", "to": "missions store", "evidence": "L2991/L3006"},
    {"from": "browser.py", "to": "connectors config", "evidence": "L3234"},
    {"from": "search.py", "to": "search_history store", "evidence": "/search writes history"},
    {"from": "agents.py", "to": "tasks/executions/audit_logs", "evidence": "task dispatch"},
    {"from": "system.py", "to": "audit_logs", "evidence": "/launch deny+audit _audit_system_launch"},
]

frontend_bypasses = [
    {"component": "APP_REGISTRY (Desktop window manager)", "evidence": "hardcoded client-side (DesktopProvider.tsx L111); window state (z-index, positions, open/close) in client state only; no /api/v1/desktop backend router"},
    {"component": "Holographics", "evidence": "pure client Math.random animation; no backend data; no /api/v1/holographic"},
    {"component": "Math.random dashboards", "evidence": "jarvis-v10-chambers, smart-home, analytics-dashboard, holographic, neural-background, cascade-codeviewer, real-time-monitoring, modern-dashboard-system, omega, knowledge-hub, neural-activity-map STILL simulate telemetry (only SystemMonitor/monitoring/system-status were fixed)"},
    {"component": "Frontend auth state", "evidence": "apiClient/authStore keep token + refresh in localStorage (not HttpOnly cookie); autonomous-state-manager backup_registry in localStorage"},
    {"component": "ProviderApiKeys type", "evidence": "lib/api.ts L327-339 lists secret-shaped field names exposed to frontend"}
]

orphaned_registries = [
    {"registry": "infrastructure/plugins registry", "status": "DISCONNECTED", "evidence": "not imported by any router (rg no hits); main.build_app has no plugin load step"},
    {"registry": "Silverwing mount (/silverwing)", "status": "ABSENT", "evidence": "main.py expects ROOT/silverwing-backend which doesn't exist -> skip; /silverwing/health integrated:false"},
    {"registry": "Model Registry / Provider Registry", "status": "EXTERNAL", "evidence": "F:/AI/providers not committed in audited repo; importable via sys.path but unconfigured (no keys)"},
    {"registry": "Device Registry", "status": "ABSENT", "evidence": "no device/identity registry; only browser sessions exist"},
    {"registry": "Tool Registry", "status": "ABSENT", "evidence": "no central ToolDef/register_tool (rg=0 hits); 3 ad-hoc surfaces"},
    {"registry": "Mission Registry", "status": "PARTIAL", "evidence": "only browser.missions store; no standalone mission router with lifecycle"}
]

consumers_bypassing_registries = [
    {"consumer": "agents.py agent_act", "bypasses": "central Tool Registry (none exists)", "evidence": "directly calls dispatch.execute_connector_action + sandbox._sandbox_execute"},
    {"consumer": "stark /tool", "bypasses": "ProviderGateway multi-tier routing", "evidence": "calls ai_service directly (uncertain if wrapped); not confirmed via gateway tiering"},
    {"consumer": "codegen /generate", "bypasses": "central Tool Registry", "evidence": "ai_service.generate direct"},
    {"consumer": "Frontend DesktopProvider", "bypasses": "all backend truth for window state", "evidence": "APP_REGISTRY client-side; no backend"}
]

int_doc = {
    "artifact": "integration-map",
    "generated_by": "JARVIS Platform X-Ray - §4 cross-sector integration tracing",
    "chains": chains,
    "cross_sector_writes": cross_sector_writes,
    "frontend_bypasses_backend": frontend_bypasses,
    "orphaned_registries": orphaned_registries,
    "consumers_that_bypass_registries": consumers_bypassing_registries,
    "integration_gaps_top5": [
        "1. Provider/Model layer is UNCONFIGURED (ai_enabled=False) -> AI chain is structurally present but functionally offline.",
        "2. No central Tool Registry -> agents/stark/codegen connect to execution surfaces directly (fragile, duplicated gate logic).",
        "3. Desktop/Holographics/IDE/Workflows have NO backend routers -> frontend-only or surfaced through browser/automation/system (state lost on refresh).",
        "4. Plugins package is DISCONNECTED dead code (extensions is a separate, also-unified concern).",
        "5. system.py router is UNAUTHENTICATED while auth.py/rbac.py have the only bearer enforcement -> auth boundary is per-router, not global."
    ],
    "evidence_method": "rg import/call traces + live /system/dashboard + /health verification + router census; file:line in 'evidence' fields."
}

with open(OUTDEP, "w", encoding="utf-8") as f:
    json.dump(dep_doc, f, indent=2, ensure_ascii=False)
    f.write("\n")
with open(OUTINT, "w", encoding="utf-8") as f:
    json.dump(int_doc, f, indent=2, ensure_ascii=False)
    f.write("\n")
print("WROTE", OUTDEP, os.path.getsize(OUTDEP), "bytes |", OUTINT, os.path.getsize(OUTINT), "bytes")
