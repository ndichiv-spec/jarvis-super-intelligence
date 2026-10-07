"""Canonical geodesic math for the JARVIS geography capability domain.

Pure standard library, no I/O, no network, no optional dependencies. This
module is the single source of truth for geographic computation so that the
Capability Fabric tools and the FastAPI geography router cannot drift apart.

Algorithms are the ones already proven by ``tests/test_geography.py``:
  * great-circle distance and initial azimuth via the Haversine formula
  * coordinate text parsing for decimal degrees and DMS
  * spherical-excess (log-tangent shoelace) polygon area
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple

__all__ = [
    "EARTH_RADIUS_M",
    "EARTH_RADIUS_KM",
    "DISTANCE_UNITS",
    "MAX_POLYGON_VERTICES",
    "CoordinateError",
    "normalize_latitude",
    "normalize_longitude",
    "normalize_coordinates",
    "haversine_distance",
    "distance_between",
    "bearing_between",
    "parse_decimal_dms",
    "format_dms",
    "parse_coordinate_text",
    "polygon_area_stats",
    "polygon_perimeter",
]

EARTH_RADIUS_M = 6371000.0
EARTH_RADIUS_KM = 6371.0

# Distance expressed in meters, per requested unit.
DISTANCE_UNITS: Dict[str, float] = {
    "meters": 1.0,
    "kilometers": 1000.0,
    "miles": 1609.344,
    "nautical_miles": 1852.0,
}

MAX_POLYGON_VERTICES = 5000

# The log-tangent area term diverges at the poles, so polygon maths refuses
# latitudes within this margin of +/-90 degrees rather than returning inf.
_POLAR_LIMIT = 89.9999

# Degrees/minutes/seconds followed by a hemisphere. A separator is required
# between the degree and minute fields so a decimal such as "40.7128" can never
# be mis-split into "40.712" degrees and "8" minutes.
_DMS_SYMBOL_PATTERN = re.compile(
    r'([+-]?\d+(?:\.\d+)?)\s*[,;°\s]\s*(\d+(?:\.\d+)?)\s*[,;\'′°\s]\s*'
    r'(\d+(?:\.\d+)?)?\s*[,;:\'′°\s]*["″]?\s*([NSEW])'
)

# Degrees/minutes/seconds followed by a hemisphere, with the degree symbol
# optional, so "40 42 46 N" is accepted as well as "40°42'46\"N".
_HEMISPHERE = re.compile(r"[NSEWnsew]")

# Plain decimal degrees carrying hemisphere suffixes, e.g. "40.7128 N 74.0060 W".
_DECIMAL_HEMISPHERE = re.compile(
    r"^\s*([+-]?\d+(?:\.\d+)?)\s*°?\s*([NSns])\s*[,;]?\s*"
    r"([+-]?\d+(?:\.\d+)?)\s*°?\s*([EWew])\s*$"
)


class CoordinateError(ValueError):
    """Raised when a coordinate is missing, non-finite or out of range."""


def _coerce(value: Any, label: str) -> float:
    if isinstance(value, bool) or value is None:
        raise CoordinateError(f"{label} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CoordinateError(f"{label} must be a number: {value!r}") from exc
    if not math.isfinite(number):
        raise CoordinateError(f"{label} must be finite: {value!r}")
    return number


def normalize_latitude(value: Any) -> float:
    """Return ``value`` as a validated latitude in [-90, 90]."""
    number = _coerce(value, "latitude")
    if not -90.0 <= number <= 90.0:
        raise CoordinateError(f"latitude out of range [-90, 90]: {number}")
    return number


def normalize_longitude(value: Any) -> float:
    """Return ``value`` as a validated longitude in [-180, 180]."""
    number = _coerce(value, "longitude")
    if not -180.0 <= number <= 180.0:
        raise CoordinateError(f"longitude out of range [-180, 180]: {number}")
    return number


def normalize_coordinates(latitude: Any, longitude: Any) -> Tuple[float, float]:
    """Validate and return a ``(latitude, longitude)`` pair."""
    return normalize_latitude(latitude), normalize_longitude(longitude)


def _coords_from(source: Any) -> Tuple[float, float]:
    """Accept a mapping with latitude/longitude or a 2-sequence of lat, lon."""
    if isinstance(source, dict):
        return normalize_coordinates(source.get("latitude"), source.get("longitude"))
    if isinstance(source, (list, tuple)) and len(source) == 2:
        return normalize_coordinates(source[0], source[1])
    raise CoordinateError("coordinates must be {latitude, longitude} or [lat, lon]")


def haversine_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> Tuple[float, float, float]:
    """Great-circle distance and bearings between two points.

    Returns ``(distance_meters, forward_bearing_deg, reverse_bearing_deg)``.
    """
    lat1 = normalize_latitude(lat1)
    lon1 = normalize_longitude(lon1)
    lat2 = normalize_latitude(lat2)
    lon2 = normalize_longitude(lon2)

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    # Clamp guards against floating point drift pushing `a` marginally past 1.
    a = min(1.0, max(0.0, a))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = EARTH_RADIUS_M * c

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
    reverse_bearing = (bearing + 180) % 360

    return distance, bearing, reverse_bearing


def distance_between(
    origin: Any, destination: Any, unit: str = "kilometers"
) -> Dict[str, Any]:
    """Great-circle distance between two coordinate pairs in ``unit``."""
    lat1, lon1 = _coords_from(origin)
    lat2, lon2 = _coords_from(destination)
    if unit not in DISTANCE_UNITS:
        raise CoordinateError(
            f"unsupported unit {unit!r}; expected one of {sorted(DISTANCE_UNITS)}"
        )
    meters, _, _ = haversine_distance(lat1, lon1, lat2, lon2)
    return {
        "distance": meters / DISTANCE_UNITS[unit],
        "unit": unit,
        "distance_meters": meters,
        "from_coords": {"latitude": lat1, "longitude": lon1},
        "to_coords": {"latitude": lat2, "longitude": lon2},
        "calculation_method": "haversine",
    }


def bearing_between(origin: Any, destination: Any) -> Dict[str, Any]:
    """Initial forward azimuth in degrees in [0, 360)."""
    lat1, lon1 = _coords_from(origin)
    lat2, lon2 = _coords_from(destination)
    _, bearing, reverse = haversine_distance(lat1, lon1, lat2, lon2)
    return {
        "bearing_degrees": bearing,
        "reverse_bearing_degrees": reverse,
        "from_coords": {"latitude": lat1, "longitude": lon1},
        "to_coords": {"latitude": lat2, "longitude": lon2},
        "calculation_method": "haversine",
    }


def _dms_to_decimal(deg: float, minutes: float, seconds: float, direction: str) -> float:
    decimal = abs(deg) + abs(minutes) / 60 + abs(seconds) / 3600
    if direction.upper() in ("S", "W"):
        decimal = -decimal
    return decimal


def parse_decimal_dms(value: str) -> Tuple[float, float]:
    """Parse coordinate text into a validated ``(latitude, longitude)`` pair.

    Accepts decimal degrees (``"40.7128 -74.0060"``), decimal degrees with
    hemisphere suffixes (``"40.7128 N 74.0060 W"``) and DMS with or without
    symbols (``"40 42 46 N 74 0 22 W"``).
    """
    if not isinstance(value, str) or not value.strip():
        raise CoordinateError("coordinate input must be a non-empty string")
    text = value.strip()

    dms_marked = any(token in text for token in ("°", "'", '"', "″", "′"))
    has_hemisphere = bool(_HEMISPHERE.search(text))
    if dms_marked or len(_HEMISPHERE.findall(text)) >= 2:
        parts = _DMS_SYMBOL_PATTERN.findall(text)
        if len(parts) >= 2:
            latitude = _dms_to_decimal(
                float(parts[0][0]), float(parts[0][1]),
                float(parts[0][2]) if parts[0][2] else 0.0, parts[0][3],
            )
            longitude = _dms_to_decimal(
                float(parts[1][0]), float(parts[1][1]),
                float(parts[1][2]) if parts[1][2] else 0.0, parts[1][3],
            )
            if parts[0][3].upper() not in ("N", "S") or parts[1][3].upper() not in ("E", "W"):
                raise CoordinateError(
                    "DMS pairs must be latitude (N/S) then longitude (E/W)"
                )
            return normalize_coordinates(latitude, longitude)

    hemisphere = _DECIMAL_HEMISPHERE.match(text)
    if hemisphere:
        latitude = float(hemisphere.group(1))
        if hemisphere.group(2).upper() == "S":
            latitude = -abs(latitude)
        longitude = float(hemisphere.group(3))
        if hemisphere.group(4).upper() == "W":
            longitude = -abs(longitude)
        return normalize_coordinates(latitude, longitude)

    if not has_hemisphere:
        try:
            parts = text.replace(",", " ").split()
            if len(parts) >= 2:
                return normalize_coordinates(float(parts[0]), float(parts[1]))
        except ValueError:
            pass

    raise CoordinateError(f"could not parse coordinate: {value}")


def format_dms(value: float, is_latitude: bool) -> str:
    """Render a coordinate as a signed DMS string with hemisphere suffix."""
    number = normalize_latitude(value) if is_latitude else normalize_longitude(value)
    hemisphere = ("N" if number >= 0 else "S") if is_latitude else (
        "E" if number >= 0 else "W"
    )
    absolute = abs(number)
    degrees = int(absolute)
    minutes_full = (absolute - degrees) * 60
    minutes = int(minutes_full)
    seconds = round((minutes_full - minutes) * 60, 3)
    if seconds >= 60:
        seconds = round(seconds - 60, 3)
        minutes += 1
    if minutes >= 60:
        minutes -= 60
        degrees += 1
    return f"{degrees}°{minutes}'{seconds}\"{hemisphere}"


def parse_coordinate_text(value: str, fmt: str = "auto") -> Dict[str, Any]:
    """Parse coordinate text and report the format that was recognised."""
    latitude, longitude = parse_decimal_dms(value)
    if fmt not in ("auto", "decimal", "dms", None):
        raise CoordinateError(f"unsupported format {fmt!r}")
    detected = "dms" if any(tok in str(value) for tok in ("°", "'", '"', "″", "N", "S", "E", "W")) else "decimal"
    return {
        "latitude": latitude,
        "longitude": longitude,
        "input_format": fmt or "auto",
        "detected_format": detected,
        "original_input": value,
        "dms_latitude": format_dms(latitude, True),
        "dms_longitude": format_dms(longitude, False),
        "validated": True,
    }


def _validated_ring(coordinates: Iterable[Sequence[float]]) -> List[List[float]]:
    ring: List[List[float]] = []
    for point in coordinates:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise CoordinateError("each coordinate must be a [latitude, longitude] pair")
        latitude, longitude = normalize_coordinates(point[0], point[1])
        if abs(latitude) >= _POLAR_LIMIT:
            raise CoordinateError(
                "polygon area is undefined within 0.0001 degrees of a pole"
            )
        ring.append([latitude, longitude])
    if len(ring) > MAX_POLYGON_VERTICES:
        raise CoordinateError(
            f"polygon exceeds {MAX_POLYGON_VERTICES} vertices"
        )
    return ring


def polygon_area_stats(coordinates: Iterable[Sequence[float]]) -> Dict[str, Any]:
    """Area, bounds and centroid of a closed polygon on a sphere.

    Uses the spherical-excess (log-tangent shoelace) formulation. The centroid
    is an arithmetic mean of the vertices, which is exact for convex rings and
    explicitly reported as an approximation.
    """
    ring = _validated_ring(coordinates)
    if len(ring) < 4:
        raise CoordinateError("polygon must have at least 4 vertices (closed)")

    total = 0.0
    previous_lat_rad = math.radians(ring[0][0])
    previous_lon_rad = math.radians(ring[0][1])
    previous_latitude = ring[0][0]
    latitudes = [point[0] for point in ring]
    longitudes = [point[1] for point in ring]

    for latitude, longitude in ring[1:]:
        lat_rad = math.radians(latitude)
        lon_rad = math.radians(longitude)
        total += (lon_rad - previous_lon_rad) * (
            math.log(math.tan(lat_rad / 2 + math.pi / 4))
            + math.log(math.tan(previous_lat_rad / 2 + math.pi / 4))
        )
        previous_lat_rad = lat_rad
        previous_lon_rad = lon_rad
        previous_latitude = latitude

    area_km2 = abs(total) * EARTH_RADIUS_KM * EARTH_RADIUS_KM / 2

    return {
        "area_km2": area_km2,
        "bounds": {
            "min_latitude": min(latitudes),
            "max_latitude": max(latitudes),
            "min_longitude": min(longitudes),
            "max_longitude": max(longitudes),
        },
        "centroid": {
            "latitude": sum(latitudes) / len(latitudes),
            "longitude": sum(longitudes) / len(longitudes),
        },
        "centroid_method": "vertex_mean_approximation",
        "vertex_count": len(ring),
        "closed": ring[0] == ring[-1],
        "calculation_method": "haversine_polygon_approximation",
    }


def polygon_perimeter(
    coordinates: Iterable[Sequence[float]], unit: str = "kilometers"
) -> Dict[str, Any]:
    """Closed-ring perimeter length, optionally including the closing edge."""
    ring = _validated_ring(coordinates)
    if len(ring) < 2:
        raise CoordinateError("perimeter needs at least 2 vertices")
    if unit not in DISTANCE_UNITS:
        raise CoordinateError(
            f"unsupported unit {unit!r}; expected one of {sorted(DISTANCE_UNITS)}"
        )

    total_m = 0.0
    for index in range(1, len(ring)):
        total_m += haversine_distance(
            ring[index - 1][0], ring[index - 1][1], ring[index][0], ring[index][1]
        )[0]
    if ring[0] != ring[-1]:
        total_m += haversine_distance(
            ring[-1][0], ring[-1][1], ring[0][0], ring[0][1]
        )[0]

    return {
        "perimeter": total_m / DISTANCE_UNITS[unit],
        "unit": unit,
        "perimeter_meters": total_m,
        "vertex_count": len(ring),
        "closed": ring[0] == ring[-1],
        "calculation_method": "haversine_sum",
    }
