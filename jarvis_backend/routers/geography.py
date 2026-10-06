"""Geography capability domain for JARVIS.

Offline-capable geographic utilities with real vs. unavailable distinction.

Capabilities:
- geography.coordinates: Parse/normalize coordinate formats
- geography.distance: Calculate distance between coordinates (offline)
- geography.bearing: Calculate bearing between coordinates (offline)
- geography.area: Calculate area/bounds/centroid for polygons (offline)
- geography.online_geocode: Convert address to coordinates (requires provider)
- geography.online_reverse_geocode: Convert coordinates to address (requires provider)
- geography.route: Calculate routes (requires routing engine)
- geography.place_search: Search geographic places (requires external source)
- geography.offline_search: Search local knowledge (Kiwix, local datasets)
- geography.map_data.inspect: Inspect local map files
- geography.map_data.search: Search local map data

All offline capabilities are always AVAILABLE.
Online/knowledge capabilities are NOT_CONFIGURED if no source exists.
"""

from __future__ import annotations

import math
import ipaddress
import os
import asyncio
import time
import uuid
from urllib.parse import urlencode, urlparse
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, validator

from ..core import get_current_user, get_store, now_iso

router = APIRouter(prefix="/api/v1/geography", tags=["geography"])
_PROVIDER_TIMEOUT_SECONDS = 10.0
_GEOCODER_RATE_LOCK = asyncio.Lock()
_GEOCODER_LAST_REQUEST = 0.0
_GEOCODER_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}


def _route_instruction(step: Dict[str, Any]) -> str:
    maneuver = step.get("maneuver") if isinstance(step.get("maneuver"), dict) else {}
    instruction = maneuver.get("instruction")
    if instruction:
        return str(instruction)[:300]

    maneuver_type = str(maneuver.get("type") or "continue").replace("_", " ")
    modifier = str(maneuver.get("modifier") or "").replace("_", " ")
    name = str(step.get("name") or "").strip()
    if maneuver_type == "arrive":
        return f"Arrive at {name}" if name else "Arrive at your destination"
    if maneuver_type == "depart":
        return f"Start on {name}" if name else "Start route"
    action = maneuver_type.title()
    if modifier:
        action = f"{action} {modifier}"
    if name:
        return f"{action} onto {name}"[:300]
    return action[:300]


def _provider_endpoint(setting: str) -> str:
    endpoint = os.environ.get(setting, "").strip()
    parsed = urlparse(endpoint)
    host = (parsed.hostname or "").lower()
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or host == "localhost"
        or host.endswith((".localhost", ".local"))
        or (ip is not None and not ip.is_global)
    ):
        raise HTTPException(
            status_code=503,
            detail=f"{setting} must be configured with an HTTPS provider endpoint",
        )
    return endpoint


# ============================================================================ #
# Enumerations
# ============================================================================ #

class DistanceUnit(str, Enum):
    """Distance units."""
    METERS = "meters"
    KILOMETERS = "kilometers"
    MILES = "miles"
    NAUTICAL_MILES = "nautical_miles"


class CapabilityStatus(str, Enum):
    """Capability availability status."""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"
    NOT_IMPLEMENTED = "not_implemented"
    ERROR = "error"


@dataclass
class GeographyCapability:
    """Metadata for a geography capability."""
    capability_id: str
    domain: str = "geography"
    version: str = "1.0.0"
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"
    required_permissions: List[str] = field(default_factory=list)
    supports_streaming: bool = False
    supports_async: bool = False
    supports_offline: bool = False
    dependencies: List[str] = field(default_factory=list)
    timeout_ms: int = 5000
    audit_required: bool = False


# ============================================================================ #
# Input/Output Schemas
# ============================================================================ #

class Coordinates(BaseModel):
    """Coordinate pair."""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)

    @validator("latitude")
    def validate_latitude(cls, v):
        if v < -90 or v > 90:
            raise ValueError("latitude must be between -90 and 90")
        return v

    @validator("longitude")
    def validate_longitude(cls, v):
        if v < -180 or v > 180:
            raise ValueError("longitude must be between -180 and 180")
        return v


class CoordinateParseRequest(BaseModel):
    """Request to parse a coordinate string."""
    input: str  # Decimal degrees, DMS, or other formats
    format: Optional[str] = None  # "decimal", "dms", "auto"


class CoordinateParseResult(BaseModel):
    """Result of coordinate parsing."""
    latitude: float
    longitude: float
    input_format: str
    original_input: str
    validated: bool = True


