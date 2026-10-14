"""JARVIS Geography Capability Domain.

Real, bounded, offline-first geographic capabilities exposed as ordinary
:class:`~research_engine.tool_registry.Tool` instances, so they inherit the
existing authorization, risk policy and ``scrub_secrets()`` boundary.

What is genuinely implemented here (no network, no optional dependencies):
  * coordinate parsing/formatting and range validation
  * great-circle distance, initial bearing
  * spherical-excess polygon area, bounds, centroid and perimeter
  * bounded inspection and search of local GeoJSON/GPX/KML/TopoJSON
  * bounded literal search of a configured local knowledge corpus

What is deliberately reported as unavailable instead of being faked:
  * geocode / reverse_geocode - no geocoding engine or gazetteer is installed
  * route - no routing engine or road graph exists on this host
  * place_search - no place index exists
  * organic_maps - no Organic Maps binary, database or app install was found

Provenance is explicit on every result: ``LOCAL_MATH`` for computation,
``LOCAL_MAP_DATA`` for files inside the authorized workspace, and
``LOCAL_KIWIX`` only when a real Kiwix/ZIM corpus is actually present and
readable. Nothing is ever labelled as retrieved knowledge when it was not.

The geodesic math lives in :mod:`research_engine.geography_math` so the
Capability Fabric and the FastAPI geography router share one implementation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .geography_math import (
    DISTANCE_UNITS,
    CoordinateError,
    bearing_between,
    distance_between,
    format_dms,
    normalize_coordinates,
    parse_coordinate_text,
    polygon_area_stats,
    polygon_perimeter,
)
from .models import RiskLevel, ToolResult
from .project_tools import WORKSPACE_ROOT, _fail, _is_secret_name, _ok, safe_path
from .tool_registry import Tool, ToolContext

VERSION = "geography/1.0"

AVAILABLE = "available"
UNAVAILABLE = "unavailable"
NOT_CONFIGURED = "not_configured"
ERROR = "error"

# Provenance labels. Never invent one of these for data we did not read.
SOURCE_LOCAL_MATH = "LOCAL_MATH"
SOURCE_LOCAL_MAP_DATA = "LOCAL_MAP_DATA"
SOURCE_LOCAL_KIWIX = "LOCAL_KIWIX"
SOURCE_NONE = "NONE"

# Permissions
GEOGRAPHY_READ = "geography:read"
GEOGRAPHY_SEARCH = "geography:search"
GEOGRAPHY_DATA = "geography:data"

READ_PERMISSIONS = (GEOGRAPHY_READ,)
SEARCH_PERMISSIONS = (GEOGRAPHY_READ, GEOGRAPHY_SEARCH)
DATA_PERMISSIONS = (GEOGRAPHY_READ, GEOGRAPHY_DATA)

# Hard limits. This host is memory constrained and files are untrusted.
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_FEATURES = 20_000
MAX_SEARCH_RESULTS = 100
MAX_SNIPPET_CHARS = 240
MAX_PROPERTY_CHARS = 400
MAX_CORPUS_FILES = 400
MAX_CORPUS_FILE_BYTES = 4 * 1024 * 1024

GEO_SUFFIXES = (".geojson", ".json", ".gpx", ".kml", ".kmz", ".topojson")
TEXT_CORPUS_SUFFIXES = (".txt", ".md", ".rst", ".csv", ".tsv")

_MAP_ROOT_ENV = ("JARVIS_GEOGRAPHY_MAP_ROOT", "GEOGRAPHY_MAP_ROOT")
_CORPUS_ENV = ("JARVIS_KIWIX_CORPUS_PATH", "KIWIX_CORPUS_PATH")

_DOCTYPE = re.compile(rb"<!DOCTYPE", re.IGNORECASE)


class MapDataUnavailable(RuntimeError):
    """Raised when local map data is not configured or not readable."""


# --------------------------------------------------------------------------- #
# Configuration (environment only - no invented defaults)
# --------------------------------------------------------------------------- #
def _env_path(names: Tuple[str, ...]) -> Optional[str]:
    for name in names:
        raw = (os.environ.get(name) or "").strip()
        if raw:
            return raw
    return None


def configured_map_root() -> Optional[str]:
    """Configured local map root, or ``None`` when unset.

    Deliberately has no default. The previous router defaulted to the POSIX
    literal ``/maps``, which can never exist on this Windows host and made the
    capability look configured when it was not.
    """
    return _env_path(_MAP_ROOT_ENV)


def configured_corpus_path() -> Optional[str]:
    """Configured offline knowledge corpus path, or ``None`` when unset."""
    return _env_path(_CORPUS_ENV)


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def resolve_map_root() -> Path:
    """Return the authorized map root or explain why it is unusable."""
    raw = configured_map_root()
    if not raw:
        raise MapDataUnavailable(
            "no local map root configured; set JARVIS_GEOGRAPHY_MAP_ROOT to a "
            "directory inside the authorized workspace"
        )
    try:
        root = safe_path(raw)
    except ValueError as exc:
        raise MapDataUnavailable(f"configured map root rejected: {exc}") from exc
    if not root.is_dir():
        raise MapDataUnavailable(f"configured map root does not exist: {root}")
    if not _inside(root, Path(WORKSPACE_ROOT)):
        raise MapDataUnavailable(
            "configured map root is outside the authorized workspace root"
        )
    return root


def resolve_map_file(candidate: Any, root: Optional[Path] = None) -> Path:
    """Resolve a map file inside the authorized map root.

    Traversal, absolute escapes, symlink escapes, secret-bearing names and
    unexpected extensions are all refused. Content is never executed.
    """
    if not isinstance(candidate, str) or not candidate.strip():
        raise MapDataUnavailable("path is required")
    base = root if root is not None else resolve_map_root()
    try:
        target = safe_path(candidate.strip())
    except ValueError as exc:
        raise MapDataUnavailable(f"path rejected: {exc}") from exc
    if not _inside(target, base):
        raise MapDataUnavailable("path is outside the authorized map root")
    if _is_secret_name(target.name):
        raise MapDataUnavailable("refused: secret-bearing files are not readable")
    if target.suffix.lower() not in GEO_SUFFIXES:
        raise MapDataUnavailable(
            f"unsupported map format {target.suffix or '(none)'!r}; expected one of "
            f"{', '.join(GEO_SUFFIXES)}"
        )
    if not target.is_file():
        raise MapDataUnavailable(f"not a readable file: {target.name}")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise MapDataUnavailable(
            f"file exceeds the {MAX_FILE_BYTES} byte inspection limit"
        )
    return target


def _read_bounded_bytes(path: Path, limit: int = MAX_FILE_BYTES) -> bytes:
    with path.open("rb") as handle:
        return handle.read(limit + 1)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# Capability status helpers
# --------------------------------------------------------------------------- #
def _unavailable(name: str, capability: str, reason: str,
                 required: Iterable[str]) -> Dict[str, Any]:
    return {
        "capability": capability,
        "status": UNAVAILABLE,
        "result_available": False,
        "data": None,
        "reason": reason,
        "required_to_enable": list(required),
        "provenance": {"source": SOURCE_NONE, "capability_version": VERSION},
        "note": "no value was fabricated; this capability has no working engine on this host",
    }


def _local_geometry_status() -> Dict[str, Any]:
    root = configured_map_root()
    if not root:
        return {
            "configured": False,
            "reason": "no local map root configured",
            "env_keys": list(_MAP_ROOT_ENV),
        }
    try:
        resolved = resolve_map_root()
    except MapDataUnavailable as exc:
        return {"configured": True, "usable": False, "reason": str(exc),
                "configured_value": root}
    files = 0
    total_bytes = 0
    for path in resolved.rglob("*"):
        if path.is_file() and path.suffix.lower() in GEO_SUFFIXES:
            files += 1
            total_bytes += path.stat().st_size
    return {
        "configured": True,
        "usable": True,
        "configured_value": root,
        "workspace_relative": _rel(resolved),
        "geo_file_count": files,
        "geo_bytes": total_bytes,
    }


def _rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(WORKSPACE_ROOT).resolve()))
    except (ValueError, OSError):
        return str(path)


def _zim_status() -> Dict[str, Any]:
    """Report real Kiwix/ZIM presence without pretending to read a ZIM."""
    raw = configured_corpus_path()
    if not raw:
        return {
            "configured": False,
            "reason": "no offline corpus path configured",
            "env_keys": list(_CORPUS_ENV),
        }
    try:
        resolved = safe_path(raw)
    except ValueError as exc:
        return {"configured": True, "usable": False, "reason": f"rejected: {exc}"}

    zim_files = ([resolved] if resolved.suffix.lower() == ".zim"
                 else sorted(resolved.rglob("*.zim"))) if resolved.exists() else []
    reader = zim_reader_available()
    if not zim_files:
        return {
            "configured": True,
            "usable": False,
            "configured_value": raw,
            "zim_file_count": 0,
            "reason": "configured corpus path contains no .zim file",
            "zim_reader_available": reader["available"],
        }
    return {
        "configured": True,
        "usable": bool(reader["available"]),
        "configured_value": raw,
        "zim_file_count": len(zim_files),
        "zim_files": [_rel(p) for p in zim_files[:20]],
        "zim_reader_available": reader["available"],
        "reason": None if reader["available"] else reader["reason"],
        "required_to_enable": [] if reader["available"] else reader["required_to_enable"],
    }


def zim_reader_available() -> Dict[str, Any]:
    """A ZIM archive cannot be read without libzim or a Kiwix HTTP service."""
    try:  # pragma: no cover - depends on host packages
        import libzim  # type: ignore  # noqa: F401
        return {"available": True, "mechanism": "libzim"}
    except Exception:  # noqa: BLE001
        pass
    serve = (os.environ.get("KIWIX_SERVE_URL") or "").strip()
    if serve:
        return {"available": False, "mechanism": None,
                "reason": f"KIWIX_SERVE_URL is set to {serve!r} but this capability "
                          "does not perform network calls",
                "required_to_enable": ["libzim python bindings",
                                       "an offline_search network-enabled variant"]}
    return {
        "available": False,
        "mechanism": None,
        "reason": "no ZIM reader present: libzim is not installed and no Kiwix "
                  "service is configured",
        "required_to_enable": ["pip install libzim", "or run kiwix-serve and expose "
                               "an explicitly network-enabled search capability"],
    }


def _corpus_text_files() -> Tuple[Optional[Path], List[Path], Optional[str]]:
    raw = configured_corpus_path()
    if not raw:
        return None, [], "no offline corpus path configured"
    try:
        resolved = safe_path(raw)
    except ValueError as exc:
        return None, [], f"corpus path rejected: {exc}"
    if not _inside(resolved, Path(WORKSPACE_ROOT)):
        return None, [], "corpus path is outside the authorized workspace"
    if not resolved.exists():
        return resolved, [], "configured corpus path does not exist"
    if resolved.is_file():
        return resolved, [resolved], None
    files = [
        path for path in sorted(resolved.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in TEXT_CORPUS_SUFFIXES
        and not _is_secret_name(path.name)
    ][:MAX_CORPUS_FILES]
    return resolved, files, None


# --------------------------------------------------------------------------- #
# Base tool
# --------------------------------------------------------------------------- #
class _GeographyTool(Tool):
    risk: RiskLevel = RiskLevel.READ
    required_permissions: tuple[str, ...] = READ_PERMISSIONS
    schema = {"type": "object", "properties": {}, "required": []}

    def _provenance(self, ctx: ToolContext, source: str, **extra: Any) -> dict:
        base = {
            "source": source,
            "capability_version": VERSION,
            "request_id": ctx.request_id,
            "user_id": ctx.user_id,
            "timestamp": time.time(),
        }
        base.update(extra)
        return base


# --------------------------------------------------------------------------- #
# 1. geography.coordinates
# --------------------------------------------------------------------------- #
class GeographyCoordinatesTool(_GeographyTool):
    name = "geography.coordinates"
    description = ("Parse, validate and format geographic coordinates. Accepts decimal "
                   "degrees, decimal degrees with hemisphere suffixes and DMS with or "
                   "without symbols. Fully offline and deterministic.")
    schema = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Coordinate text to parse."},
            "format": {"type": "string", "enum": ["auto", "decimal", "dms"]},
        },
        "required": ["input"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            parsed = parse_coordinate_text(args.get("input") or "",
                                          args.get("format") or "auto")
            return _ok(self.name, ctx, started, {
                "status": AVAILABLE,
                "result_available": True,
                **parsed,
                "units": {"latitude": "degrees_north", "longitude": "degrees_east"},
                "provenance": self._provenance(ctx, SOURCE_LOCAL_MATH,
                                               method="validated_parse"),
            }, {"format": parsed["detected_format"]})
        except CoordinateError as exc:
            return _fail(self.name, ctx, started, f"invalid coordinates: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- #
# 2. geography.distance
# --------------------------------------------------------------------------- #
class GeographyDistanceTool(_GeographyTool):
    name = "geography.distance"
    description = ("Great-circle distance between two coordinates using the Haversine "
                   "formula. Supports meters, kilometers, miles and nautical miles. "
                   "Fully offline and deterministic.")
    schema = {
        "type": "object",
        "properties": {
            "from": {"type": "object", "description": "{latitude, longitude} or [lat, lon]"},
            "to": {"type": "object", "description": "{latitude, longitude} or [lat, lon]"},
            "unit": {"type": "string", "enum": sorted(DISTANCE_UNITS),
                     "description": "Default kilometers."},
        },
        "required": ["from", "to"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            result = distance_between(args.get("from"), args.get("to"),
                                      args.get("unit") or "kilometers")
            return _ok(self.name, ctx, started, {
                "status": AVAILABLE,
                "result_available": True,
                "distance": result["distance"],
                "unit": result["unit"],
                "distance_meters": result["distance_meters"],
                "from_coords": result["from_coords"],
                "to_coords": result["to_coords"],
                "calculation_method": result["calculation_method"],
                "note": "great-circle distance, not a road or travel distance",
                "provenance": self._provenance(ctx, SOURCE_LOCAL_MATH,
                                               method="haversine"),
            }, {"unit": result["unit"]})
        except CoordinateError as exc:
            return _fail(self.name, ctx, started, f"invalid coordinates: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- #
# 3. geography.bearing
# --------------------------------------------------------------------------- #
class GeographyBearingTool(_GeographyTool):
    name = "geography.bearing"
    description = ("Initial forward azimuth in degrees between two coordinates, plus the "
                   "reverse bearing. Fully offline and deterministic.")
    schema = {
        "type": "object",
        "properties": {
            "from": {"type": "object"},
            "to": {"type": "object"},
        },
        "required": ["from", "to"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            result = bearing_between(args.get("from"), args.get("to"))
            return _ok(self.name, ctx, started, {
                "status": AVAILABLE,
                "result_available": True,
                **result,
                "provenance": self._provenance(ctx, SOURCE_LOCAL_MATH,
                                               method="haversine"),
            })
        except CoordinateError as exc:
            return _fail(self.name, ctx, started, f"invalid coordinates: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- #
# 4. geography.area
# --------------------------------------------------------------------------- #
class GeographyAreaTool(_GeographyTool):
    name = "geography.area"
    description = ("Area, bounding box, centroid and perimeter of a closed polygon using "
                   "the spherical-excess formulation. The centroid is a vertex-mean "
                   "approximation, exact only for convex rings. Fully offline.")
    schema = {
        "type": "object",
        "properties": {
            "coordinates": {
                "type": "array",
                "description": "Ordered [latitude, longitude] vertices of a closed ring.",
                "items": {"type": "array", "items": {"type": "number"},
                          "minItems": 2, "maxItems": 2},
            },
            "perimeter_unit": {"type": "string", "enum": sorted(DISTANCE_UNITS)},
        },
        "required": ["coordinates"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            coordinates = args.get("coordinates")
            if not isinstance(coordinates, (list, tuple)):
                return _fail(self.name, ctx, started, "coordinates must be an array")
            stats = polygon_area_stats(coordinates)
            payload = {
                "status": AVAILABLE,
                "result_available": True,
                **stats,
                "provenance": self._provenance(ctx, SOURCE_LOCAL_MATH,
                                               method=stats["calculation_method"]),
            }
            if args.get("perimeter_unit"):
                payload["perimeter"] = polygon_perimeter(
                    coordinates, args["perimeter_unit"]
                )
            return _ok(self.name, ctx, started, payload,
                       {"vertices": stats["vertex_count"]})
        except CoordinateError as exc:
            return _fail(self.name, ctx, started, f"invalid polygon: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- #
# 5. geography.location_info
# --------------------------------------------------------------------------- #
class GeographyLocationInfoTool(_GeographyTool):
    name = "geography.location_info"
    description = ("Report what is genuinely known about a coordinate offline: validated "
                   "decimal and DMS forms, hemisphere, and polar/antimeridian notes. "
                   "Address, elevation, timezone and administrative area are reported as "
                   "unavailable because no gazetteer or timezone database is installed.")
    schema = {
        "type": "object",
        "properties": {
            "latitude": {"type": "number"},
            "longitude": {"type": "number"},
        },
        "required": ["latitude", "longitude"],
    }

    def _invoke(self, args: dict[str, Any], ctx: ToolContext, started: float) -> ToolResult:
        args = args or {}
        latitude = args.get("latitude")
        longitude = args.get("longitude")
        if latitude is None or longitude is None:
            if not args.get("input"):
                return _fail(self.name, ctx, started,
                             "latitude and longitude are required")
            parsed = parse_coordinate_text(args.get("input"))
            latitude, longitude = parsed["latitude"], parsed["longitude"]

        latitude, longitude = normalize_coordinates(latitude, longitude)

        return _ok(self.name, ctx, started, {
            "status": AVAILABLE,
            "result_available": True,
            "coordinates": {
                "latitude": latitude,
                "longitude": longitude,
                "dms_latitude": format_dms(latitude, True),
                "dms_longitude": format_dms(longitude, False),
                "hemisphere": {
                    "latitude": "north" if latitude >= 0 else "south",
                    "longitude": "east" if longitude >= 0 else "west",
                },
            },
            "derived_facts": {
                "is_polar": abs(latitude) >= 66.5632,
                "crosses_antimeridian": abs(longitude) > 179.999,
                "near_pole_for_area_math": abs(latitude) >= 89.9999,
                "utm_zone": int((longitude + 180) // 6) + 1,
            },
            "unavailable_fields": {
                "address": UNAVAILABLE,
                "elevation_m": UNAVAILABLE,
                "timezone": UNAVAILABLE,
                "country": UNAVAILABLE,
                "administrative_area": UNAVAILABLE,
                "reason": "no gazetteer, elevation model or IANA timezone database "
                          "is installed on this host",
            },
            "provenance": self._provenance(ctx, SOURCE_LOCAL_MATH,
                                           method="coordinate_derivation"),
        })

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            return self._invoke(args, ctx, started)
        except CoordinateError as exc:
            return _fail(self.name, ctx, started, f"invalid coordinates: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- #
# 6-8. Provider-dependent capabilities: reported unavailable, never faked
# --------------------------------------------------------------------------- #
class GeographyGeocodeTool(_GeographyTool):
    name = "geography.geocode"
    description = ("Convert a place name or address into coordinates. Requires a real "
                   "geocoding engine (Nominatim, Photon or equivalent). Reports "
                   "unavailable with remediation instead of inventing coordinates.")
    schema = {"type": "object", "properties": {"query": {"type": "string"}},
              "required": ["query"]}

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        return _ok(self.name, ctx, started, _unavailable(
            self.name, "geography.geocode",
            "no geocoding engine is installed or configured on this host",
            ["a local Nominatim or Photon instance",
             "a configured geocoding provider credential"],
        ), {"status": UNAVAILABLE})


class GeographyReverseGeocodeTool(_GeographyTool):
    name = "geography.reverse_geocode"
    description = ("Convert coordinates into a human-readable address. Requires a real "
                   "reverse geocoding engine. Reports unavailable with remediation "
                   "instead of inventing an address.")
    schema = {"type": "object",
              "properties": {"latitude": {"type": "number"},
                             "longitude": {"type": "number"}},
              "required": ["latitude", "longitude"]}

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        return _ok(self.name, ctx, started, _unavailable(
            self.name, "geography.reverse_geocode",
            "no reverse geocoding engine is installed or configured on this host",
            ["a local Nominatim or Photon instance",
             "a configured reverse geocoding provider credential"],
        ), {"status": UNAVAILABLE})


class GeographyRouteTool(_GeographyTool):
    name = "geography.route"
    description = ("Compute a travel route between coordinates. Requires a real routing "
                   "engine with a road graph. Great-circle distance is explicitly NOT "
                   "substituted for a route.")
    schema = {
        "type": "object",
        "properties": {
            "from": {"type": "object"},
            "to": {"type": "object"},
            "profile": {"type": "string", "enum": ["car", "bike", "foot"]},
        },
        "required": ["from", "to"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        payload = _unavailable(
            self.name, "geography.route",
            "no routing engine or road graph exists on this host",
            ["an OSRM, Valhalla or GraphHopper instance with an OSM extract",
             "a configured routing provider credential"],
        )
        payload["refused_substitute"] = {
            "great_circle_distance": "available via geography.distance",
            "reason": "a straight line is not a route; no distance, duration or "
                      "turn-by-turn value is reported",
        }
        return _ok(self.name, ctx, started, payload, {"status": UNAVAILABLE})


class GeographyPlaceSearchTool(_GeographyTool):
    name = "geography.place_search"
    description = ("Search for named places. Uses an authorized local place dataset when "
                   "one is configured, and otherwise reports unavailable rather than "
                   "returning model knowledge as if it were a place database.")
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "description": "Default 20, max 100."},
        },
        "required": ["query"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        args = args or {}
        query = str(args.get("query") or "").strip()
        if not query:
            return _fail(self.name, ctx, started, "query is required")
        limit = min(int(args.get("limit") or 20), MAX_SEARCH_RESULTS)

        try:
            matches = _search_map_files(query, limit)
        except MapDataUnavailable as exc:
            payload = _unavailable(
                self.name, "geography.place_search", str(exc),
                ["a local place dataset (GeoJSON/GPX/KML) inside the map root",
                 "a configured place-search provider"],
            )
            payload["local_map_status"] = _local_geometry_status()
            return _ok(self.name, ctx, started, payload, {"status": UNAVAILABLE})

        if not matches:
            payload = _unavailable(
                self.name, "geography.place_search",
                "no local place dataset is configured under the map root",
                ["a local place dataset (GeoJSON/GPX/KML) inside the map root"],
            )
            payload["local_map_status"] = _local_geometry_status()
            return _ok(self.name, ctx, started, payload, {"status": UNAVAILABLE})

        return _ok(self.name, ctx, started, {
            "status": AVAILABLE,
            "result_available": True,
            "query": query,
            "count": len(matches),
            "results": matches,
            "truncated": len(matches) >= limit,
            "provenance": self._provenance(ctx, SOURCE_LOCAL_MAP_DATA,
                                           searched_files=_LAST_SEARCH_FILES[0]),
        }, {"matches": len(matches)})


# --------------------------------------------------------------------------- #
# 9. geography.offline_search (local corpus / Kiwix, provenance-labelled)
# --------------------------------------------------------------------------- #
_LAST_SEARCH_FILES: List[int] = [0]


class GeographyOfflineSearchTool(_GeographyTool):
    name = "geography.offline_search"
    description = ("Search a configured local knowledge corpus for geographic knowledge. "
                   "Reports NOT_CONFIGURED when no corpus exists and never labels model "
                   "knowledge as corpus retrieval. ZIM archives require a ZIM reader.")
    required_permissions = SEARCH_PERMISSIONS
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "description": "Default 20, max 100."},
        },
        "required": ["query"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        args = args or {}
        query = str(args.get("query") or "").strip()
        if not query:
            return _fail(self.name, ctx, started, "query is required")
        limit = min(int(args.get("limit") or 20), MAX_SEARCH_RESULTS)
        needle = query.lower()

        zim = _zim_status()
        corpus_root, files, problem = _corpus_text_files()

        if not files:
            reason = problem or "configured corpus contains no searchable text files"
            return _ok(self.name, ctx, started, {
                "capability": "geography.offline_search",
                "status": NOT_CONFIGURED,
                "result_available": False,
                "data": None,
                "reason": reason,
                "kiwix": zim,
                "required_to_enable": [
                    "set JARVIS_KIWIX_CORPUS_PATH to a directory inside the workspace",
                    "install libzim to read .zim archives",
                ],
                "provenance": self._provenance(ctx, SOURCE_NONE),
                "note": "nothing was searched; no corpus was fabricated",
            }, {"status": NOT_CONFIGURED})

        results: List[Dict[str, Any]] = []
        scanned = 0
        for path in files:
            if len(results) >= limit:
                break
            scanned += 1
            try:
                if path.stat().st_size > MAX_CORPUS_FILE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lowered = text.lower()
            position = lowered.find(needle)
            if position < 0:
                continue
            start = max(0, position - MAX_SNIPPET_CHARS // 2)
            results.append({
                "file": _rel(path),
                "excerpt": text[start:start + MAX_SNIPPET_CHARS].strip(),
                "offset": position,
            })

        return _ok(self.name, ctx, started, {
            "capability": "geography.offline_search",
            "status": AVAILABLE,
            "result_available": True,
            "query": query,
            "count": len(results),
            "results": results,
            "files_scanned": scanned,
            "files_available": len(files),
            "truncated": len(results) >= limit,
            "kiwix": zim,
            "source_type": SOURCE_LOCAL_KIWIX if zim.get("zim_file_count") else
                           "LOCAL_CORPUS_TEXT",
            "provenance": self._provenance(
                ctx,
                SOURCE_LOCAL_KIWIX if zim.get("zim_file_count") else "LOCAL_CORPUS_TEXT",
                corpus_root=_rel(corpus_root) if corpus_root else None,
            ),
        }, {"matches": len(results), "files_scanned": scanned})


# --------------------------------------------------------------------------- #
# 10-11. geography.map_data.inspect / .search
# --------------------------------------------------------------------------- #
def _iter_features(document: Any, limit: int) -> Iterable[dict]:
    if not isinstance(document, dict):
        return []
    kind = document.get("type")
    if kind == "FeatureCollection":
        features = document.get("features")
        if isinstance(features, list):
            return [f for f in features[:limit] if isinstance(f, dict)]
        return []
    if kind == "Feature":
        return [document]
    return []


def _geometry_of(feature: dict) -> Optional[dict]:
    geometry = feature.get("geometry")
    return geometry if isinstance(geometry, dict) else None


def _iter_positions(geometry: Optional[dict], cap: int = 200_000) -> Iterable[Tuple[float, float]]:
    """Yield (longitude, latitude) pairs from any GeoJSON geometry."""
    if not geometry:
        return
    stack: List[Any] = [geometry.get("coordinates")]
    emitted = 0
    while stack and emitted < cap:
        node = stack.pop()
        if not isinstance(node, list):
            continue
        if (len(node) >= 2 and isinstance(node[0], (int, float))
                and isinstance(node[1], (int, float))
                and not isinstance(node[0], bool)):
            yield float(node[1]), float(node[0])
            emitted += 1
            continue
        for child in node:
            stack.append(child)


def _summarize(document: Any) -> Dict[str, Any]:
    features = list(_iter_features(document, MAX_FEATURES))
    geometry_types: Dict[str, int] = {}
    latitudes: List[float] = []
    longitudes: List[float] = []
    property_keys: set = set()

    for feature in features:
        geometry = _geometry_of(feature)
        if geometry and isinstance(geometry.get("type"), str):
            name = geometry["type"]
            geometry_types[name] = geometry_types.get(name, 0) + 1
        for lon, lat in _iter_positions(geometry):
            if -180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0:
                longitudes.append(lon)
                latitudes.append(lat)
        properties = feature.get("properties")
        if isinstance(properties, dict):
            for key in properties:
                if isinstance(key, str) and len(key) <= 80:
                    property_keys.add(key)

    summary: Dict[str, Any] = {
        "feature_count": len(features),
        "geometry_types": geometry_types,
        "property_keys": sorted(property_keys)[:80],
        "property_key_count": len(property_keys),
    }
    if latitudes and longitudes:
        summary["bounds"] = {
            "min_latitude": min(latitudes), "max_latitude": max(latitudes),
            "min_longitude": min(longitudes), "max_longitude": max(longitudes),
        }
    else:
        summary["bounds"] = None
    return summary


def _search_map_files(query: str, limit: int) -> List[Dict[str, Any]]:
    root = resolve_map_root()
    needle = query.lower()
    matches: List[Dict[str, Any]] = []
    scanned = 0
    for path in sorted(root.rglob("*")):
        if len(matches) >= limit:
            break
        if not path.is_file() or path.suffix.lower() not in GEO_SUFFIXES:
            continue
        if _is_secret_name(path.name):
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        try:
            document = _load_map_document(path)
        except MapDataUnavailable:
            continue
        scanned += 1
        for index, feature in enumerate(_iter_features(document, MAX_FEATURES)):
            if len(matches) >= limit:
                break
            properties = feature.get("properties")
            if not isinstance(properties, dict):
                continue
            for key, value in list(properties.items())[:100]:
                if not isinstance(value, str) or len(value) > MAX_PROPERTY_CHARS:
                    continue
                if needle in value.lower() or needle in str(key).lower():
                    geometry = _geometry_of(feature)
                    point: Optional[Dict[str, float]] = None
                    for lon, lat in _iter_positions(geometry, cap=1):
                        point = {"latitude": lat, "longitude": lon}
                        break
                    matches.append({
                        "file": _rel(path),
                        "feature_index": index,
                        "matched_key": str(key)[:80],
                        "matched_value": value[:MAX_SNIPPET_CHARS],
                        "geometry_type": (geometry or {}).get("type"),
                        "coordinates": point,
                    })
                    break
    _LAST_SEARCH_FILES[0] = scanned
    return matches


def _load_map_document(path: Path) -> Any:
    raw = _read_bounded_bytes(path)
    if len(raw) > MAX_FILE_BYTES:
        raise MapDataUnavailable("file exceeds the inspection limit")
    suffix = path.suffix.lower()
    if suffix == ".kmz":
        raise MapDataUnavailable(
            "KMZ archives are refused: extraction is not performed on untrusted input"
        )
    if suffix in (".gpx", ".kml"):
        if _DOCTYPE.search(raw[:4096]):
            raise MapDataUnavailable(
                "refused: XML DOCTYPE declaration present (entity-expansion risk)"
            )
        try:
            return ElementTree.fromstring(raw.decode("utf-8", errors="replace"))
        except ElementTree.ParseError as exc:
            raise MapDataUnavailable(f"malformed XML: {exc}") from exc
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise MapDataUnavailable(f"malformed JSON: {exc}") from exc


class GeographyMapInspectTool(_GeographyTool):
    name = "geography.map_data.inspect"
    description = ("Inspect an authorized local GeoJSON, GPX, KML or TopoJSON file: "
                   "format, size, digest, feature and geometry inventory, property keys "
                   "and bounding box. Read-only, workspace-confined, traversal refused.")
    required_permissions = DATA_PERMISSIONS
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Map file inside the map root."},
        },
        "required": ["path"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            path = resolve_map_file(args.get("path"))
            document = _load_map_document(path)
            raw = _read_bounded_bytes(path)

            payload: Dict[str, Any] = {
                "capability": "geography.map_data.inspect",
                "status": AVAILABLE,
                "result_available": True,
                "file": _rel(path),
                "format": path.suffix.lower().lstrip("."),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(raw),
                "provenance": self._provenance(ctx, SOURCE_LOCAL_MAP_DATA,
                                               file=_rel(path)),
            }

            if isinstance(document, ElementTree.Element):
                payload["xml_root"] = document.tag
                counts: Dict[str, int] = {}
                latitudes: List[float] = []
                longitudes: List[float] = []
                coordinate_tags = ("trkpt", "wpt", "rtept")
                feature_tags = ("trk", "trkseg", "rte", "rtept", "wpt", "Placemark",
                                "Point", "LineString", "Polygon", "LinearRing",
                                "coordinates")
                for element in document.iter():
                    tag = element.tag.rsplit("}", 1)[-1]
                    if tag not in feature_tags:
                        continue
                    counts[tag] = counts.get(tag, 0) + 1
                    if tag in coordinate_tags:
                        lat = element.get("lat")
                        lon = element.get("lon")
                        if lat and lon:
                            try:
                                latitudes.append(float(lat))
                                longitudes.append(float(lon))
                            except ValueError:
                                pass
                payload["element_counts"] = counts
                payload["bounds"] = (
                    {
                        "min_latitude": min(latitudes), "max_latitude": max(latitudes),
                        "min_longitude": min(longitudes), "max_longitude": max(longitudes),
                    }
                    if latitudes and longitudes else None
                )
            else:
                payload["document_type"] = (document or {}).get("type")
                payload["name"] = (document or {}).get("name")
                payload.update(_summarize(document))
                if "crs" in (document or {}):
                    payload["crs"] = document["crs"]

            return _ok(self.name, ctx, started, payload, {
                "size_bytes": payload["size_bytes"],
            })
        except MapDataUnavailable as exc:
            status = NOT_CONFIGURED if "configured" in str(exc) else UNAVAILABLE
            return _ok(self.name, ctx, started, {
                "capability": "geography.map_data.inspect",
                "status": status,
                "result_available": False,
                "data": None,
                "reason": str(exc),
                "local_map_status": _local_geometry_status(),
                "provenance": self._provenance(ctx, SOURCE_NONE),
            }, {"status": status})
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class GeographyMapSearchTool(_GeographyTool):
    name = "geography.map_data.search"
    description = ("Bounded literal search of feature attributes across authorized local "
                   "map files, returning matching features with geometry type and "
                   "coordinates. Never executes file content and never leaves the "
                   "authorized map root.")
    required_permissions = DATA_PERMISSIONS
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "description": "Default 20, max 100."},
        },
        "required": ["query"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            query = str(args.get("query") or "").strip()
            if not query:
                return _fail(self.name, ctx, started, "query is required")
            limit = min(int(args.get("limit") or 20), MAX_SEARCH_RESULTS)
            matches = _search_map_files(query, limit)
            return _ok(self.name, ctx, started, {
                "capability": "geography.map_data.search",
                "status": AVAILABLE,
                "result_available": True,
                "query": query,
                "count": len(matches),
                "results": matches,
                "files_scanned": _LAST_SEARCH_FILES[0],
                "truncated": len(matches) >= limit,
                "provenance": self._provenance(ctx, SOURCE_LOCAL_MAP_DATA),
            }, {"matches": len(matches)})
        except MapDataUnavailable as exc:
            status = NOT_CONFIGURED if "configured" in str(exc) else UNAVAILABLE
            return _ok(self.name, ctx, started, {
                "capability": "geography.map_data.search",
                "status": status,
                "result_available": False,
                "data": None,
                "reason": str(exc),
                "local_map_status": _local_geometry_status(),
                "provenance": self._provenance(ctx, SOURCE_NONE),
            }, {"status": status})
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- #
# 12. geography.organic_maps
# --------------------------------------------------------------------------- #
class GeographyOrganicMapsTool(_GeographyTool):
    name = "geography.organic_maps"
    description = ("Report whether an Organic Maps integration is executable on this host. "
                   "Organic Maps is only AVAILABLE with a real binary, map database or "
                   "app install; it is never simulated.")
    schema = {"type": "object", "properties": {}, "required": []}

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        return _ok(self.name, ctx, started, {
            "capability": "geography.organic_maps",
            "status": NOT_CONFIGURED,
            "result_available": False,
            "data": None,
            "reason": "no Organic Maps binary, map database or application install was "
                      "found on this host",
            "search_and_navigation": "not provided; no Organic Maps integration exists",
            "required_to_enable": [
                "an Organic Maps install exposing a queryable map database",
                "a documented local integration for search and routing",
            ],
            "provenance": self._provenance(ctx, SOURCE_NONE),
        }, {"status": NOT_CONFIGURED})


# --------------------------------------------------------------------------- #
# Domain status + exports
# --------------------------------------------------------------------------- #
GEOGRAPHY_TOOLS: tuple[type, ...] = (
    GeographyCoordinatesTool,
    GeographyDistanceTool,
    GeographyBearingTool,
    GeographyAreaTool,
    GeographyLocationInfoTool,
    GeographyGeocodeTool,
    GeographyReverseGeocodeTool,
    GeographyRouteTool,
    GeographyPlaceSearchTool,
    GeographyOfflineSearchTool,
    GeographyMapInspectTool,
    GeographyMapSearchTool,
    GeographyOrganicMapsTool,
)


def geography_tools() -> list:
    return [cls() for cls in GEOGRAPHY_TOOLS]


def geography_capability_status() -> Dict[str, Any]:
    """Truthful availability snapshot for the whole geography domain."""
    map_status = _local_geometry_status()
    zim = _zim_status()
    _, corpus_files, corpus_problem = _corpus_text_files()

    def entry(capability: str, status: str, offline: bool, reason: str = "") -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "capability_id": capability,
            "domain": "geography",
            "version": "1.0.0",
            "status": status,
            "supports_offline": offline,
        }
        if reason:
            row["reason"] = reason
        return row

    capabilities = [
        entry("geography.coordinates", AVAILABLE, True),
        entry("geography.distance", AVAILABLE, True),
        entry("geography.bearing", AVAILABLE, True),
        entry("geography.area", AVAILABLE, True),
        entry("geography.location_info", AVAILABLE, True),
        entry("geography.geocode", UNAVAILABLE, False, "no geocoding engine"),
        entry("geography.reverse_geocode", UNAVAILABLE, False,
              "no reverse geocoding engine"),
        entry("geography.route", UNAVAILABLE, False, "no routing engine or road graph"),
        entry("geography.place_search",
              AVAILABLE if map_status.get("geo_file_count") else UNAVAILABLE,
              False, None if map_status.get("geo_file_count")
              else "no local place dataset"),
        entry("geography.offline_search",
              AVAILABLE if corpus_files else NOT_CONFIGURED,
              True, None if corpus_files else (corpus_problem or "no corpus configured")),
        entry("geography.map_data.inspect",
              AVAILABLE if map_status.get("usable") else NOT_CONFIGURED,
              True, None if map_status.get("usable") else map_status.get("reason", "")),
        entry("geography.map_data.search",
              AVAILABLE if map_status.get("usable") else NOT_CONFIGURED,
              True, None if map_status.get("usable") else map_status.get("reason", "")),
        entry("geography.organic_maps", NOT_CONFIGURED, True,
              "no Organic Maps integration exists"),
    ]

    counts = {"total": len(capabilities)}
    for label in (AVAILABLE, UNAVAILABLE, NOT_CONFIGURED):
        counts[label] = sum(1 for row in capabilities if row["status"] == label)

    return {
        "domain": "geography",
        "version": VERSION,
        "capabilities": capabilities,
        "local_map_data": map_status,
        "kiwix": zim,
        "counts": counts,
    }
