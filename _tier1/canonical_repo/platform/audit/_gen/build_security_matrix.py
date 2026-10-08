"""SEC-1 P2: Generate .jarvis/platform-audit/security-matrix.json

Classifies every route registered on the JARVIS FastAPI app into a security
matrix. Classification is rule-based on (module, path, method) with an explicit
override table for the sensitive host / credential endpoints (system.py,
provider-settings, platform_identity, auth, rbac). Routes whose source was not
individually inspected during SEC-1 P1 are flagged with
evidence_verified=false and a remediation note; nothing here is fabricated.

Usage:
    C:\...\python.exe build_security_matrix.py
"""
from __future__ import annotations

import json
import os
import sys
import inspect
from typing import Any, Dict, List, Tuple

REPO_ROOT = r"F:\AI\Jarvis-super-intelligence-"
sys.path.insert(0, REPO_ROOT)

import jarvis_backend.main as main_mod  # noqa: E402

OUT = os.path.join(REPO_ROOT, ".jarvis/platform-audit/security-matrix.json")


def _base(method: str, path: str, *, read_write: str, sensitive: bool,
          destructive: bool, auth: str, role: str, mechanism: str,
          audit: str, cred_risk: str, router: str, evidence: str) -> Dict[str, Any]:
    return {
        "router": router,
        "method": method,
        "path": path,
        "read_write": read_write,
        "sensitive": sensitive,
        "destructive": destructive,
        "authentication_required": auth,
        "authorization_required": role,
        "current_dependency": mechanism,
        "current_security_mechanism": mechanism,
        "required_role_policy": role,
        "audit_requirement": audit,
        "credential_exposure_risk": cred_risk,
        "evidence_verified": bool(evidence),
        "evidence_note": evidence or "rule-based classification; router not individually reviewed",
    }


OVR: Dict[Tuple[str, str], Dict[str, Any]] = {}

# --- main.py routes ---
OVR[("GET", "/")] = _base("GET", "/", read_write="read", sensitive=False, destructive=False,
                          auth="none", role="public", mechanism="none", audit="none", cred_risk="none",
                          router="main", evidence="liveness probe")
OVR[("GET", "/silverwing/health")] = _base("GET", "/silverwing/health", read_write="read",
                                            sensitive=False, destructive=False, auth="none", role="public",
                                            mechanism="none", audit="none", cred_risk="none", router="main",
                                            evidence="silverwing liveness bridge")
OVR[("GET", "/api/v1/status")] = _base("GET", "/api/v1/status", read_write="read", sensitive=False,
                                       destructive=False, auth="none", role="public", mechanism="none",
                                       audit="none", cred_risk="none", router="main", evidence="platform status probe")

# --- health.py ---
for _m, _p, _ev in [("GET", "/health", "liveness"), ("GET", "/api/ping", "liveness"),
                    ("GET", "/api/version", "version"), ("GET", "/api/v1/health/status", "health")]:
    OVR[(_m, _p)] = _base(_m, _p, read_write="read", sensitive=False, destructive=False, auth="none",
                          role="public", mechanism="none", audit="none", cred_risk="none", router="health",
                          evidence=_ev)

# --- auth.py ---
OVR[("POST", "/api/v1/auth/login")] = _base("POST", "/api/v1/auth/login", read_write="write",
                                            sensitive=False, destructive=False, auth="none",
                                            role="public (auth-by-design)", mechanism="password verify PBKDF2",
                                            audit="auth.login", cred_risk="none", router="auth",
                                            evidence="login issues tokens (no pre-auth needed)")
OVR[("POST", "/api/v1/auth/register")] = _base("POST", "/api/v1/auth/register", read_write="write",
                                               sensitive=False, destructive=False, auth="none",
                                               role="public (registration allowed)", mechanism="password hash PBKDF2",
                                               audit="auth.register", cred_risk="none", router="auth",
                                               evidence="user self-enroll")
OVR[("POST", "/api/v1/auth/refresh")] = _base("POST", "/api/v1/auth/refresh", read_write="write",
                                              sensitive=False, destructive=False, auth="none",
                                              role="public (refresh-token bearer)", mechanism="refresh-token jti",
                                              audit="auth.refresh", cred_risk="none", router="auth",
                                              evidence="refresh-token rotation")
