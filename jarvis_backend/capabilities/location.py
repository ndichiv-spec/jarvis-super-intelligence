"""Authorized, ephemeral validation of browser-sourced current location."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..capability import Capability, CapabilityEvent, CapabilityStatus, ExecutionContext, ExecutionResult


class BrowserLocationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    latitude: float = Field(ge=-90, le=90, strict=True)
    longitude: float = Field(ge=-180, le=180, strict=True)
    accuracy_meters: float | None = Field(default=None, ge=0, strict=True)
    altitude_meters: float | None = Field(default=None, strict=True)
    heading_degrees: float | None = Field(default=None, ge=0, le=360, strict=True)
    speed_meters_per_second: float | None = Field(default=None, ge=0, strict=True)
    captured_at: datetime
    accuracy_preference: Literal["standard", "high"] = "high"


class LocationCurrentCapability(Capability):
    name = "location.current"
    version = "1.0.0"
    category = "geography"
    sensitive = True

    async def _check_health(self) -> dict[str, Any]:
        return {
            "status": CapabilityStatus.AVAILABLE,
            "healthy": True,
            "source": "browser_geolocation",
        }

    async def execute(
        self,
        request: dict[str, Any],
        context: ExecutionContext | None = None,
    ) -> ExecutionResult:
        if context is None or not context.user_id or not context.session_id:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="An authenticated session is required.",
                error_type="UNAUTHORIZED",
            )
        if "location:read" not in context.permissions:
            await self._emit(context, "location.denied", "denied", "permission_denied")
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="Location access is not authorized for this user.",
                error_type="PERMISSION_DENIED",
                correlation_id=context.correlation_id,
            )

        await self._emit(context, "location.requested", "running")
        try:
            location = BrowserLocationInput.model_validate(request)
        except ValidationError:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="The browser returned invalid location data.",
                error_type="INVALID_LOCATION",
                correlation_id=context.correlation_id,
            )

        if location.accuracy_preference not in {"standard", "high"}:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="The requested accuracy preference is unsupported.",
                error_type="INVALID_LOCATION",
                correlation_id=context.correlation_id,
            )
        captured_at = location.captured_at
        if captured_at.tzinfo is None:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="The browser location timestamp must include a timezone.",
                error_type="INVALID_LOCATION",
                correlation_id=context.correlation_id,
            )
        age_seconds = (datetime.now(UTC) - captured_at.astimezone(UTC)).total_seconds()
        if age_seconds < -5 or age_seconds > 120:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="The browser location is stale or has an invalid timestamp.",
                error_type="STALE_LOCATION",
                correlation_id=context.correlation_id,
            )
        if not all(math.isfinite(value) for value in (
            location.latitude,
            location.longitude,
            age_seconds,
        )):
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="The browser returned invalid location data.",
                error_type="INVALID_LOCATION",
                correlation_id=context.correlation_id,
            )

        data: dict[str, Any] = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "timestamp": captured_at.astimezone(UTC).isoformat(),
            "source": "browser_geolocation",
            "freshness": {
                "capturedAt": captured_at.astimezone(UTC).isoformat(),
                "ageSeconds": max(0, round(age_seconds, 3)),
            },
        }
        optional_fields = {
            "accuracyMeters": location.accuracy_meters,
            "altitudeMeters": location.altitude_meters,
            "headingDegrees": location.heading_degrees,
            "speedMetersPerSecond": location.speed_meters_per_second,
        }
        data.update({key: value for key, value in optional_fields.items() if value is not None})
        await self._emit(context, "location.received", "completed")
        return ExecutionResult(
            capability=self.name,
            success=True,
            data=data,
            correlation_id=context.correlation_id,
        )

    async def _emit(
        self,
        context: ExecutionContext,
        event_type: str,
        status: str,
        reason: str | None = None,
    ) -> None:
        if self._registry is None:
            return
        await self._registry.event_bus.emit_async(CapabilityEvent(
            event_type=event_type,
            source=self.name,
            capability=self.name,
            correlation_id=context.correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            execution_id=context.execution_id,
            status=status,
            payload={"reason": reason} if reason else {},
        ))
