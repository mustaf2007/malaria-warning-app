"""Open-data connectors. No credentials or paid API keys are required."""
from __future__ import annotations
import time
from typing import Any
import requests
from .config import INDICATORS, REQUEST_TIMEOUT, USER_AGENT

WB_BASE = "https://api.worldbank.org/v2"
WHO_GHO_BASE = "https://ghoapi.azureedge.net/api"

class DataSourceError(RuntimeError):
    """Raised when a public source cannot provide a usable response."""


def _get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.6 * (attempt + 1))
    raise DataSourceError(f"Unable to retrieve public data: {last_error}")


def fetch_african_countries() -> list[dict[str, str]]:
    """Return World Bank country metadata for African economies only."""
    payload = _get_json(f"{WB_BASE}/country", {"format": "json", "per_page": 400})
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        raise DataSourceError("World Bank country metadata returned an unexpected format.")
    countries = []
    for row in payload[1]:
        region = (row.get("region") or {}).get("value", "")
        iso3 = row.get("id")
        iso2 = row.get("iso2Code")
        if region == "Africa" and iso3 and iso2 and iso2 != "ZH":
            countries.append({"iso3": iso3, "iso2": iso2, "name": row.get("name", iso3), "region": region})
    return sorted(countries, key=lambda item: item["name"])


def fetch_world_bank_indicator(code: str, start_year: int = 2000, end_year: int = 2024) -> list[dict[str, Any]]:
    """Fetch an indicator for all countries; null observations are retained as missing."""
    if not code or not code.replace(".", "").replace("_", "").isalnum():
        raise ValueError("Invalid World Bank indicator code.")
    page = 1
    rows: list[dict[str, Any]] = []
    while True:
        payload = _get_json(
            f"{WB_BASE}/country/all/indicator/{code}",
            {"format": "json", "per_page": 20000, "page": page, "date": f"{start_year}:{end_year}"},
        )
        if not isinstance(payload, list) or len(payload) < 2:
            raise DataSourceError(f"World Bank returned an unexpected response for {code}.")
        metadata, observations = payload[0], payload[1]
        for item in observations or []:
            country = item.get("country") or {}
            iso3 = (item.get("countryiso3code") or "").strip()
            value = item.get("value")
            if iso3 and item.get("date"):
                rows.append({
                    "iso3": iso3,
                    "country": country.get("value", iso3),
                    "year": int(item["date"]),
                    "indicator_code": code,
                    "value": float(value) if value is not None else None,
                    "source": "World Bank",
                    "source_url": f"https://data.worldbank.org/indicator/{code}",
                    "last_updated": item.get("obs_status") or None,
                })
        if not metadata or page >= int(metadata.get("pages", 1)):
            break
        page += 1
    return rows


def discover_who_malaria_indicators() -> list[dict[str, str]]:
    """Discover malaria-related indicator codes from the WHO GHO OData catalogue."""
    payload = _get_json(f"{WHO_GHO_BASE}/Indicator", {"$format": "json", "$top": 5000})
    values = payload.get("value", []) if isinstance(payload, dict) else []
    matches = []
    for item in values:
        name = str(item.get("IndicatorName") or "")
        code = str(item.get("IndicatorCode") or "")
        if code and "malaria" in name.lower():
            matches.append({"code": code, "name": name, "source": "WHO Global Health Observatory"})
    return sorted(matches, key=lambda item: item["name"])


def fetch_who_gho_indicator(code: str) -> list[dict[str, Any]]:
    """Fetch a selected WHO GHO indicator code; source fields are preserved."""
    if not code or not code.replace("_", "").isalnum():
        raise ValueError("Invalid WHO GHO indicator code.")
    payload = _get_json(f"{WHO_GHO_BASE}/{code}", {"$format": "json", "$top": 10000})
    values = payload.get("value", []) if isinstance(payload, dict) else []
    output = []
    for item in values:
        year = item.get("TimeDim")
        country = item.get("SpatialDim")
        value = item.get("NumericValue")
        if year and country:
            try:
                output.append({
                    "iso3": str(country), "country": str(country), "year": int(year),
                    "indicator_code": code, "value": float(value) if value is not None else None,
                    "source": "WHO Global Health Observatory",
                    "source_url": f"https://www.who.int/data/gho/data/indicators/indicator-details/GHO/{code}",
                    "last_updated": item.get("TimeDimensionValue"),
                })
            except (TypeError, ValueError):
                continue
    return output


def fetch_indicator_bundle(start_year: int = 2000, end_year: int = 2024, codes: list[str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Fetch available catalogue indicators independently; failures are reported, not hidden."""
    selected = codes or [item.code for item in INDICATORS]
    all_rows: list[dict[str, Any]] = []
    statuses: list[dict[str, str]] = []
    for code in selected:
        try:
            rows = fetch_world_bank_indicator(code, start_year, end_year)
            all_rows.extend(rows)
            valid = sum(row["value"] is not None for row in rows)
            statuses.append({"code": code, "status": "loaded" if valid else "no observations", "records": str(len(rows)), "non_missing": str(valid), "source": "World Bank"})
        except Exception as exc:
            statuses.append({"code": code, "status": "unavailable", "records": "0", "non_missing": "0", "source": f"World Bank: {exc}"})
    return all_rows, statuses
