"""Country boundary retrieval for country-focused malaria mapping."""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Any
from urllib.parse import urlparse

import requests

API_BASE = "https://www.geoboundaries.org/api/current/gbOpen"
ALLOWED_DOWNLOAD_HOSTS = {"www.geoboundaries.org", "geoboundaries.org", "github.com", "raw.githubusercontent.com"}
USER_AGENT = "AfricaMalariaIntelligence/1.0 (open-data research dashboard)"
REQUEST_TIMEOUT = 25


class BoundaryDataError(RuntimeError):
    """Raised when an authoritative country boundary cannot be resolved."""


def _coordinate_pairs(value: Any):
    """Yield longitude/latitude pairs from nested GeoJSON coordinates."""
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            yield float(value[0]), float(value[1])
        else:
            for child in value:
                yield from _coordinate_pairs(child)


def _metadata_record(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    if isinstance(payload, dict):
        return payload
    raise BoundaryDataError("geoBoundaries returned an unexpected country metadata response.")


def fetch_country_boundary(iso3: str) -> dict[str, Any]:
    """Fetch a validated ADM0 GeoJSON boundary and its Leaflet bounds."""
    code = str(iso3 or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError("Country must be a three-letter ISO3 code.")

    try:
        metadata_response = requests.get(
            f"{API_BASE}/{code}/ADM0/",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        metadata_response.raise_for_status()
        metadata = _metadata_record(metadata_response.json())
        download_url = metadata.get("simplifiedGeometryGeoJSON") or metadata.get("gjDownloadURL")
        if not isinstance(download_url, str):
            raise BoundaryDataError(f"geoBoundaries did not publish an ADM0 GeoJSON URL for {code}.")
        parsed = urlparse(download_url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS:
            raise BoundaryDataError("geoBoundaries returned an untrusted boundary download URL.")

        boundary_response = requests.get(
            download_url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json, application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        boundary_response.raise_for_status()
        geojson = boundary_response.json()
    except BoundaryDataError:
        raise
    except Exception as exc:
        raise BoundaryDataError(f"Could not retrieve the {code} country boundary: {exc}") from exc

    if not isinstance(geojson, dict) or geojson.get("type") != "FeatureCollection":
        raise BoundaryDataError(f"The {code} ADM0 boundary is not a GeoJSON FeatureCollection.")
    features = geojson.get("features")
    if not isinstance(features, list) or not features:
        raise BoundaryDataError(f"The {code} ADM0 boundary contains no features.")

    longitudes: list[float] = []
    latitudes: list[float] = []
    for feature in features:
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            continue
        for longitude, latitude in _coordinate_pairs(geometry.get("coordinates")):
            if -180 <= longitude <= 180 and -90 <= latitude <= 90:
                longitudes.append(longitude)
                latitudes.append(latitude)

    if not longitudes or not latitudes:
        raise BoundaryDataError(f"The {code} ADM0 boundary contains no valid polygon coordinates.")

    west, east = min(longitudes), max(longitudes)
    south, north = min(latitudes), max(latitudes)
    if west >= east or south >= north:
        raise BoundaryDataError(f"The {code} ADM0 boundary has invalid geographic bounds.")

    return {
        "iso3": code,
        "name": str(metadata.get("boundaryName") or code),
        "geojson": geojson,
        "bounds": [[south, west], [north, east]],
        "bbox": [west, south, east, north],
        "source_url": str(metadata.get("boundarySource") or "https://www.geoboundaries.org/"),
        "license": str(metadata.get("license") or metadata.get("boundaryLicense") or "See geoBoundaries metadata"),
    }



def fetch_admin1_boundaries(iso3: str) -> dict[str, Any]:
    """Fetch geoBoundaries open ADM1 geometry for one country."""
    code = str(iso3 or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError("Country must be a three-letter ISO3 code.")
    try:
        response = requests.get(
            f"{API_BASE}/{code}/ADM1/",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        metadata = _metadata_record(response.json())
        download_url = metadata.get("simplifiedGeometryGeoJSON") or metadata.get("gjDownloadURL")
        if not isinstance(download_url, str):
            raise BoundaryDataError(f"geoBoundaries has no ADM1 GeoJSON URL for {code}.")
        parsed = urlparse(download_url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS:
            raise BoundaryDataError("geoBoundaries returned an untrusted ADM1 download URL.")
        geometry_response = requests.get(
            download_url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json, application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        geometry_response.raise_for_status()
        geojson = geometry_response.json()
    except BoundaryDataError:
        raise
    except Exception as exc:
        raise BoundaryDataError(f"Could not retrieve {code} ADM1 boundaries: {exc}") from exc

    if not isinstance(geojson, dict) or geojson.get("type") != "FeatureCollection":
        raise BoundaryDataError(f"The {code} ADM1 boundary is not a GeoJSON FeatureCollection.")
    features = geojson.get("features")
    if not isinstance(features, list) or not features:
        raise BoundaryDataError(f"The {code} ADM1 boundary contains no administrative units.")
    valid = [
        feature for feature in features
        if isinstance(feature, dict)
        and isinstance(feature.get("geometry"), dict)
        and feature["geometry"].get("type") in {"Polygon", "MultiPolygon"}
    ]
    if not valid:
        raise BoundaryDataError(f"The {code} ADM1 boundary contains no polygon geometries.")
    geojson["features"] = valid
    return {
        "iso3": code,
        "geojson": geojson,
        "boundary_name": str(metadata.get("boundaryName") or code),
        "boundary_year": str(metadata.get("boundaryYearRepresented") or "Not specified"),
        "boundary_source": str(metadata.get("boundarySource") or "geoBoundaries"),
        "license": str(metadata.get("boundaryLicense") or "See geoBoundaries metadata"),
        "metadata_url": f"{API_BASE}/{code}/ADM1/",
    }


def _normalise_admin_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def join_admin1_estimates_to_geojson(
    geojson: dict[str, Any],
    admin_units: list[dict[str, Any]],
    estimates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Join MAP admin-1 estimates to boundary features using unique exact name matches.

    Ambiguous, duplicate, or unmatched names are deliberately excluded rather than guessed.
    """
    if not isinstance(geojson, dict) or geojson.get("type") != "FeatureCollection":
        raise ValueError("Expected a GeoJSON FeatureCollection.")
    ids_by_name: dict[str, list[str]] = {}
    names_by_id: dict[str, str] = {}
    for unit in admin_units:
        unit_id = str(unit.get("id", "")).strip()
        name = str(unit.get("name", "")).strip()
        key = _normalise_admin_name(name)
        if unit_id and key:
            ids_by_name.setdefault(key, []).append(unit_id)
            names_by_id[unit_id] = name

    def feature_name_key(feature: dict[str, Any]) -> str:
        props = feature.get("properties") or {}
        candidates = [
            props.get("shapeName"), props.get("shapeNameAlt"), props.get("name"),
            props.get("NAME_1"), props.get("ADM1_EN"), props.get("admin1Name"),
        ]
        return next((_normalise_admin_name(name) for name in candidates if _normalise_admin_name(name)), "")

    source_features = [feature for feature in geojson.get("features", []) if isinstance(feature, dict)]
    boundary_name_counts: dict[str, int] = {}
    for feature in source_features:
        key = feature_name_key(feature)
        if key:
            boundary_name_counts[key] = boundary_name_counts.get(key, 0) + 1

    features = []
    matched_ids = set()
    for original in source_features:
        key = feature_name_key(original)
        matches = ids_by_name.get(key, [])
        if not key or len(matches) != 1 or boundary_name_counts.get(key) != 1:
            continue
        unit_id = matches[0]
        props = dict(original.get("properties") or {})
        props["map_admin1_id"] = unit_id
        props["map_admin1_name"] = names_by_id[unit_id]
        feature = dict(original)
        feature["properties"] = props
        features.append(feature)
        matched_ids.add(unit_id)

    rows = []
    for row in estimates:
        unit_id = str(row.get("admin1_id", "")).strip()
        value = row.get("value")
        if unit_id not in matched_ids or value is None:
            continue
        if isinstance(value, (int, float)) and not math.isfinite(value):
            continue
        joined = dict(row)
        joined["map_admin1_id"] = unit_id
        joined["admin1_name"] = names_by_id[unit_id]
        rows.append(joined)

    return {
        "geojson": {"type": "FeatureCollection", "features": features},
        "rows": rows,
        "matched_units": len(matched_ids),
        "total_map_units": len(names_by_id),
        "unmatched_map_names": sorted(names_by_id[x] for x in set(names_by_id) - matched_ids),
    }