OVR[("POST", "/api/v1/auth/forgot-password")] = _base("POST", "/api/v1/auth/forgot-password",
                                                       read_write="write", sensitive=False, destructive=False,
                                                       auth="none", role="public", mechanism="none",
                                                       audit="auth.forgot_password", cred_risk="none", router="auth",
                                                       evidence="tokenless reset request")
OVR[("POST", "/api/v1/auth/reset-password")] = _base("POST", "/api/v1/auth/reset-password",
                                                      read_write="write", sensitive=False, destructive=False,
                                                      auth="none", role="public (reset-token bearer)",
                                                      mechanism="reset-token verify", audit="auth.reset_password",
                                                      cred_risk="none", router="auth", evidence="reset token")
for _m, _p, _ev in [("POST", "/api/v1/auth/logout", "authenticated"),
                    ("POST", "/api/v1/auth/change-password", "authenticated")]:
    OVR[(_m, _p)] = _base(_m, _p, read_write="write", sensitive=False, destructive=False, auth=_ev,
                          role="authenticated", mechanism="Bearer get_current_user",
                          audit="auth." + (_p.split("/")[-1].replace("-", "_")), cred_risk="none",
                          router="auth", evidence="self " + _p.split("/")[-1])
OVR[("GET", "/api/v1/auth/me")] = _base("GET", "/api/v1/auth/me", read_write="read", sensitive=False,
                                        destructive=False, auth="authenticated", role="authenticated",
                                        mechanism="Bearer get_current_user", audit="auth.me", cred_risk="none",
                                        router="auth", evidence="self view")
OVR[("PUT", "/api/v1/auth/me")] = _base("PUT", "/api/v1/auth/me", read_write="write", sensitive=False,
                                        destructive=False, auth="authenticated", role="authenticated",
                                        mechanism="Bearer get_current_user", audit="auth.update_me",
                                        cred_risk="none", router="auth", evidence="self update")
OVR[("GET", "/api/v1/auth/sessions")] = _base("GET", "/api/v1/auth/sessions", read_write="read",
                                               sensitive=False, destructive=False, auth="authenticated",
                                               role="authenticated", mechanism="Bearer get_current_user",
                                               audit="auth.list_sessions", cred_risk="none", router="auth",
                                               evidence="self sessions")
OVR[("DELETE", "/api/v1/auth/sessions/{session_id}")] = _base("DELETE", "/api/v1/auth/sessions/{session_id}",
                                                               read_write="write", sensitive=False, destructive=True,
                                                               auth="authenticated", role="authenticated",
                                                               mechanism="Bearer get_current_user",
                                                               audit="auth.revoke_session", cred_risk="none",
                                                               router="auth", evidence="self session revoke")
OVR[("DELETE", "/api/v1/auth/sessions")] = _base("DELETE", "/api/v1/auth/sessions", read_write="write",
                                                  sensitive=False, destructive=True, auth="authenticated",
                                                  role="authenticated", mechanism="Bearer get_current_user",
                                                  audit="auth.revoke_sessions", cred_risk="none", router="auth",
                                                  evidence="bulk session revoke")
OVR[("GET", "/api/v1/auth/api-keys")] = _base("GET", "/api/v1/auth/api-keys", read_write="read",
                                              sensitive=False, destructive=False, auth="authenticated",
                                              role="authenticated", mechanism="Bearer get_current_user",
                                              audit="auth.list_api_keys", cred_risk="none", router="auth",
                                              evidence="self keys; raw never persisted (PBKDF2)")
OVR[("POST", "/api/v1/auth/api-keys")] = _base("POST", "/api/v1/auth/api-keys", read_write="write",
                                               sensitive=False, destructive=False, auth="authenticated",
                                               role="authenticated", mechanism="Bearer get_current_user",
                                               audit="auth.create_api_key", cred_risk="none", router="auth",
                                               evidence="create key; raw shown once")
OVR[("DELETE", "/api/v1/auth/api-keys/{key_id}")] = _base("DELETE", "/api/v1/auth/api-keys/{key_id}",
                                                           read_write="write", sensitive=False, destructive=True,
                                                           auth="authenticated", role="authenticated",
                                                           mechanism="Bearer get_current_user",
                                                           audit="auth.delete_api_key", cred_risk="none",
                                                           router="auth", evidence="delete key")