class DistanceRequest(BaseModel):
    """Request to calculate distance between two points."""
    from_coords: Coordinates
    to_coords: Coordinates
    unit: DistanceUnit = DistanceUnit.KILOMETERS


class DistanceResult(BaseModel):
    """Result of distance calculation."""
    distance: float
    unit: str
    from_coords: Dict[str, float]
    to_coords: Dict[str, float]
    calculation_method: str = "haversine"


class BearingRequest(BaseModel):
    """Request to calculate bearing between two points."""
    from_coords: Coordinates
    to_coords: Coordinates


class BearingResult(BaseModel):
    """Result of bearing calculation."""
    bearing_degrees: float
    from_coords: Dict[str, float]
    to_coords: Dict[str, float]
    calculation_method: str = "haversine"


class CoordinateFormat:
    """Supported coordinate formats."""
    FORMAT_DECIMAL = "decimal"
    FORMAT_DMS = "dms"
    FORMAT_UTM = "utm"


# ============================================================================ #
# Offline Capabilities - Always Available
# ============================================================================ #

def haversine_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> Tuple[float, float, float]:
    """
    Calculate great-circle distance using Haversine formula.
    
    Returns: (distance_meters, forward_bearing_deg, reverse_bearing_deg)
    """
    R = 6371000  # Earth radius in meters
    
    φ1 = math.radians(lat1)
    φ2 = math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    
    a = math.sin(Δφ / 2) ** 2 + \
        math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    distance = R * c
    
    # Calculate forward bearing
    y = math.sin(Δλ) * math.cos(φ2)
    x = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(Δλ)
    bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
    
    # Reverse bearing
    reverse_bearing = (bearing + 180) % 360
    
    return distance, bearing, reverse_bearing


def parse_decimal_dms(value: str) -> Tuple[float, float]:
    """
    Parse coordinate in various formats.
    
    Supports:
    - Decimal degrees: "40.7128 -74.0060"
    - DMS: "40°42'46\"N 74°0'22\"W" or "40 42 46 N 74 0 22 W"
    """
    value = value.strip()
    
    # Check for DMS format with symbols
    if "°" in value or "'" in value or '"' in value:
        # Parse DMS format
        import re
        
        # Pattern for DMS: 40°42'46"N or 40 42 46 N
        dms_pattern = r'([+-]?\d+(?:\.\d+)?)\s*°?\s*(\d+(?:\.\d+)?)\s*[\'′]?\s*(\d+(?:\.\d+)?)?(?:\.?\d*)"?\s*([NSEW])'
        
        parts = re.findall(dms_pattern, value, re.IGNORECASE)
        if len(parts) >= 2:
            def dms_to_decimal(deg, min_, sec, direction):
                dec = abs(float(deg)) + abs(float(min_)) / 60 + abs(float(sec)) / 3600
                if direction.upper() in ('S', 'W'):
                    dec = -dec
                return dec
            
            lat = dms_to_decimal(float(parts[0][0]), float(parts[0][1]), 
                                   float(parts[0][2]) if parts[0][2] else 0, parts[0][3])
            lon = dms_to_decimal(float(parts[1][0]), float(parts[1][1]), 
                                   float(parts[1][2]) if parts[1][2] else 0, parts[1][3])
            return lat, lon
    
    # Try decimal format
    try:
        parts = value.replace(',', ' ').split()
        if len(parts) >= 2:
            lat = float(parts[0])
            lon = float(parts[1])
            return lat, lon
    except ValueError:
        pass
    
    raise ValueError(f"Could not parse coordinate: {value}")


# ============================================================================ #
# API Endpoints
# ============================================================================ #

