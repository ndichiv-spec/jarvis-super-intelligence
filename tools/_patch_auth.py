from pathlib import Path

p = Path("jarvis_backend/routers/auth.py")
c = p.read_text(encoding="utf-8")

# --- Hunk 1: extend core imports for API-key helpers ---
imp_old = '''from ..core import (
    create_refresh_token,
    create_token,
    decode_token,
    get_current_user,
    get_optional_user,
    get_store,
    hash_password,
    is_api_key_expired,
    iso_expire_at,
    make_user_payload,
    now_iso,
    refresh_access_token,
    revoke_refresh_token,
    verify_password,
)
'''
imp_new = '''from ..core import (
    _strip_key_secrets,
    api_key_prefix,
    create_refresh_token,
    create_token,
    decode_token,
    generate_api_key,
    get_current_user,
    get_optional_user,
    get_store,
    hash_password,
    is_api_key_expired,
    iso_expire_at,
    make_user_payload,
    now_iso,
    refresh_access_token,
    revoke_refresh_token,
    verify_password,
)
'''
assert c.count(imp_old) == 1, f"import match count = {c.count(imp_old)}"
c = c.replace(imp_old, imp_new)

# --- Hunk 2: rewrite list/create/delete api-key routes + add rotate ---
routes_old = '''@router.get("/api-keys")
async def list_api_keys(user: Dict[str, Any] = Depends(get_current_user)):
    keys = get_store("api_keys").load()
    mine = []
    for item in keys.values():
        if item.get("user_id") != user["id"]:
            continue
        record = {k: v for k, v in item.items() if k != "key"}
        # Never echo the raw key; compute a client-facing expiry status instead.
        record["expired"] = is_api_key_expired(item)
        mine.append(record)
    return {"api_keys": mine}


@router.post("/api-keys")
async def create_api_key(body: ApiKeyCreate, user: Dict[str, Any] = Depends(get_current_user)):
    keys = get_store("api_keys").load()
    key_id = str(uuid.uuid4())
    raw_key = "jarvis_" + secrets.token_hex(24)
    keys[key_id] = {
        "id": key_id,
        "user_id": user["id"],
        "name": body.name,
        "description": body.description,
        "scopes": body.scopes or [],
        "key": raw_key,
        "created_at": now_iso(),
        "expires_at": iso_expire_at(body.expires_in_days) if body.expires_in_days else None,
    }
    get_store("api_keys").save()
    _audit(user["id"], "create_api_key", body.name)
    # Return the raw key ONLY here (creator retrieves it once). The persisted
    # record keeps the plaintext ``key`` for now; list_api_keys never exposes it.
    safe = {k: v for k, v in keys[key_id].items() if k != "key"}
    return {"api_key": safe, "raw_key": raw_key}


@router.delete("/api-keys/{key_id}")
async def delete_api_key(key_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    keys = get_store("api_keys").load()
    if key_id in keys and keys[key_id].get("user_id") == user["id"]:
        keys.pop(key_id, None)
        get_store("api_keys").save()
        _audit(user["id"], "delete_api_key")
    return {"success": True}
'''
routes_new = '''def _require_admin(user: Dict[str, Any]) -> Dict[str, Any]:
    """Gate to admin (roles or explicit is_admin). Mirrors the helpers in the
    rbac/connectors/developer/extensions routers so API-key principals whose
    ``is_admin`` is derived from their ``admin`` scope are treated identically."""
    names = [r for r in (user.get("roles") or []) if isinstance(r, str)]
    if "admin" in names or user.get("is_admin"):
        return user
    raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/api-keys")
async def list_api_keys(user: Dict[str, Any] = Depends(get_current_user)):
    keys = get_store("api_keys").load()
    mine = []
    for item in keys.values():
        owner = item.get("owner") or item.get("user_id")
        if owner != user["id"]:
            continue
        # Never echo the raw key or its hash; surface only safe metadata (sections
        # 5 / 7 / 14).
        record = _strip_key_secrets(item)
        record["expired"] = is_api_key_expired(item)
        record.setdefault("prefix", item.get("prefix"))
        record.setdefault("status", item.get("status", "active"))
        record.setdefault("last_used_at", item.get("last_used_at"))
        mine.append(record)
    return {"api_keys": mine}


@router.post("/api-keys")
async def create_api_key(body: ApiKeyCreate, user: Dict[str, Any] = Depends(get_current_user)):
    _require_admin(user)
    raw_key, key_hash = generate_api_key()
    key_id = str(uuid.uuid4())
    keys = get_store("api_keys").load()
    keys[key_id] = {
        "id": key_id,
        "key_id": key_id,
        "user_id": user["id"],
        "owner": user["id"],
        "name": body.name,
        "description": body.description,
        "scopes": body.scopes or [],
        "prefix": api_key_prefix(raw_key),
        "hash": key_hash,
        "created_at": now_iso(),
        "expires_at": iso_expire_at(body.expires_in_days) if body.expires_in_days else None,
        "last_used_at": None,
        "status": "active",
    }
    get_store("api_keys").save()
    _audit(user["id"], "create_api_key", body.name)
    # The raw key is shown ONCE; it is never persisted or returned elsewhere (#5/#6/#8).
    safe = _strip_key_secrets(keys[key_id])
    return {
        "key_id": key_id,
        "prefix": keys[key_id]["prefix"],
        "key": raw_key,
        "warning": "Store this key securely. It will not be shown again.",
        "api_key": safe,
    }


@router.delete("/api-keys/{key_id}")
async def delete_api_key(key_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    _require_admin(user)
    keys = get_store("api_keys").load()
    record = keys.get(key_id)
    if record:
        # Soft-revoke (retain metadata for audit; section 9).
        record["status"] = "revoked"
        record["revoked_at"] = now_iso()
        get_store("api_keys").save()
        _audit(user["id"], "revoke_api_key", record.get("prefix", key_id))
    return {"success": True}


@router.post("/api-keys/{key_id}/rotate")
async def rotate_api_key(key_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    _require_admin(user)
    keys = get_store("api_keys").load()
    old = keys.get(key_id)
    if not old:
        raise HTTPException(status_code=404, detail="API key not found")
    new_raw, new_hash = generate_api_key()
    new_id = str(uuid.uuid4())
    # Revoke the old key (metadata retained for audit); issue a fresh record.
    old["status"] = "revoked"
    old["revoked_at"] = now_iso()
    old["revoked_reason"] = "rotation"
    keys[key_id] = old
    keys[new_id] = {
        "id": new_id,
        "key_id": new_id,
        "user_id": old.get("user_id"),
        "owner": old.get("owner"),
        "name": old.get("name"),
        "description": old.get("description"),
        "scopes": old.get("scopes") or [],
        "prefix": api_key_prefix(new_raw),
        "hash": new_hash,
        "created_at": now_iso(),
        "expires_at": old.get("expires_at"),
        "last_used_at": None,
        "status": "active",
        "previous_key_id": key_id,
    }
    get_store("api_keys").save()
    _audit(user["id"], "rotate_api_key", old.get("prefix", key_id))
    safe = _strip_key_secrets(keys[new_id])
    return {
        "key_id": new_id,
        "prefix": keys[new_id]["prefix"],
        "key": new_raw,
        "warning": "Store this key securely. It will not be shown again.",
        "api_key": safe,
    }
'''
assert c.count(routes_old) == 1, f"routes match count = {c.count(routes_old)}"
c = c.replace(routes_old, routes_new)

p.write_text(c, encoding="utf-8")
print("auth.py patched OK")