OVR[("POST", "/api/v1/auth/api-keys/{key_id}/rotate")] = _base("POST", "/api/v1/auth/api-keys/{key_id}/rotate",
                                                               read_write="write", sensitive=False, destructive=False,
                                                               auth="authenticated", role="authenticated",
                                                               mechanism="Bearer get_current_user",
                                                               audit="auth.rotate_api_key", cred_risk="none",
                                                               router="auth", evidence="rotate key")

# --- system.py (P4 source-reviewed) ---
OVR[("GET", "/api/v1/system/status")] = _base("GET", "/api/v1/system/status", read_write="read",
                                              sensitive=True, destructive=False, auth="authenticated",
                                              role="privileged-host", mechanism="none (UNAUTH currently)",
                                              audit="system.status", cred_risk="none", router="system",
                                              evidence="host fingerprint; gate P4")
OVR[("GET", "/api/v1/system/capabilities")] = _base("GET", "/api/v1/system/capabilities",
                                                     read_write="read", sensitive=False, destructive=False,
                                                     auth="none", role="public", mechanism="none",
                                                     audit="none (regression gate)", cred_risk="none", router="system",
                                                     evidence="capability registry; no secrets")
OVR[("GET", "/api/v1/system/dashboard")] = _base("GET", "/api/v1/system/dashboard", read_write="read",
                                                 sensitive=True, destructive=False, auth="none", role="public",
                                                 mechanism="none", audit="system.dashboard", cred_risk="none",
                                                 router="system", evidence="platform state; reads audit_logs; regression gate")
OVR[("GET", "/api/v1/system/processes")] = _base("GET", "/api/v1/system/processes", read_write="read",
                                                 sensitive=True, destructive=False, auth="authenticated",
                                                 role="privileged-host", mechanism="none (UNAUTH currently)",
                                                 audit="system.processes", cred_risk="none", router="system",
                                                 evidence="psutil host process list; gate P4")
OVR[("POST", "/api/v1/system/processes/kill")] = _base("POST", "/api/v1/system/processes/kill",
                                                       read_write="write", sensitive=True, destructive=True,
                                                       auth="authenticated", role="privileged-host",
                                                       mechanism="none (UNAUTH currently)", audit="system.process_kill",
                                                       cred_risk="none", router="system",
                                                       evidence="host process kill; deny-list")
OVR[("POST", "/api/v1/system/process/kill")] = _base("POST", "/api/v1/system/process/kill",
                                                    read_write="write", sensitive=True, destructive=True,
                                                    auth="authenticated", role="privileged-host",
                                                    mechanism="none (UNAUTH currently)", audit="system.process_kill",
                                                    cred_risk="none", router="system", evidence="alias of processes/kill")
OVR[("GET", "/api/v1/system/provider-settings")] = _base("GET", "/api/v1/system/provider-settings",
                                                          read_write="read", sensitive=True, destructive=False,
                                                          auth="authenticated", role="privileged-host",
                                                          mechanism="none (UNAUTH + PLAINTEXT currently)",
                                                          audit="system.provider_settings",
                                                          cred_risk="HIGH (plaintext secret names+values returned)",
                                                          router="system", evidence="gate P4 + metadata-only GET P6/P7")
OVR[("PUT", "/api/v1/system/provider-settings")] = _base("PUT", "/api/v1/system/provider-settings",
                                                          read_write="write", sensitive=True, destructive=False,
                                                          auth="authenticated", role="privileged-host",
                                                          mechanism="none (UNAUTH + PLAINTEXT currently)",
                                                          audit="provider.updated", cred_risk="HIGH (writes plaintext secrets)",
                                                          router="system", evidence="gate P4 + Fernet-encrypt secret-shaped fields P6/P7")
OVR[("GET", "/api/v1/system/files")] = _base("GET", "/api/v1/system/files", read_write="read",
                                             sensitive=True, destructive=False, auth="authenticated",
                                             role="privileged-host", mechanism="none (UNAUTH currently)",
                                             audit="system.files_list", cred_risk="path disclosure", router="system",
                                             evidence="arbitrary FS list (default ROOT); path-confine P4")