@router.get("/capabilities", response_model=List[Dict[str, Any]])
async def list_capabilities():
    """List all geography capabilities with their status."""
    capabilities = []
    
    # Offline capabilities - always available
    offline_caps = [
        GeographyCapability(
            capability_id="geography.coordinates",
            description="Parse/normalize coordinate formats (decimal degrees, DMS)",
            input_schema={"input": str, "format": str},
            output_schema={"latitude": float, "longitude": float},
            supports_offline=True,
            dependencies=[],
        ),
        GeographyCapability(
            capability_id="geography.distance",
            description="Calculate distance between coordinates using Haversine formula",
            input_schema={"from_coords": Coordinates, "to_coords": Coordinates, "unit": str},
            output_schema={"distance": float, "unit": str, "calculation_method": str},
            supports_offline=True,
            dependencies=[],
        ),
        GeographyCapability(
            capability_id="geography.bearing",
            description="Calculate bearing between two coordinates",
            input_schema={"from_coords": Coordinates, "to_coords": Coordinates},
            output_schema={"bearing_degrees": float, "calculation_method": str},
            supports_offline=True,
            dependencies=[],
        ),
        GeographyCapability(
            capability_id="geography.area",
            description="Calculate area, bounds, and centroid for polygon geometry",
            input_schema={"coordinates": List[List[float]]},
            output_schema={"area": float, "bounds": Dict[str, float]},
            supports_offline=True,
            dependencies=[],
        ),
    ]
    
    # Online/knowledge capabilities - may not be configured
    online_caps = [
        GeographyCapability(
            capability_id="geography.geocode",
            description="Convert address/place name to coordinates (requires provider)",
            input_schema={"query": str},
            output_schema={"coordinates": Coordinates, "source": str},
            supports_offline=False,
            dependencies=["geocoding_provider"],
        ),
        GeographyCapability(
            capability_id="geography.reverse_geocode",
            description="Convert coordinates to address/description (requires provider)",
            input_schema={"latitude": float, "longitude": float},
            output_schema={"address": str, "place": str, "source": str},
            supports_offline=False,
            dependencies=["geocoding_provider"],
        ),
        GeographyCapability(
            capability_id="geography.route",
            description="Route calculation between coordinates (requires routing engine)",
            input_schema={"from": Coordinates, "to": Coordinates},
            output_schema={"distance": float, "duration": float, "steps": list},
            supports_offline=False,
            dependencies=["routing_engine"],
        ),
        GeographyCapability(
            capability_id="geography.place_search",
            description="Search for places (requires external geographic database)",
            input_schema={"query": str, "limit": int},
            output_schema={"results": list, "source": str},
            supports_offline=False,
            dependencies=["geographic_database"],
        ),
        GeographyCapability(
            capability_id="geography.offline_search",
            description="Search local Kiwix corpus for geographic information",
            input_schema={"query": str, "limit": int},
            output_schema={"results": list, "source": str},
            supports_offline=False,
            dependencies=["kiwix_corpus"],
        ),
        GeographyCapability(
            capability_id="geography.map_data.inspect",
            description="Inspect local map files (GeoJSON, GPX, KML)",
            input_schema={"path": str},
            output_schema={"feature_count": int, "bounds": Dict, "geometry_types": list},
            supports_offline=False,
            dependencies=["local_filesystem"],
        ),
    ]
    
    all_caps = offline_caps + online_caps
    
    for cap in all_caps:
        if cap.capability_id in {"geography.offline_search", "geography.map_data.inspect"}:
            status = CapabilityStatus.NOT_IMPLEMENTED
        else:
            status = CapabilityStatus.AVAILABLE if cap.supports_offline else _check_configured(cap.capability_id)
        capabilities.append({
            "capability_id": cap.capability_id,
            "domain": cap.domain,
            "version": cap.version,
            "description": cap.description,
            "status": status.value,
            "supports_offline": cap.supports_offline,
            "dependencies": cap.dependencies,
            "requires_provider": not cap.supports_offline,
        })
    
    return capabilities


def _check_configured(capability_id: str) -> CapabilityStatus:
    """Check if a non-offline capability is configured."""
    # These checks describe implemented integrations only.
    if capability_id == "geography.geocode":
        return CapabilityStatus.AVAILABLE if (
            os.environ.get("JARVIS_GEOCODER_URL") and os.environ.get("JARVIS_GEOCODER_USER_AGENT")
        ) else CapabilityStatus.NOT_CONFIGURED
    if capability_id == "geography.reverse_geocode":
        return CapabilityStatus.AVAILABLE if (
            os.environ.get("JARVIS_GEOCODER_URL") and os.environ.get("JARVIS_GEOCODER_USER_AGENT")
        ) else CapabilityStatus.NOT_CONFIGURED
    if capability_id == "geography.route":
        return CapabilityStatus.AVAILABLE if os.environ.get("JARVIS_ROUTING_URL") else CapabilityStatus.NOT_CONFIGURED
    if capability_id == "geography.place_search":
        return CapabilityStatus.NOT_CONFIGURED
    if capability_id == "geography.offline_search":
        return CapabilityStatus.NOT_IMPLEMENTED
    if capability_id == "geography.map_data.inspect":
        return CapabilityStatus.NOT_IMPLEMENTED
    
    return CapabilityStatus.UNAVAILABLE


