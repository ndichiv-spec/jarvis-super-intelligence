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
import uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, validator

from ..core import get_current_user, get_store, now_iso

router = APIRouter(prefix="/api/v1/geography", tags=["geography"])


PUBLIC_GEOGRAPHY_SOURCES = (
    {
        "id": "usgs-earthquakes",
        "label": "USGS public earthquake feed",
        "url": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson",
        "kind": "geojson",
    },
    {
        "id": "nasa-viirs",
        "label": "NASA VIIRS public imagery",
        "url": (
            "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
            "VIIRS_SNPP_CorrectedReflectance_TrueColor/default/"
            f"{(datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()}/"
            "GoogleMapsCompatible_Level9/0/0/0.jpg"
        ),
        "kind": "image",
    },
    {
        "id": "gdelt-news",
        "label": "GDELT public news index",
        "url": "https://api.gdeltproject.org/api/v2/doc/doc",
        "kind": "news",
    },
    {
        "id": "openstreetmap-geocoder",
        "label": "OpenStreetMap public geocoder",
        "url": "https://nominatim.openstreetmap.org/search",
        "kind": "geocoder",
    },
)


async def _verify_public_source(
    client: httpx.AsyncClient, source: Dict[str, str]
) -> Dict[str, Any]:
    """Probe one allow-listed public source and validate its basic response shape."""
    params: Dict[str, str] = {}
    headers: Dict[str, str] = {}
    if source["kind"] == "news":
        params = {"query": "world", "mode": "ArtList", "format": "json", "maxrecords": "1"}
    elif source["kind"] == "geocoder":
        params = {"q": "London", "format": "jsonv2", "limit": "1"}
        headers = {"User-Agent": "JARVIS-Geography/1.0 capability-check"}

    started = datetime.now(timezone.utc)
    try:
        response = await client.get(source["url"], params=params, headers=headers)
        response.raise_for_status()
        if source["kind"] == "geojson":
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
                raise ValueError("Response is not a GeoJSON FeatureCollection")
        elif source["kind"] == "news":
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("articles"), list):
                raise ValueError("Response does not contain a news article list")
        elif source["kind"] == "geocoder":
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError("Response is not a geocoding result list")
        elif source["kind"] == "image" and not response.headers.get("content-type", "").startswith("image/"):
            raise ValueError("Response is not an image")
        return {
            "id": source["id"],
            "label": source["label"],
            "status": "available",
            "http_status": response.status_code,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "latency_ms": round((datetime.now(timezone.utc) - started).total_seconds() * 1000),
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "id": source["id"],
            "label": source["label"],
            "status": "unavailable",
            "error": str(exc)[:240],
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "latency_ms": round((datetime.now(timezone.utc) - started).total_seconds() * 1000),
        }


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
            supports_offline=True,
            dependencies=["kiwix_corpus"],
        ),
        GeographyCapability(
            capability_id="geography.map_data.inspect",
            description="Inspect local map files (GeoJSON, GPX, KML)",
            input_schema={"path": str},
            output_schema={"feature_count": int, "bounds": Dict, "geometry_types": list},
            supports_offline=True,
            dependencies=["local_filesystem"],
        ),
    ]
    
    all_caps = offline_caps + online_caps
    
    for cap in all_caps:
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


@router.post("/sources/verify")
async def verify_public_sources():
    """Check allow-listed public geography sources from the Python backend."""
    results: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0), follow_redirects=False) as client:
        for source in PUBLIC_GEOGRAPHY_SOURCES:
            results.append(await _verify_public_source(client, source))
    available = sum(result["status"] == "available" for result in results)
    return {
        "status": "available" if available == len(results) else "degraded" if available else "unavailable",
        "available": available,
        "total": len(results),
        "checked_at": now_iso(),
        "sources": results,
    }


def _check_configured(capability_id: str) -> CapabilityStatus:
    """Check if a non-offline capability is configured."""
    # Check for configured providers/databases
    misc = get_store("misc").load()
    
    if capability_id == "geography.geocode":
        return CapabilityStatus.NOT_CONFIGURED
    if capability_id == "geography.reverse_geocode":
        return CapabilityStatus.NOT_CONFIGURED
    if capability_id == "geography.route":
        return CapabilityStatus.NOT_CONFIGURED
    if capability_id == "geography.place_search":
        return CapabilityStatus.NOT_CONFIGURED
    if capability_id == "geography.offline_search":
        kiwix_path = misc.get("kiwix_corpus_path", "")
        from pathlib import Path
        if kiwix_path and Path(kiwix_path).exists():
            return CapabilityStatus.AVAILABLE
        return CapabilityStatus.NOT_CONFIGURED
    if capability_id == "geography.map_data.inspect":
        allowed_root = misc.get("allowed_map_root", "/maps")
        from pathlib import Path
        if Path(allowed_root).exists():
            return CapabilityStatus.AVAILABLE
        return CapabilityStatus.NOT_CONFIGURED
    
    return CapabilityStatus.UNAVAILABLE


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