OVR[("POST", "/api/v1/system/files/read")] = _base("POST", "/api/v1/system/files/read",
                                                    read_write="read", sensitive=True, destructive=False,
                                                    auth="authenticated", role="privileged-host",
                                                    mechanism="none (UNAUTH currently)", audit="system.file_read",
                                                    cred_risk="arbitrary file read", router="system",
                                                    evidence="arbitrary file read; path-confine P4")
OVR[("GET", "/api/v1/system/clipboard")] = _base("GET", "/api/v1/system/clipboard", read_write="read",
                                                 sensitive=True, destructive=False, auth="authenticated",
                                                 role="privileged-host", mechanism="none (UNAUTH currently)",
                                                 audit="system.clipboard_read", cred_risk="host clipboard leak",
                                                 router="system", evidence="host clipboard contents; gate P4")
OVR[("POST", "/api/v1/system/clipboard")] = _base("POST", "/api/v1/system/clipboard", read_write="write",
                                                  sensitive=True, destructive=False, auth="authenticated",
                                                  role="privileged-host", mechanism="none (UNAUTH currently)",
                                                  audit="system.clipboard_write", cred_risk="host clipboard write",
                                                  router="system", evidence="host clipboard set; gate P4")
OVR[("POST", "/api/v1/system/launch")] = _base("POST", "/api/v1/system/launch", read_write="write",
                                               sensitive=True, destructive=True, auth="authenticated",
                                               role="privileged-host", mechanism="deny-list first (403), then auth",
                                               audit="system_launch (allowed/denied)", cred_risk="host command exec",
                                               router="system", evidence="deny-list BEFORE auth; shutdown->403 preserved P4")
OVR[("GET", "/api/v1/system/launch/apps")] = _base("GET", "/api/v1/system/launch/apps", read_write="read",
                                                   sensitive=False, destructive=False, auth="authenticated",
                                                   role="authenticated", mechanism="none (UNAUTH currently)",
                                                   audit="system.launch_apps", cred_risk="none", router="system",
                                                   evidence="static app list; gate P4")
OVR[("POST", "/api/v1/system/screenshot")] = _base("POST", "/api/v1/system/screenshot", read_write="write",
                                                   sensitive=True, destructive=False, auth="authenticated",
                                                   role="privileged-host", mechanism="none (UNAUTH currently)",
                                                   audit="system.screenshot", cred_risk="host screen capture",
                                                   router="system", evidence="host screenshot; gate P4")
OVR[("GET", "/api/v1/system/windows")] = _base("GET", "/api/v1/system/windows", read_write="read",
                                               sensitive=True, destructive=False, auth="authenticated",
                                               role="privileged-host", mechanism="none (UNAUTH currently)",
                                               audit="system.windows", cred_risk="host window enumeration",
                                               router="system", evidence="host windows via powershell; gate P4")
OVR[("GET", "/api/v1/system/file-structure")] = _base("GET", "/api/v1/system/file-structure",
                                                       read_write="read", sensitive=True, destructive=False,
                                                       auth="authenticated", role="privileged-host",
                                                       mechanism="none (UNAUTH currently)", audit="system.file_structure",
                                                       cred_risk="host FS tree disclosure", router="system",
                                                       evidence="_walk(ROOT,2); gate P4")

# --- platform_identity.py (P7 verified) ---
OVR[("GET", "/api/v1/platform/identity")] = _base("GET", "/api/v1/platform/identity", read_write="read",
                                                  sensitive=False, destructive=False, auth="none",
                                                  role="public (safe metadata only)", mechanism="none",
                                                  audit="none (regression gate)", cred_risk="none", router="platform_identity",
                                                  evidence="GET returns no secrets; _SECRET_LEAK_MARKERS present")
OVR[("PUT", "/api/v1/platform/identity")] = _base("PUT", "/api/v1/platform/identity", read_write="write",
                                                  sensitive=True, destructive=False, auth="authenticated",
                                                  role="privileged-host", mechanism="secret-shape rejection (L118)",
                                                  audit="identity.updated", cred_risk="none (secrets rejected)",
                                                  router="platform_identity",
                                                  evidence="PUT rejects secret-shaped field; audits kind=identity action=updated")
for _m, _p, _ev in [("GET", "/api/v1/platform/identity/capabilities", "safe metadata"),
                    ("GET", "/api/v1/platform/identity/providers", "provider names only")]:
    OVR[(_m, _p)] = _base(_m, _p, read_write="read", sensitive=False, destructive=False, auth="none",
                          role="public", mechanism="none", audit="none", cred_risk="none", router="platform_identity",
                          evidence=_ev)