@router.get("/providers")
async def geography_providers(user: Dict[str, Any] = Depends(get_current_user)):
    """Expose configured geography services without returning provider URLs or keys."""
    return {
        "geocoding": {
            "configured": bool(os.environ.get("JARVIS_GEOCODER_URL")),
            "user_agent_configured": bool(os.environ.get("JARVIS_GEOCODER_USER_AGENT")),
        },
        "routing": {"configured": bool(os.environ.get("JARVIS_ROUTING_URL"))},
        "satellite_imagery": {
            "configured": False,
            "provider_license_confirmed": bool(
                os.environ.get("JARVIS_MAP_TILE_URL")
                and os.environ.get("JARVIS_SATELLITE_IMAGERY_LICENSE_CONFIRMED", "").lower() == "true"
                and os.environ.get("JARVIS_MAP_ATTRIBUTION")
            ),
            "license_confirmed": os.environ.get(
                "JARVIS_SATELLITE_IMAGERY_LICENSE_CONFIRMED", ""
            ).lower() == "true",
        },
        "attribution": os.environ.get("JARVIS_MAP_ATTRIBUTION", "")
        if os.environ.get("JARVIS_MAP_TILE_URL")
        and os.environ.get("JARVIS_SATELLITE_IMAGERY_LICENSE_CONFIRMED", "").lower() == "true"
        else "",
    }


