from __future__ import annotations

import json
import time
import uuid
from typing import Any

from sqlalchemy import insert, select, update

from .db import endpoint_audit_events, endpoints, ensure_schema, get_engine

VALID_CONTRACT_VERSIONS = {"1.0", "1.1"}
VALID_MODALITIES = {"text", "links", "image", "audio", "map", "video", "voice"}
SERVER_CAPABILITIES = {
    "presentation.text",
    "presentation.links",
    "presentation.image",
    "presentation.audio",
    "presentation.map",
    "presentation.video",
    "presentation.voice",
}
HEARTBEAT_STATES = {"connected", "disconnected", "unhealthy"}
VALID_ENDPOINT_TYPES = {"browser", "mobile", "desktop", "wearable", "audio"}


class EndpointRegistry:
    """Durable owner-bound endpoint registry using the shared SQL database."""

    def list_endpoints(self, user_id: str) -> list[dict[str, Any]]:
        ensure_schema()
        with get_engine().connect() as connection:
            rows = connection.execute(
                select(endpoints)
                .where(endpoints.c.owner_id == user_id)
                .order_by(endpoints.c.updated_at.desc())
            ).mappings()
            return [self._decode(row) for row in rows]

    def get_endpoint(self, endpoint_id: str, user_id: str) -> dict[str, Any]:
        ensure_schema()
        with get_engine().connect() as connection:
            row = connection.execute(
                select(endpoints).where(endpoints.c.endpoint_id == endpoint_id)
            ).mappings().first()
        if row is None:
            raise KeyError(f"endpoint {endpoint_id!r} not found")
        if row["owner_id"] != user_id:
            raise PermissionError("endpoint does not belong to the authenticated owner")
        return self._decode(row)

    def register_endpoint(
        self,
        *,
        user_id: str,
        endpoint_id: str | None = None,
        name: str | None = None,
        endpoint_type: str = "browser",
        endpoint_url: str | None = None,
        session_id: str | None = None,
        capabilities: list[str] | tuple[str, ...] | None = None,
        supported_modalities: list[str] | tuple[str, ...] | None = None,
        presentation_contract_versions: list[str] | tuple[str, ...] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ensure_schema()
        active_id = endpoint_id or str(uuid.uuid4())
        try:
            uuid.UUID(active_id)
        except (ValueError, AttributeError) as exc:
            raise ValueError("endpoint_id must be a UUID") from exc
        if endpoint_type not in VALID_ENDPOINT_TYPES:
            raise ValueError(f"unsupported endpoint type: {endpoint_type!r}")
        now = time.time()
        claims = self._sanitize_capabilities(capabilities or [])
        modalities = self._sanitize_modalities(supported_modalities or ["text"])
        versions = self._sanitize_versions(
            presentation_contract_versions or ["1.1"]
        )
        payload = {
            "endpoint_id": active_id,
            "name": (name or active_id)[:128],
            "endpoint_type": endpoint_type,
            "endpoint_url": endpoint_url,
            "session_id": session_id,
            "status": "registered",
            "advertised_capabilities": claims,
            "validated_capabilities": sorted(set(claims) & SERVER_CAPABILITIES),
            "unsupported_capabilities": sorted(set(claims) - SERVER_CAPABILITIES),
            "supported_modalities": modalities,
            "presentation_contract_versions": versions,
            "last_seen": now,
            "created_at": now,
            "updated_at": now,
            "metadata": dict(metadata or {}),
        }
        with get_engine().begin() as connection:
            existing = connection.execute(
                select(
                    endpoints.c.owner_id,
                    endpoints.c.status,
                    endpoints.c.created_at,
                ).where(
                    endpoints.c.endpoint_id == active_id
                )
            ).first()
            if existing:
                if existing.owner_id != user_id:
                    raise PermissionError(
                        "endpoint already exists under another owner"
                    )
                if existing.status == "revoked":
                    raise ValueError("revoked endpoints cannot be registered again")
                payload["created_at"] = existing.created_at
                connection.execute(
                    update(endpoints)
                    .where(endpoints.c.endpoint_id == active_id)
                    .values(
                        payload=json.dumps(payload, ensure_ascii=False),
                        status="registered",
                        is_active=False,
                        version=endpoints.c.version + 1,
                        updated_at=now,
                    )
                )
            else:
                connection.execute(
                    insert(endpoints).values(
                        endpoint_id=active_id,
                        owner_id=user_id,
                        status="registered",
                        is_active=False,
                        version=1,
                        payload=json.dumps(payload, ensure_ascii=False),
                        created_at=now,
                        updated_at=now,
                    )
                )
            self._audit(
                connection, active_id, user_id, "endpoint.registered",
                {"endpoint_type": endpoint_type},
            )
        return self.get_endpoint(active_id, user_id)

    def heartbeat(
        self,
        *,
        user_id: str,
        endpoint_id: str,
        status: str | None = None,
        capabilities: list[str] | tuple[str, ...] | None = None,
        supported_modalities: list[str] | tuple[str, ...] | None = None,
        presentation_contract_versions: list[str] | tuple[str, ...] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ensure_schema()
        now = time.time()
        with get_engine().begin() as connection:
            row = connection.execute(
                select(endpoints).where(endpoints.c.endpoint_id == endpoint_id)
            ).mappings().first()
            endpoint = self._owned(row, user_id, endpoint_id)
            if endpoint["status"] == "revoked":
                raise PermissionError("endpoint has been revoked")
            requested_state = status or endpoint["status"]
            if requested_state not in HEARTBEAT_STATES | {"registered"}:
                raise ValueError(f"unsupported heartbeat state: {requested_state!r}")
            payload = json.loads(endpoint["payload"])
            if capabilities is not None:
                payload.update(self._claims_payload(capabilities))
            if supported_modalities is not None:
                payload["supported_modalities"] = self._sanitize_modalities(
                    supported_modalities
                )
            if presentation_contract_versions is not None:
                payload["presentation_contract_versions"] = self._sanitize_versions(
                    presentation_contract_versions
                )
            if metadata is not None:
                payload["metadata"] = {
                    **payload.get("metadata", {}),
                    **dict(metadata),
                }
            payload.update(status=requested_state, last_seen=now, updated_at=now)
            changed = connection.execute(
                update(endpoints)
                .where(
                    endpoints.c.endpoint_id == endpoint_id,
                    endpoints.c.owner_id == user_id,
                    endpoints.c.version == endpoint["version"],
                )
                .values(
                    status=requested_state,
                    payload=json.dumps(payload, ensure_ascii=False),
                    version=endpoints.c.version + 1,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                raise RuntimeError("endpoint changed concurrently; retry heartbeat")
            self._audit(
                connection, endpoint_id, user_id, "endpoint.heartbeat",
                {"status": requested_state},
            )
        return self.get_endpoint(endpoint_id, user_id)

    def list_audit_events(
        self, *, user_id: str, endpoint_id: str, limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.get_endpoint(endpoint_id, user_id)
        ensure_schema()
        with get_engine().connect() as connection:
            rows = connection.execute(
                select(endpoint_audit_events)
                .where(
                    endpoint_audit_events.c.endpoint_id == endpoint_id,
                    endpoint_audit_events.c.owner_id == user_id,
                )
                .order_by(endpoint_audit_events.c.timestamp.desc())
                .limit(max(1, min(limit, 500)))
            ).mappings()
            events = []
            for row in rows:
                event = dict(row)
                event["payload"] = json.loads(event["payload"])
                events.append(event)
            return events

    def negotiate_capabilities(
        self,
        *,
        user_id: str,
        endpoint_id: str,
        advertised_capabilities: list[str] | tuple[str, ...] | None = None,
        supported_modalities: list[str] | tuple[str, ...] | None = None,
        presentation_contract_versions: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        endpoint = self.get_endpoint(endpoint_id, user_id)
        if endpoint["status"] == "revoked":
            raise PermissionError("endpoint has been revoked")
        claims = self._sanitize_capabilities(
            advertised_capabilities
            if advertised_capabilities is not None
            else endpoint["advertised_capabilities"]
        )
        modalities = self._sanitize_modalities(
            supported_modalities
            if supported_modalities is not None
            else endpoint["supported_modalities"]
        )
        versions = self._sanitize_versions(
            presentation_contract_versions
            if presentation_contract_versions is not None
            else endpoint["presentation_contract_versions"]
        )
        compatible_versions = sorted(
            VALID_CONTRACT_VERSIONS & set(versions),
            key=lambda value: tuple(int(part) for part in value.split(".")),
            reverse=True,
        )
        if not compatible_versions:
            raise ValueError("no compatible presentation contract version")
        validated_claims = sorted(set(claims) & SERVER_CAPABILITIES)
        negotiated_modalities = sorted(set(modalities) & VALID_MODALITIES)
        if "text" not in negotiated_modalities:
            negotiated_modalities.append("text")
            negotiated_modalities.sort()
        self.heartbeat(
            user_id=user_id,
            endpoint_id=endpoint_id,
            status="connected",
            capabilities=claims,
            supported_modalities=negotiated_modalities,
            presentation_contract_versions=[compatible_versions[0]],
        )
        result = {
            "endpoint_id": endpoint_id,
            "owner_id": user_id,
            "negotiated_contract_version": compatible_versions[0],
            "negotiated_capabilities": validated_claims,
            "unsupported_capabilities": sorted(set(claims) - SERVER_CAPABILITIES),
            "supported_modalities": negotiated_modalities,
            "status": "connected",
            "state": "connected",
            "authorization_granted": False,
            "verified_operational": False,
        }
        self._audit_external(
            endpoint_id, user_id, "endpoint.negotiated",
            {
                "contract_version": compatible_versions[0],
                "capabilities": validated_claims,
                "authorization_granted": False,
            },
        )
        return result

    def select_endpoint(
        self, *, user_id: str, endpoint_id: str,
    ) -> dict[str, Any]:
        ensure_schema()
        now = time.time()
        with get_engine().begin() as connection:
            row = connection.execute(
                select(endpoints).where(endpoints.c.endpoint_id == endpoint_id)
            ).mappings().first()
            endpoint = self._owned(row, user_id, endpoint_id)
            if endpoint["status"] != "connected":
                raise ValueError("only connected endpoints can be selected")
            connection.execute(
                update(endpoints)
                .where(endpoints.c.owner_id == user_id)
                .values(is_active=False)
            )
            connection.execute(
                update(endpoints)
                .where(
                    endpoints.c.endpoint_id == endpoint_id,
                    endpoints.c.owner_id == user_id,
                )
                .values(is_active=True, version=endpoints.c.version + 1, updated_at=now)
            )
            self._audit(
                connection, endpoint_id, user_id, "endpoint.selected", {}
            )
        return self.get_endpoint(endpoint_id, user_id)

    def revoke_endpoint(
        self, *, user_id: str, endpoint_id: str,
    ) -> dict[str, Any]:
        ensure_schema()
        now = time.time()
        with get_engine().begin() as connection:
            row = connection.execute(
                select(endpoints).where(endpoints.c.endpoint_id == endpoint_id)
            ).mappings().first()
            endpoint = self._owned(row, user_id, endpoint_id)
            payload = json.loads(endpoint["payload"])
            payload.update(status="revoked", updated_at=now)
            connection.execute(
                update(endpoints)
                .where(
                    endpoints.c.endpoint_id == endpoint_id,
                    endpoints.c.owner_id == user_id,
                )
                .values(
                    status="revoked",
                    is_active=False,
                    payload=json.dumps(payload, ensure_ascii=False),
                    version=endpoints.c.version + 1,
                    updated_at=now,
                )
            )
            self._audit(
                connection, endpoint_id, user_id, "endpoint.revoked", {}
            )
        return self.get_endpoint(endpoint_id, user_id)

    @staticmethod
    def _sanitize_capabilities(value: list[str] | tuple[str, ...]) -> list[str]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("capabilities must be a list of strings")
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValueError("capabilities must contain non-empty strings")
        return list(dict.fromkeys(item.strip() for item in value))

    @classmethod
    def _claims_payload(cls, capabilities: list[str] | tuple[str, ...]) -> dict[str, Any]:
        claims = cls._sanitize_capabilities(capabilities)
        return {
            "advertised_capabilities": claims,
            "validated_capabilities": sorted(set(claims) & SERVER_CAPABILITIES),
            "unsupported_capabilities": sorted(set(claims) - SERVER_CAPABILITIES),
        }

    @classmethod
    def _sanitize_modalities(cls, value: list[str] | tuple[str, ...]) -> list[str]:
        if not isinstance(value, (list, tuple)) or any(
            not isinstance(item, str) or item not in VALID_MODALITIES for item in value
        ):
            raise ValueError("unsupported endpoint modality")
        return list(dict.fromkeys(value or ["text"]))

    @classmethod
    def _sanitize_versions(cls, value: list[str] | tuple[str, ...]) -> list[str]:
        if not isinstance(value, (list, tuple)) or any(
            not isinstance(item, str) or item not in VALID_CONTRACT_VERSIONS
            for item in value
        ):
            raise ValueError("unsupported presentation contract version")
        if not value:
            raise ValueError("at least one presentation contract version is required")
        return sorted(
            set(value),
            key=lambda version: tuple(int(part) for part in version.split(".")),
            reverse=True,
        )

    @staticmethod
    def _decode(row: Any) -> dict[str, Any]:
        payload = json.loads(row["payload"])
        payload.update(
            owner_id=row["owner_id"],
            status=row["status"],
            state=row["status"],
            is_active=bool(row["is_active"]),
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        return payload

    @staticmethod
    def _owned(row: Any, user_id: str, endpoint_id: str) -> Any:
        if row is None:
            raise KeyError(f"endpoint {endpoint_id!r} not found")
        if row["owner_id"] != user_id:
            raise PermissionError("endpoint does not belong to the authenticated owner")
        return row

    @staticmethod
    def _audit(
        connection: Any,
        endpoint_id: str,
        owner_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            insert(endpoint_audit_events).values(
                event_id=str(uuid.uuid4()),
                endpoint_id=endpoint_id,
                owner_id=owner_id,
                event_type=event_type,
                timestamp=time.time(),
                payload=json.dumps(payload, ensure_ascii=False),
            )
        )

    def _audit_external(
        self, endpoint_id: str, owner_id: str, event_type: str,
        payload: dict[str, Any],
    ) -> None:
        ensure_schema()
        with get_engine().begin() as connection:
            self._audit(connection, endpoint_id, owner_id, event_type, payload)


def register_endpoint(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return EndpointRegistry().register_endpoint(*args, **kwargs)


def list_endpoints(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return EndpointRegistry().list_endpoints(*args, **kwargs)