# --- rbac.py (source-reviewed; already auth-gated) ---
OVR[("GET", "/api/v1/rbac/users")] = _base("GET", "/api/v1/rbac/users", read_write="read", sensitive=True,
                                           destructive=False, auth="authenticated", role="admin",
                                           mechanism="Depends(_require_admin)", audit="rbac.list_users",
                                           cred_risk="user enumeration", router="rbac", evidence="admin-gated")
OVR[("POST", "/api/v1/rbac/users")] = _base("POST", "/api/v1/rbac/users", read_write="write", sensitive=True,
                                            destructive=False, auth="authenticated", role="admin",
                                            mechanism="Depends(_require_admin)", audit="rbac.create_user",
                                            cred_risk="user creation (password)", router="rbac", evidence="admin-gated")
for _m, _p in [("PUT", "/api/v1/rbac/users/{user_id}"), ("DELETE", "/api/v1/rbac/users/{user_id}")]:
    OVR[(_m, _p)] = _base(_m, _p, read_write="write", sensitive=True, destructive=(_m == "DELETE"),
                          auth="authenticated", role="admin", mechanism="Depends(_require_admin)",
                          audit="rbac." + ("update_user" if _m == "PUT" else "delete_user"),
                          cred_risk="user mgmt", router="rbac", evidence="admin-gated")
OVR[("GET", "/api/v1/rbac/roles")] = _base("GET", "/api/v1/rbac/roles", read_write="read", sensitive=False,
                                           destructive=False, auth="authenticated", role="authenticated",
                                           mechanism="Depends(_require_auth)", audit="rbac.list_roles",
                                           cred_risk="none", router="rbac", evidence="authenticated read")
for _m, _p, _a in [("POST", "/api/v1/rbac/roles", "create_role"),
                   ("PUT", "/api/v1/rbac/roles/{role_id}", "update_role"),
                   ("DELETE", "/api/v1/rbac/roles/{role_id}", "delete_role")]:
    OVR[(_m, _p)] = _base(_m, _p, read_write="write", sensitive=True, destructive=(_m == "DELETE"),
                          auth="authenticated", role="admin", mechanism="Depends(_require_admin)",
                          audit="rbac." + _a, cred_risk="privilege mgmt", router="rbac", evidence="admin-gated")
for _m, _p, _a in [("GET", "/api/v1/rbac/permissions", "list_permissions"),
                   ("GET", "/api/v1/rbac/audit-logs", "list_audit_logs"),
                   ("GET", "/api/v1/rbac/audit-logs/export", "export_audit_logs")]:
    _role = "admin" if _p != "/api/v1/rbac/permissions" else "authenticated"
    _mech = "Depends(_require_admin)" if _p != "/api/v1/rbac/permissions" else "Depends(_require_auth)"
    OVR[(_m, _p)] = _base(_m, _p, read_write="read", sensitive=(_p != "/api/v1/rbac/permissions"),
                          destructive=False, auth="authenticated", role=_role, mechanism=_mech,
                          audit="rbac." + _a, cred_risk="audit/perm disclosure", router="rbac", evidence="gated")
OVR[("GET", "/api/v1/rbac/tenant/settings")] = _base("GET", "/api/v1/rbac/tenant/settings", read_write="read",
                                                      sensitive=False, destructive=False, auth="authenticated",
                                                      role="authenticated", mechanism="Depends(_require_auth)",
                                                      audit="rbac.tenant_settings", cred_risk="none", router="rbac",
                                                      evidence="authenticated read")
OVR[("PUT", "/api/v1/rbac/tenant/settings")] = _base("PUT", "/api/v1/rbac/tenant/settings", read_write="write",
                                                     sensitive=True, destructive=False, auth="authenticated",
                                                     role="admin", mechanism="Depends(_require_admin)",
                                                     audit="rbac.update_tenant_settings", cred_risk="config",
                                                     router="rbac", evidence="admin-gated")