@router.get("/geocode")
async def geocode_place(q: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Resolve a place name using an explicitly configured Nominatim-compatible endpoint."""
    query = q.strip()
    if not query or len(query) > 200:
        raise HTTPException(status_code=422, detail="Query must contain 1 to 200 characters")

    endpoint = _provider_endpoint("JARVIS_GEOCODER_URL")
    user_agent = os.environ.get("JARVIS_GEOCODER_USER_AGENT", "").strip()
    if not user_agent:
        raise HTTPException(
            status_code=503,
            detail="Configure JARVIS_GEOCODER_USER_AGENT with an identifiable application contact",
        )

    global _GEOCODER_LAST_REQUEST
    key = query.casefold()
    cached = _GEOCODER_CACHE.get(key)
    if cached and cached[0] > time.monotonic():
        return {"query": query, "results": cached[1], "source": "configured geocoder", "cached": True}

    async with _GEOCODER_RATE_LOCK:
        delay = 1.0 - (time.monotonic() - _GEOCODER_LAST_REQUEST)
        if delay > 0:
            await asyncio.sleep(delay)
        _GEOCODER_LAST_REQUEST = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=_PROVIDER_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    endpoint,
                    params={"q": query, "format": "jsonv2", "limit": 5},
                    headers={"User-Agent": user_agent, "Accept": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="The configured geocoding provider request failed") from exc

    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="The geocoding provider returned an unsupported response")

    results = []
    for item in data[:5]:
        try:
            latitude = float(item["lat"])
            longitude = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if -90 <= latitude <= 90 and -180 <= longitude <= 180:
            results.append({
                "name": str(item.get("display_name") or query)[:300],
                "latitude": latitude,
                "longitude": longitude,
                "type": str(item.get("type") or ""),
            })
    if len(_GEOCODER_CACHE) >= 500:
        expired_keys = [cache_key for cache_key, value in _GEOCODER_CACHE.items() if value[0] <= time.monotonic()]
        for cache_key in expired_keys:
            _GEOCODER_CACHE.pop(cache_key, None)
        if len(_GEOCODER_CACHE) >= 500:
            _GEOCODER_CACHE.pop(next(iter(_GEOCODER_CACHE)))
    _GEOCODER_CACHE[key] = (time.monotonic() + 3600, results)
    return {"query": query, "results": results, "source": "configured geocoder", "cached": False}


@router.post("/route")
async def route_between_places(
    body: Dict[str, Coordinates],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Request a driving route from a configured OSRM-compatible provider."""
    origin = body.get("from")
    destination = body.get("to")
    if origin is None or destination is None:
        raise HTTPException(status_code=422, detail="Both 'from' and 'to' coordinates are required")

    endpoint = _provider_endpoint("JARVIS_ROUTING_URL").rstrip("/")
    route_url = (
        f"{endpoint}/{origin.longitude},{origin.latitude};"
        f"{destination.longitude},{destination.latitude}"
    )
    try:
        async with httpx.AsyncClient(timeout=_PROVIDER_TIMEOUT_SECONDS) as client:
            response = await client.get(
                route_url,
                params={"overview": "full", "geometries": "geojson", "steps": "true"},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="The configured routing provider request failed") from exc

    routes = payload.get("routes") if isinstance(payload, dict) else None
    if not routes:
        raise HTTPException(status_code=404, detail="No route was returned for these coordinates")
    route = routes[0]
    return {
        "distance_meters": route.get("distance"),
        "duration_seconds": route.get("duration"),
        "geometry": route.get("geometry"),
        "steps": [
            {
                "instruction": _route_instruction(step),
                "distance_meters": step.get("distance"),
                "duration_seconds": step.get("duration"),
            }
            for leg in route.get("legs", [])
            for step in leg.get("steps", [])
        ],
        "source": "configured routing provider",
    }


# ============================================================================ #
# COORDINATE PARSING
# ============================================================================ #

@router.post("/coordinates/parse", response_model=CoordinateParseResult)
async def parse_coordinates(req: CoordinateParseRequest):
    """
    Parse a coordinate string into latitude/longitude.
    
    Supports:
    - Decimal degrees: "40.7128 -74.0060"
    - DMS: "40°42'46\"N 74°0'22\"W"
    - DMS without symbols: "40 42 46 N 74 0 22 W"
    """
    try:
        lat, lon = parse_decimal_dms(req.input)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return CoordinateParseResult(
        latitude=lat,
        longitude=lon,
        input_format=req.format or "auto",
        original_input=req.input,
        validated=True,
    )


# ============================================================================ #
# DISTANCE CALCULATION (Offline)
# ============================================================================ #

@router.post("/distance", response_model=DistanceResult)
async def calculate_distance(req: DistanceRequest):
    """
    Calculate distance between two coordinates.
    
    Uses the Haversine formula for great-circle distance.
    Fully offline-capable - no external dependencies.
    """
    dist_m, _, _ = haversine_distance(
        req.from_coords.latitude, req.from_coords.longitude,
        req.to_coords.latitude, req.to_coords.longitude
    )
    
    # Convert to requested unit
    unit_multipliers = {
        DistanceUnit.METERS: 1,
        DistanceUnit.KILOMETERS: 1000,
        DistanceUnit.MILES: 1609.344,
        DistanceUnit.NAUTICAL_MILES: 1852,
    }
    
    distance = dist_m / unit_multipliers.get(req.unit, 1000)
    
    return DistanceResult(
        distance=distance,
        unit=req.unit.value,
        from_coords={"latitude": req.from_coords.latitude, "longitude": req.from_coords.longitude},
        to_coords={"latitude": req.to_coords.latitude, "longitude": req.to_coords.longitude},
        calculation_method="haversine",
    )


# ============================================================================ #
# BEARING CALCULATION (Offline)
# ============================================================================ #

@router.post("/bearing", response_model=BearingResult)
async def calculate_bearing(req: BearingRequest):
    """
    Calculate initial bearing (forward azimuth) between two coordinates.
    
    Uses the Haversine formula for bearing calculation.
    Fully offline-capable - no external dependencies.
    """
    _, bearing, _ = haversine_distance(
        req.from_coords.latitude, req.from_coords.longitude,
        req.to_coords.latitude, req.to_coords.longitude
    )
    
    return BearingResult(
        bearing_degrees=bearing,
        from_coords={"latitude": req.from_coords.latitude, "longitude": req.from_coords.longitude},
        to_coords={"latitude": req.to_coords.latitude, "longitude": req.to_coords.longitude},
        calculation_method="haversine",
    )


# ============================================================================ #
# AREA CALCULATION (Offline)
# ============================================================================ #

class AreaRequest(BaseModel):
    """Request to calculate area of a polygon."""
    coordinates: List[List[float]]  # List of [lat, lon] pairs forming a closed polygon


class AreaResult(BaseModel):
    """Result of area calculation."""
    area_km2: float
    bounds: Dict[str, float]
    centroid: Dict[str, float]
    vertex_count: int
    calculation_method: str = "haversine_polygon"


@router.post("/area", response_model=AreaResult)
async def calculate_area(req: AreaRequest):
    """
    Calculate area of a polygon.
    
    Uses the Haversine formula for accurate area calculation on a sphere.
    Coordinates must form a closed polygon (first and last points identical).
    Fully offline-capable.
    """
    if len(req.coordinates) < 4:
        raise HTTPException(status_code=400, detail="Polygon must have at least 4 vertices (closed)")
    
    coords = req.coordinates
    
    # Shoelace formula for area on a sphere
    total_area = 0
    lat1_rad = math.radians(coords[0][0])
    lon1_rad = math.radians(coords[0][1])
    
    min_lat = max_lat = coords[0][0]
    min_lon = max_lon = coords[0][1]
    
    for i in range(1, len(coords)):
        lat = coords[i][0]
        lon = coords[i][1]
        
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        
        # Haversine-based area contribution
        total_area += (lon_rad - lon1_rad) * (math.log(math.tan(lat_rad / 2 + math.pi / 4)) + 
                                             math.log(math.tan(lat1_rad / 2 + math.pi / 4)))
        
        # Update bounds
        min_lat = min(min_lat, lat)
        max_lat = max(max_lat, lat)
        min_lon = min(min_lon, lon)
        max_lon = max(max_lon, lon)
        
        lat1_rad = lat_rad
        lon1_rad = lon_rad
    
    # Convert to square kilometers
    R = 6371  # Earth radius in km
    area_km2 = abs(total_area) * R * R / 2
    
    # Calculate centroid (simple average for small polygons)
    centroid_lat = sum(c[0] for c in coords) / len(coords)
    centroid_lon = sum(c[1] for c in coords) / len(coords)
    
    return AreaResult(
        area_km2=area_km2,
        bounds={
            "min_latitude": min_lat,
            "max_latitude": max_lat,
            "min_longitude": min_lon,
            "max_longitude": max_lon,
        },
        centroid={"latitude": centroid_lat, "longitude": centroid_lon},
        vertex_count=len(coords),
        calculation_method="haversine_polygon_approximation",
    )


# ============================================================================ #
# OFFLINE SEARCH (Conditional - Only if Kiwix available)
# ============================================================================ #

@router.get("/offline_search", response_model=Dict[str, Any])
async def offline_search(q: str, limit: int = 5):
    """
    Search the local Kiwix corpus for geographic information.
    
    Only available when a Kiwix corpus is configured.
    Returns results with source_type = LOCAL_KIWIX.
    """
    misc = get_store("misc").load()
    kiwix_path = misc.get("kiwix_corpus_path", "")
    
    if not kiwix_path:
        return {
            "error": "Kiwix corpus not configured",
            "status": CapabilityStatus.NOT_CONFIGURED.value,
            "results": [],
            "source": "none",
            "source_type": "NONE",
        }
    
    from pathlib import Path
    if not Path(kiwix_path).exists():
        return {
            "error": "Kiwix corpus path does not exist",
            "status": CapabilityStatus.ERROR.value,
            "results": [],
            "source": "kiwix",
            "source_type": "LOCAL_KIWIX",
        }
    
    # TODO: Implement Kiwix search when available
    # For now, return NOT_CONFIGURED status
    return {
        "error": "Kiwix search interface not yet implemented",
        "status": CapabilityStatus.NOT_CONFIGURED.value,
        "results": [],
        "source": "kiwix",
        "source_type": "LOCAL_KIWIX",
        "kiwix_path_found": str(Path(kiwix_path).exists()),
    }


# ============================================================================ #
# GEOGRAPHIC CAPABILITY CONSTANTS
# ============================================================================ #

GEOGRAPHY_CAPABILITIES = {
    "geography.coordinates": GeographyCapability(
        capability_id="geography.coordinates",
        domain="geography",
        version="1.0.0",
        description="Parse/normalize coordinate formats",
        supports_offline=True,
        required_permissions=[],
        audit_required=False,
    ),
    "geography.distance": GeographyCapability(
        capability_id="geography.distance",
        domain="geography",
        version="1.0.0",
        description="Calculate distance between coordinates",
        supports_offline=True,
        required_permissions=[],
        audit_required=False,
    ),
    "geography.bearing": GeographyCapability(
        capability_id="geography.bearing",
        domain="geography",
        version="1.0.0",
        description="Calculate bearing between coordinates",
        supports_offline=True,
        required_permissions=[],
        audit_required=False,
    ),
    "geography.area": GeographyCapability(
        capability_id="geography.area",
        domain="geography",
        version="1.0.0",
        description="Calculate polygon area",
        supports_offline=True,
        required_permissions=[],
        audit_required=False,
    ),
}