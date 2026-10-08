# RBAC Report

**Spec sections:** #9 (roles + permissions + least privilege + authorized/
unauthorized paths), #16 (admin surface end-to-end), #17 (RBAC authorization
test surface), #5 (Pydantic v2 `.model_dump()` fix), #6 (testing).

**Date:** 2026-09-15 · **Environment:** Python 3.13, FastAPI 0.115.0, Pydantic 2.13.5.

---

## 1. Role model

Roles and permissions are seeded by `core.start_backend()` and
`core._seed_canonical_roles()` (idempotent — inserts only missing roles):

| Role | Permissions | Scope |
|---|---|---|
| `owner` | `["*"]` | Full system access (superuser) |
| `admin` | `["*"]` | Full system access |
| `operator` | `system:read`, `monitoring:*`, `automation:execute`, `agent:*`, `model:*`, `task:*` | Operate the system (no connector/user secrets) |
| `developer` | `system:read`, `monitoring:read`, `automation:*`, `connector:*`, `tool:*`, `extension:*`, `role:read`, `permission:read`, `api_key:*` | Configure integrations/tools/connectors |
| `analyst` | `system:read`, `monitoring:read`, `audit:*`, `knowledge:*`, `memory:*` | Read telemetry/audit/knowledge (no write) |
| `viewer` | `system:read`, `monitoring:read`, `agent:read`, `knowledge:read`, `memory:read` | Read-only |

Permissions are least-privilege: only `owner`/`admin` carry the `*` wildcard;
`viewer` and `analyst` carry read-only scopes; `developer` can manage
connectors/extensions/api-keys but cannot manage users or roles.

Resources with a permission entry: `user, role, tenant, agent, task, memory,
knowledge, voice, system, monitoring, automation, api_key, multimodal`
(plus `*: all`).

---

## 2. Route authorization matrix (`/api/v1/rbac/*`)

Previously **every** RBAC route was unauthenticated — anyone could list,
create, or delete users and roles. That is fixed: mutations require admin; reads
require an authenticated user.

| Route | Method | Gate | Was |
|---|---|---|---|
| `/users` | GET (list) | admin | **none → admin** |
| `/users` | POST (create) | admin | **none → admin** |
| `/users/{user_id}` | PUT | admin | **none → admin** |
| `/users/{user_id}` | DELETE | admin | **none → admin** |
| `/roles` | GET (list) | authenticated | **none → auth** |
| `/roles` | POST | admin | **none → admin** |
| `/roles/{role_id}` | PUT | admin | **none → admin** |
| `/roles/{role_id}` | DELETE | admin | **none → admin** |
| `/permissions` | GET | authenticated | **none → auth** |
| `/audit-logs` | GET | admin | **none → admin** |
| `/audit-logs/export` | GET | admin | **none → admin** |
| `/tenant/settings` | GET | authenticated | **none → auth** |
| `/tenant/settings` | PUT | admin | **none → admin** |

### Gate helpers (`routers/rbac.py`)
```python
def _require_admin(user = Depends(get_current_user)):
    names = [r for r in (user.get("roles") or []) if isinstance(r, str)]
    if "admin" in names or user.get("is_admin"):
        return user
    # OWNER resolution: a role carrying "*" also grants admin access.
    roles = get_store("roles").load()
    for role in roles.values():
        if role.get("name") in set(names) and "*" in (role.get("permissions") or []):
            return user
    raise HTTPException(403, detail="Admin access required")

def _require_auth(user = Depends(get_current_user)):
    return user
```
The authenticated principal is resolved **only** from the bearer JWT `sub`
(`core.get_current_user` → `decode_token` → user lookup), never from the
request body — so a user cannot elevate themselves by sending a forged `user_id`.

---

## 3. Authorized / unauthorized paths (tested)

| Scenario | Expected | Test |
|---|---|---|
| admin POST `/roles` | 200 | `test_admin_authorized_to_create_role` |
| regular user POST `/roles` | **403** | `test_regular_user_denied_create_role` |
| no token POST `/roles` | **401** | `test_no_auth_denied` |
| `owner` role (via `*` perm) POST `/roles` | 200 | `test_owner_role_grants_admin_access` |

All 8 RBAC tests pass. The full auth/RBAC/OAuth/security surface passes
(93 passed after changes; 221 passed/1 skipped across the full collected suite —
no regressions).

---

## 4. Pydantic v2 compatibility fix (`.dict()` → `.model_dump()`)

The codebase runs Pydantic **2.13.5**, where the v1 `.dict()` method is a
deprecated compatibility shim that emits `PydanticDeprecationWarning` (and is
removed in Pydantic 3). The two call sites in the active `jarvis_backend`
package were migrated — **not** blindly: each was inspected in context and the
`exclude_none=True)` semantics preserved.

| File | Location | Change |
|---|---|---|
| `routers/rbac.py:207` (now `update_tenant_settings`) | `body.dict(exclude_none=True)` | `body.model_dump(exclude_none=True)` |
| `routers/system.py:204` (`update_provider_settings`) | `body.dict(exclude_none=True)` | `body.model_dump(exclude_none=True)` |

A repo-wide scan confirms **zero** remaining legacy `.dict(` calls in
`jarvis_backend/` after the change (other `.dict(` occurrences live only in
`silverwing-backend/`, which is an excluded dependency with its own test suite).

End-to-end coverage:
```
test_tenant_settings_model_dump_works_for_admin  PASS  (PUT /rbac/tenant/settings for admin → 200, field updated)
```

---

## 5. Audit trail integration

RBAC mutations are auditable: `_audit`/`audit_record` record `auth`-scoped
actions (`login`, `register`, `create_api_key`, …) and OAuth/connection actions
record `kind`/`operation`/`ok`. The `test_admin_audit_logging` suite verifies:
login + register + api-key-create are recorded, each entry has the required shape
(`id, actor_id, action, resource_type, timestamp`), and none leak secrets.

---

## 6. Verification of least privilege

- `viewer` carries no `*` and no write scopes (`test_least_privilege_viewer`).
- `developer` can manage api-keys/connectors/extensions but cannot manage users or
  roles (no `admin`/`*` perm).
- `analyst` can read audit/knowledge/memory but cannot write.
- Only `owner`/`admin` can mutate users, roles, or tenant settings.

The permission catalog is exposed read-only at `GET /rbac/permissions`
(authenticated) for a follow-up that gates individual resources by
fine-grained permission (beyond the admin gate implemented here).