# --- stark.py (source-reviewed stub) ---
OVR[("POST", "/api/v1/stark/tool")] = _base("POST", "/api/v1/stark/tool", read_write="write", sensitive=True,
                                            destructive=False, auth="authenticated", role="authenticated",
                                            mechanism="none (UNAUTH currently — STUB)", audit="stark.tool",
                                            cred_risk="none (echoes params, no exec)", router="stark",
                                            evidence="stark_tool echoes params only; gate P3 boundary")
OVR[("POST", "/api/v1/stark/chat")] = _base("POST", "/api/v1/stark/chat", read_write="write", sensitive=True,
                                            destructive=False, auth="authenticated", role="authenticated",
                                            mechanism="none (UNAUTH currently)", audit="stark.chat", cred_risk="none",
                                            router="stark", evidence="calls ai_service.chat")
OVR[("GET", "/api/v1/stark/status")] = _base("GET", "/api/v1/stark/status", read_write="read", sensitive=True,
                                             destructive=False, auth="authenticated", role="authenticated",
                                             mechanism="none (UNAUTH currently)", audit="stark.status",
                                             cred_risk="config (ai_service.settings)", router="stark",
                                             evidence="returns ai_service.settings() — gate P3")
OVR[("GET", "/api/v1/stark/health")] = _base("GET", "/api/v1/stark/health", read_write="read", sensitive=False,
                                             destructive=False, auth="none", role="public", mechanism="none",
                                             audit="none", cred_risk="none", router="stark", evidence="liveness")

# --- ai.py (source-reviewed) ---
OVR[("POST", "/api/v1/ai/process")] = _base("POST", "/api/v1/ai/process", read_write="write", sensitive=True,
                                            destructive=False, auth="authenticated", role="authenticated",
                                            mechanism="none (UNAUTH currently)", audit="ai.process",
                                            cred_risk="model invocation / abuse", router="ai",
                                            evidence="provider_gateway.chat; frontend chat path — documented debt (gating risks breaking chat)")
OVR[("POST", "/api/v1/ai/generate")] = _base("POST", "/api/v1/ai/generate", read_write="write", sensitive=False,
                                             destructive=False, auth="authenticated", role="authenticated",
                                             mechanism="none", audit="none", cred_risk="none", router="ai",
                                             evidence="HTTP 410 deprecated")
OVR[("POST", "/api/v1/ai/feedback")] = _base("POST", "/api/v1/ai/feedback", read_write="write", sensitive=False,
                                              destructive=False, auth="authenticated", role="authenticated",
                                              mechanism="none (UNAUTH currently)", audit="ai.feedback", cred_risk="none",
                                              router="ai", evidence="writes feedback store")
OVR[("GET", "/api/v1/ai/models")] = _base("GET", "/api/v1/ai/models", read_write="read", sensitive=False,
                                          destructive=False, auth="authenticated", role="authenticated",
                                          mechanism="none (UNAUTH currently)", audit="ai.models", cred_risk="none",
                                          router="ai", evidence="provider/model catalog (metadata only)")
OVR[("GET", "/api/v1/ai/status")] = _base("GET", "/api/v1/ai/status", read_write="read", sensitive=True,
                                          destructive=False, auth="authenticated", role="authenticated",
                                          mechanism="none (UNAUTH currently)", audit="ai.status",
                                          cred_risk="config (brain_api_key_configured bool only)", router="ai",
                                          evidence="returns bool, not the key value")
OVR[("POST", "/api/v1/ai/tasks")] = _base("POST", "/api/v1/ai/tasks", read_write="write", sensitive=True,
                                          destructive=False, auth="authenticated", role="authenticated",
                                          mechanism="none (UNAUTH currently)", audit="ai.create_task",
                                          cred_risk="task scheduling", router="ai", evidence="task store")
OVR[("GET", "/api/v1/ai/tasks")] = _base("GET", "/api/v1/ai/tasks", read_write="read", sensitive=True,
                                         destructive=False, auth="authenticated", role="authenticated",
                                         mechanism="none (UNAUTH currently)", audit="ai.list_tasks",
                                         cred_risk="task data", router="ai", evidence="task store read")
OVR[("POST", "/api/v1/llm/chat")] = _base("POST", "/api/v1/llm/chat", read_write="write", sensitive=False,
                                          destructive=False, auth="authenticated", role="authenticated",
                                          mechanism="none", audit="none", cred_risk="none", router="ai",
                                          evidence="HTTP 410 deprecated")
