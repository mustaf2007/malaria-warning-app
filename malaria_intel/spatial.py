"""Country boundary retrieval for country-focused malaria mapping."""
from __future__ import annotations

import re
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