OVR[("GET", "/api/v1/llm/status")] = _base("GET", "/api/v1/llm/status", read_write="read", sensitive=True,
                                           destructive=False, auth="authenticated", role="authenticated",
                                           mechanism="none (UNAUTH currently)", audit="llm.status",
                                           cred_risk="config", router="ai", evidence="ai_service.settings()")

# routers authenticated by source (P1 grep evidence), not individually classified
_AUTHED_ROUTERS = {
    "agents": ("authenticated", "Bearer get_current_user"),
    "browser": ("authenticated", "Bearer get_current_user"),
    "connectors": ("authenticated", "Bearer get_current_user + _require_admin(mutations)"),
    "automation": ("authenticated", "Bearer get_current_user + _require_admin_or_dev"),
    "developer": ("authenticated", "Bearer get_current_user + _require_admin(writes)"),
    "extensions": ("authenticated", "Bearer get_current_user + _require_admin(mutations)"),
    "legacy": ("authenticated", "Bearer get_current_user"),
    "search": ("authenticated", "Bearer get_current_user"),
    "sandbox": ("authenticated", "Bearer get_current_user"),
}

# routers NOT authenticated, rule-based classification
_UNAUTH_ROUTERS = {
    "misc": "none (UNAUTH — debt)",
    "billing": "none (UNAUTH — debt)",
    "global_knowledge": "none (UNAUTH — debt)",
    "knowledge": "none (UNAUTH — debt)",
    "memory": "none (UNAUTH — debt)",
    "multimodal": "none (UNAUTH — debt)",
    "media": "none (UNAUTH — debt)",
    "voice": "none (UNAUTH — debt)",
    "codegen": "none (UNAUTH — debt)",
    "monitoring": "none (UNAUTH — debt)",
}


def _rule_classify(method, path, module, tags):
    router = module.rsplit(".", 1)[-1]
    is_write = method in ("POST", "PUT", "DELETE", "PATCH")
    read_write = "write" if is_write else "read"
    if module.startswith("fastapi") or path in ("/docs", "/redoc", "/docs/oauth2-redirect", "/openapi.json"):
        return {"router": "framework", "read_write": read_write, "sensitive": False, "destructive": False,
                "authentication_required": "none", "authorization_required": "public",
                "current_dependency": "none", "current_security_mechanism": "none",
                "required_role_policy": "public", "audit_requirement": "none",
                "credential_exposure_risk": "none", "evidence_verified": True,
                "evidence_note": "FastAPI auto-generated OpenAPI/docs (disable in prod)"}
    if router == "health":
        return {"router": "health", "read_write": read_write, "sensitive": False, "destructive": False,
                "authentication_required": "none", "authorization_required": "public",
                "current_dependency": "none", "current_security_mechanism": "none",
                "required_role_policy": "public", "audit_requirement": "none",
                "credential_exposure_risk": "none", "evidence_verified": True,
                "evidence_note": "liveness probe"}
    if router in _AUTHED_ROUTERS:
        _auth, _mech = _AUTHED_ROUTERS[router]
        if router == "automation":
            role = "developer-or-admin" if is_write else "authenticated"
        elif router in ("connectors", "developer", "extensions") and is_write:
            role = "admin"
        else:
            role = "authenticated"
        return {"router": router, "read_write": read_write, "sensitive": is_write, "destructive": method == "DELETE",
                "authentication_required": _auth, "authorization_required": role,
                "current_dependency": _mech, "current_security_mechanism": _mech,
                "required_role_policy": role, "audit_requirement": "sensitive" if is_write else "none",
                "credential_exposure_risk": "none", "evidence_verified": True,
                "evidence_note": "router imports get_current_user (P1 grep evidence)"}
    if router in _UNAUTH_ROUTERS:
        return {"router": router, "read_write": read_write, "sensitive": is_write, "destructive": method == "DELETE",
                "authentication_required": "authenticated (TODO)", "authorization_required": "authenticated",
                "current_dependency": "none (UNAUTH)", "current_security_mechanism": _UNAUTH_ROUTERS[router],
                "required_role_policy": "authenticated", "audit_requirement": "sensitive" if is_write else "none",
                "credential_exposure_risk": "none", "evidence_verified": False,
                "evidence_note": "not individually source-reviewed; classify before hardening"}
    if module.startswith("identity"):
        role = "admin" if path.startswith("/api/v1/admin") else "authenticated"
        return {"router": "identity (external OIDC)", "read_write": read_write, "sensitive": True,
                "destructive": is_write, "authentication_required": "authenticated", "authorization_required": role,
                "current_dependency": "OIDC session", "current_security_mechanism": "external identity package",
                "required_role_policy": role, "audit_requirement": "sensitive" if is_write else "none",
                "credential_exposure_risk": "none", "evidence_verified": False,
                "evidence_note": "external identity.router package; requires OIDC security review (P14)"}
    return {"router": router, "read_write": read_write, "sensitive": is_write, "destructive": method == "DELETE",
            "authentication_required": "authenticated (TODO)", "authorization_required": "authenticated",
            "current_dependency": "unknown", "current_security_mechanism": "unknown",
            "required_role_policy": "authenticated", "audit_requirement": "sensitive" if is_write else "none",
            "credential_exposure_risk": "none", "evidence_verified": False,
            "evidence_note": "unreviewed endpoint; classify before relying on this entry"}


def main() -> int:
    app = main_mod.app
    routes: List[Dict[str, Any]] = []
    for r in app.routes:
        if getattr(r, "methods", None) is None:
            continue
        path = r.path
        endpoint = getattr(r, "endpoint", None)
        module = ""
        if endpoint is not None:
            try:
                module = inspect.getmodule(endpoint).__name__
            except Exception:
                module = ""
        tags = list(getattr(r, "tags", []) or [])
        for m in r.methods:
            if m == "HEAD":
                continue
            key = (m, path)
            rec = dict(OVR[key]) if key in OVR else _rule_classify(m, path, module, tags)
            rec["method"] = m
            rec["path"] = path
            routes.append(rec)
    seen = set()
    out = []
    for r in routes:
        k = (r["method"], r["path"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    out.sort(key=lambda x: (x["router"], x["method"], x["path"]))
    doc = {
        "schema_version": "1.0",
        "generated_by": "SEC-1 P2 build_security_matrix.py",
        "generated_at": __import__("datetime").datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "total_endpoints": len(out),
        "note": ("Per-endpoint security matrix for the JARVIS backend. "
                 "'current_security_mechanism' records LIVE behavior at build time; "
                 "'required_role_policy' is the SEC-1 target. Entries with "
                 "evidence_verified=false are rule-based and must be source-reviewed "
                 "before reliance. This matrix is the input to P3-P10 gating."),
        "authorization_tiers": {
            "public": "no authentication required (liveness / platform metadata)",
            "authenticated": "any valid bearer token (get_current_user)",
            "authenticated (normal user)": "authenticated; normal-user scope",
            "developer": "developer or admin role (automation/tooling endpoints)",
            "admin": "admin/owner role; write to roles, users, connectors, system host ops",
            "privileged-host": "admin/owner for host operations (system.py); deny-list enforced before auth on /launch",
        },
        "regression_gates": {
            "public_endpoints": [
                "/api/v1/system/capabilities", "/api/v1/system/dashboard",
                "/api/v1/platform/identity", "/", "/health", "/api/ping",
                "/api/version", "/api/v1/health/status", "/api/v1/status",
                "/silverwing/health", "/api/v1/stark/health",
            ],
            "shutdown_lockdown": "POST /api/v1/system/launch {\"app\":\"shutdown\"} -> 403 (deny-list enforced before auth)",
        },
        "endpoints": out,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    print(f"WROTE {OUT}")
    print(f"total endpoints: {len(out)}")
    from collections import Counter
    c = Counter((r["authentication_required"], r["required_role_policy"]) for r in out)
    for k, v in sorted(c.items()):
        print(f"  auth={k[0]!r:42} role={k[1]!r:34} -> {v}")
    # spotlight the high-risk currently-unauth
    print("HIGH-RISK currently-unauth endpoints:")
    for r in out:
        cur = r.get("current_security_mechanism", "") or r.get("current_dependency", "")
        if ("UNAUTH" in cur or "none (UNAUTH" in str(cur)) and r.get("sensitive"):
            print(f"  {r['method']:6} {r['path']:46} router={r['router']} cred_risk={r['credential_exposure_risk']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
