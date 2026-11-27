"""Open-data connectors. No credentials or paid API keys are required."""
from __future__ import annotations
import time
from io import StringIO
from typing import Any
from urllib.parse import urljoin, urlsplit
import pandas as pd
import requests
from .config import INDICATORS, OWID_DATASETS, REQUEST_TIMEOUT, USER_AGENT

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



def _get_odata_rows(url: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Read WHO OData pages safely; reject malformed, off-host, or truncated results."""
    expected_host = urlsplit(WHO_GHO_BASE).hostname
    initial = urlsplit(url)
    try:
        initial_port = initial.port
    except ValueError as exc:
        raise DataSourceError("WHO OData request has an invalid API port.") from exc
    if (
        initial.scheme != "https"
        or initial.hostname != expected_host
        or initial_port not in (None, 443)
        or initial.username
        or initial.password
    ):
        raise DataSourceError("WHO OData request must use the official HTTPS API host and port.")

    def read_page(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
        if not isinstance(payload, dict):
            raise DataSourceError("WHO OData returned an unexpected response schema.")
        values = payload.get("value")
        if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
            raise DataSourceError("WHO OData response is missing a valid records list.")
        next_link = payload.get("@odata.nextLink") or payload.get("odata.nextLink")
        if next_link is not None and not isinstance(next_link, str):
            raise DataSourceError("WHO OData returned an invalid pagination link.")
        return values, next_link

    payload = _get_json(url, params)
    page_rows, next_link = read_page(payload)
    output = list(page_rows)
    current_url = url
    pages_read = 1
    max_pages = 100

    while next_link:
        if pages_read >= max_pages:
            raise DataSourceError(
                f"WHO OData pagination exceeded the {max_pages}-page safety limit; results may be incomplete."
            )
        next_url = urljoin(current_url, next_link)
        parsed = urlsplit(next_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != expected_host
            or parsed.port not in (None, 443)
            or parsed.username
            or parsed.password
        ):
            raise DataSourceError("WHO OData supplied a pagination link outside the official HTTPS API host.")
        payload = _get_json(next_url)
        page_rows, next_link = read_page(payload)
        output.extend(page_rows)
        current_url = next_url
        pages_read += 1

    return output


# ISO3 codes for the 54 sovereign African countries. Use geography rather than
# exact World Bank region labels, which can change or classify North Africa
# under a separate regional grouping.
AFRICAN_COUNTRY_ISO3 = frozenset({
    "AGO", "BEN", "BWA", "BFA", "BDI", "CPV", "CMR", "CAF", "TCD",
    "COM", "COD", "COG", "CIV", "DJI", "EGY", "GNQ", "ERI", "SWZ",
    "ETH", "GAB", "GMB", "GHA", "GIN", "GNB", "KEN", "LSO", "LBR",
    "LBY", "MDG", "MWI", "MLI", "MRT", "MUS", "MAR", "MOZ", "NAM",
    "NER", "NGA", "RWA", "STP", "SEN", "SYC", "SLE", "SOM", "ZAF",
    "SSD", "SDN", "TZA", "TGO", "TUN", "UGA", "ZMB", "ZWE", "DZA",
})


def fetch_african_countries() -> list[dict[str, str]]:
    """Return World Bank metadata for the 54 sovereign African countries."""
    payload = _get_json(f"{WB_BASE}/country", {"format": "json", "per_page": 400})
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        raise DataSourceError("World Bank country metadata returned an unexpected format.")
    countries = []
    for row in payload[1]:
        iso3 = str(row.get("id") or "").upper()
        iso2 = row.get("iso2Code")
        if iso3 in AFRICAN_COUNTRY_ISO3 and iso2 and iso2 != "ZH":
            countries.append({
                "iso3": iso3,
                "iso2": iso2,
                "name": row.get("name", iso3),
                "region": (row.get("region") or {}).get("value", ""),
            })
    return sorted(countries, key=lambda item: item["name"])


def fetch_world_bank_indicator(code: str, start_year: int = 1960, end_year: int | None = None) -> list[dict[str, Any]]:
    """Fetch an indicator for all countries; null observations are retained as missing."""
    if end_year is None:
        from datetime import datetime, timezone
        end_year = datetime.now(timezone.utc).year
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
    # GHO is OData and returns JSON by default. Some Azure API front doors reject
    # the explicit $format=json parameter and oversized $top values. Follow the
    # server-provided @odata.nextLink rather than requesting thousands at once.
    values = _get_odata_rows(f"{WHO_GHO_BASE}/Indicator", {"$top": 1000})
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
    # Use OData default JSON and bounded pages, matching the discovery endpoint.
    # _get_odata_rows follows the server-provided @odata.nextLink.
    values = _get_odata_rows(f"{WHO_GHO_BASE}/{code}", {"$top": 1000})
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


def fetch_indicator_bundle(start_year: int = 1960, end_year: int | None = None, codes: list[str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Fetch available catalogue indicators independently; failures are reported, not hidden."""
    if end_year is None:
        from datetime import datetime, timezone
        end_year = datetime.now(timezone.utc).year
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


def fetch_owid_grapher(slug: str, start_year: int = 1960, end_year: int | None = None) -> list[dict[str, Any]]:
    """Fetch a documented Our World in Data Grapher CSV and normalize country rows."""
    if end_year is None:
        from datetime import datetime, timezone
        end_year = datetime.now(timezone.utc).year
    if slug not in OWID_DATASETS:
        raise ValueError("The requested Our World in Data series is not in the approved catalogue.")
    url = f"https://ourworldindata.org/grapher/{slug}.csv?v=1&csvType=full&useColumnShortNames=false"
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        frame = pd.read_csv(StringIO(response.text))
    except Exception as exc:
        raise DataSourceError(f"Our World in Data series {slug} could not be retrieved: {exc}") from exc
    required = {"Entity", "Code", "Year"}
    if not required.issubset(frame.columns):
        raise DataSourceError(f"Unexpected Our World in Data CSV schema for {slug}.")
    value_columns = [column for column in frame.columns if column not in required]
    if len(value_columns) != 1:
        raise DataSourceError(f"Expected one value column in Our World in Data series {slug}.")
    value_column = value_columns[0]
    frame["Year"] = pd.to_numeric(frame["Year"], errors="coerce")
    frame[value_column] = pd.to_numeric(frame[value_column], errors="coerce")
    frame = frame[(frame["Year"] >= start_year) & (frame["Year"] <= end_year)]
    output = []
    for item in frame.to_dict(orient="records"):
        iso3 = str(item.get("Code") or "").strip()
        if len(iso3) != 3 or iso3.lower() == "nan":
            continue
        output.append({
            "iso3": iso3.upper(), "country": str(item.get("Entity") or iso3),
            "year": int(item["Year"]), "indicator_code": f"OWID:{slug}",
            "value": float(item[value_column]) if pd.notna(item[value_column]) else None,
            "source": "Our World in Data (original source noted in dataset metadata)",
            "source_url": url, "last_updated": None,
        })
    return output


def fetch_owid_bundle(start_year: int = 1960, end_year: int | None = None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Fetch each approved OWID malaria series independently and report connector status."""
    if end_year is None:
        from datetime import datetime, timezone
        end_year = datetime.now(timezone.utc).year
    rows: list[dict[str, Any]] = []
    statuses: list[dict[str, str]] = []
    for slug in OWID_DATASETS:
        try:
            current = fetch_owid_grapher(slug, start_year, end_year)
            rows.extend(current)
            statuses.append({"code": f"OWID:{slug}", "status": "loaded" if current else "no observations", "records": str(len(current)), "non_missing": str(sum(r["value"] is not None for r in current)), "source": "Our World in Data"})
        except Exception as exc:
            statuses.append({"code": f"OWID:{slug}", "status": "unavailable", "records": "0", "non_missing": "0", "source": f"Our World in Data: {exc}"})
    return rows, statuses


# Malaria Atlas Project public Trends API. Metric path tokens are case-sensitive.
MAP_BASE = "https://data.malariaatlas.org/map-platform-app-backend/api/v1"
MAP_METRICS = {
    "Pf_incidence-count": {"name": "P. falciparum clinical cases", "group": "Burden", "unit": "estimated cases", "availability_key": "pfIncidenceRate"},
    "Pf_incidence-rate": {"name": "P. falciparum clinical incidence", "group": "Burden", "unit": "cases per 1,000 population per year", "availability_key": "pfIncidenceRate"},
    "Pf_PR-rate": {"name": "P. falciparum parasite prevalence (PfPR2-10)", "group": "Burden", "unit": "proportion", "availability_key": "pfpr"},
    "Pf_mortality-count": {"name": "P. falciparum deaths", "group": "Burden", "unit": "estimated deaths", "availability_key": "pfMortalityRate"},
    "Pf_mortality-rate": {"name": "P. falciparum mortality rate", "group": "Burden", "unit": "deaths per 100,000 population per year", "availability_key": "pfMortalityRate"},
    "Pv_incidence-count": {"name": "P. vivax clinical cases", "group": "Burden", "unit": "estimated cases", "availability_key": "pvIncidenceRate"},
    "Pv_incidence-rate": {"name": "P. vivax clinical incidence", "group": "Burden", "unit": "cases per 1,000 population per year", "availability_key": "pvIncidenceRate"},
    "Pv_PR-rate": {"name": "P. vivax parasite prevalence", "group": "Burden", "unit": "proportion", "availability_key": "pvpr"},
    "Antimalarial_EFT-rate": {"name": "Effective antimalarial treatment", "group": "Interventions", "unit": "proportion", "availability_key": "effectiveTreatment"},
    "IRS_coverage-rate": {"name": "Indoor residual spraying coverage", "group": "Interventions", "unit": "proportion", "availability_key": "irsCoverage"},
    "ITN_use-rate": {"name": "Population sleeping under insecticide-treated nets", "group": "Interventions", "unit": "proportion", "availability_key": "itnUse"},
    "ITN_access-rate": {"name": "Population with access to insecticide-treated nets", "group": "Interventions", "unit": "proportion", "availability_key": "itnAccess"},
    "ITN_use_rate-rate": {"name": "ITN use among people with household access", "group": "Interventions", "unit": "proportion", "availability_key": "itnUseRate"},
}


def fetch_map_releases() -> list[dict[str, Any]]:
    """Fetch MAP release metadata; callers must choose an explicit release."""
    payload = _get_json(f"{MAP_BASE}/trends/metadata")
    if not isinstance(payload, list):
        raise DataSourceError("MAP release metadata returned an unexpected schema.")
    releases = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("version"):
            continue
        releases.append({
            "version": str(item["version"]),
            "data_end_year": int(item.get("dataEndYear") or 0),
            "provisional": bool(item.get("provisional", False)),
            "admin_version": (item.get("geoServerRefs") or {}).get("mapAdminVersion", ""),
            "geo_server_refs": item.get("geoServerRefs") or {},
        })
    return releases


def fetch_map_admin1(country_iso3: str, admin_version: str) -> list[dict[str, str]]:
    """Resolve subnational admin-1 IDs for one African country and MAP boundary release."""
    if len(country_iso3) != 3 or not country_iso3.isalpha():
        raise ValueError("Country must be a three-letter ISO3 code.")
    if not admin_version or not all(ch.isalnum() or ch in "._-" for ch in admin_version):
        raise ValueError("Invalid MAP administrative boundary version.")
    payload = _get_json(
        f"https://data.malariaatlas.org/admin-unit-metadata/admin-units/ADMIN1",
        {"mapAdmin": admin_version},
    )
    if isinstance(payload, dict):
        records = payload.get("features") or payload.get("data") or payload.get("results") or []
    elif isinstance(payload, list):
        records = payload
    else:
        raise DataSourceError("MAP administrative-unit catalogue returned an unexpected schema.")
    output = []
    for item in records:
        props = item.get("properties", item) if isinstance(item, dict) else {}
        iso3 = str(props.get("iso3") or props.get("ISO3") or "").upper()
        if iso3 != country_iso3.upper():
            continue
        unit_id = props.get("id") or props.get("ID")
        name = props.get("name") or props.get("NAME_1") or props.get("admin1Name")
        if unit_id is not None and name:
            output.append({"id": str(unit_id), "name": str(name), "country": str(props.get("countryName") or props.get("country") or country_iso3), "iso3": iso3})
    return sorted(output, key=lambda item: item["name"])


def _jsonstat_rows(payload: dict[str, Any], geography_level: str, metric: str, stat: str, source_url: str) -> list[dict[str, Any]]:
    """Decode MAP JSON-stat data using category indexes, not assumed positional order."""
    if not isinstance(payload, dict):
        raise DataSourceError("MAP JSON-stat response must be an object.")
    dimension = payload.get("dimension")
    if not isinstance(dimension, dict):
        raise DataSourceError("MAP JSON-stat response is missing dimension metadata.")
    geo_key = "ISO" if geography_level == "admin0" else "ID"
    geo_dim = dimension.get(geo_key)
    year_dim = dimension.get("Year")
    if not isinstance(geo_dim, dict) or not isinstance(year_dim, dict):
        raise DataSourceError("MAP JSON-stat response is missing geography or year dimensions.")
    geo_category = geo_dim.get("category") or {}
    year_category = year_dim.get("category") or {}
    if not isinstance(geo_category, dict) or not isinstance(year_category, dict):
        raise DataSourceError("MAP JSON-stat category metadata is malformed.")
    geo_index = geo_category.get("index")
    year_index = year_category.get("index")
    geo_labels = geo_category.get("label") or {}
    if isinstance(geo_index, list):
        geo_index = {code: index for index, code in enumerate(geo_index)}
    if isinstance(year_index, list):
        year_index = {year: index for index, year in enumerate(year_index)}
    if not isinstance(geo_index, dict) or not isinstance(year_index, dict) or not geo_index or not year_index:
        raise DataSourceError("MAP JSON-stat category indexes have an unsupported or empty format.")
    try:
        geo_positions = [int(index) for index in geo_index.values()]
        year_positions = [int(index) for index in year_index.values()]
        years = [(int(year), int(index)) for year, index in year_index.items()]
        geos = [(str(code), int(index)) for code, index in geo_index.items()]
    except (TypeError, ValueError) as exc:
        raise DataSourceError("MAP JSON-stat category indexes contain invalid positions or years.") from exc
    if (
        sorted(geo_positions) != list(range(len(geo_positions)))
        or sorted(year_positions) != list(range(len(year_positions)))
        or len(set(year for year, _ in years)) != len(years)
        or any(not code for code, _ in geos)
    ):
        raise DataSourceError("MAP JSON-stat category indexes must be unique and contiguous from zero.")
    years.sort(key=lambda item: item[1])
    geos.sort(key=lambda item: item[1])
    values = payload.get("value")
    if isinstance(values, dict):
        value_at = lambda index: values.get(str(index))
        received = len(values)
    elif isinstance(values, list):
        value_at = lambda index: values[index]
        received = len(values)
    else:
        raise DataSourceError("MAP JSON-stat values must be an array or indexed object.")
    expected = len(geos) * len(years)
    if received < expected:
        raise DataSourceError(f"MAP JSON-stat values are incomplete: expected {expected}, received {received}.")
    output = []
    for geo_code, geo_pos in geos:
        for year, year_pos in years:
            raw_value = value_at(geo_pos * len(years) + year_pos)
            try:
                value = float(raw_value) if raw_value is not None else None
            except (TypeError, ValueError):
                value = None
            # MAP documents zero as a possible missing-estimate sentinel.
            # Preserve it but mark it explicitly for downstream interpretation.
            output.append({
                "iso3": geo_code if geography_level == "admin0" else "",
                "admin1_id": geo_code if geography_level == "admin1" else "",
                "country": geo_labels.get(geo_code, geo_code),
                "year": year, "indicator_code": f"MAP:{metric}",
                "value": value, "source": f"Malaria Atlas Project · {stat}",
                "source_url": source_url, "map_release": payload.get("version"),
                "map_stat": stat, "possible_missing_zero": value == 0,
            })
    return output


def fetch_map_series(metric: str, version: str, geography_level: str = "admin0",
                     iso3: str | None = None, admin_unit_id: str | None = None,
                     stat: str = "mean") -> list[dict[str, Any]]:
    """Fetch a filtered MAP national or subnational time series from one explicit release."""
    if metric not in MAP_METRICS:
        raise ValueError("Unsupported MAP metric.")
    if stat not in {"mean", "lci", "uci"}:
        raise ValueError("Statistic must be mean, lci or uci.")
    if geography_level not in {"admin0", "admin1"}:
        raise ValueError("Geography level must be admin0 or admin1.")
    if not version or not version.isdigit():
        raise ValueError("Select a valid explicit MAP release.")
    if bool(iso3) == bool(admin_unit_id):
        raise ValueError("Provide exactly one geography filter: ISO3 or administrative-unit ID.")
    if iso3 and (geography_level != "admin0" and geography_level != "admin1"):
        raise ValueError("Invalid geography filter.")
    if admin_unit_id and not admin_unit_id.isdigit():
        raise ValueError("Invalid administrative-unit ID.")
    params = {"version": version, "iso3": iso3} if iso3 else {"version": version, "adminUnitId": admin_unit_id}
    url = f"{MAP_BASE}/trends/{'malaria' if MAP_METRICS[metric]['group'] == 'Burden' else 'interventions'}/{metric}/{geography_level}/{stat}"
    payload = _get_json(url, params)
    if not isinstance(payload, dict) or "dimension" not in payload or "value" not in payload:
        raise DataSourceError("MAP Trends API returned an unexpected JSON-stat response.")
    rows = _jsonstat_rows(payload, geography_level, metric, stat, url)
    for row in rows:
        row["source_url"] = f"{url}?version={version}&" + (f"iso3={iso3}" if iso3 else f"adminUnitId={admin_unit_id}")
        row["map_release"] = version
        row["map_provisional"] = None
    return rows


# MAP high-resolution WMS raster layers. The layer reference is read from the
# selected release metadata; no layer names or release IDs are guessed.
MAP_WMS_BASE = "https://data.malariaatlas.org/geoserver"


def resolve_map_wms_layer(layer_ref: str) -> dict[str, Any]:
    """Resolve a release raster and its published temporal dimension from WMS capabilities."""
    import re
    import xml.etree.ElementTree as ET

    if not isinstance(layer_ref, str) or not layer_ref.strip():
        raise ValueError("The selected MAP release does not advertise this raster layer.")
    layer_ref = layer_ref.strip()
    if not re.fullmatch(r"[A-Za-z0-9_:.\-]+", layer_ref):
        raise ValueError("MAP raster reference contains unsupported characters.")
    workspace = layer_ref.split("__", 1)[0] if "__" in layer_ref else layer_ref.split(":", 1)[0]
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", workspace):
        raise ValueError("Invalid MAP GeoServer workspace.")
    endpoint = f"{MAP_WMS_BASE}/{workspace}/ows"
    response = requests.get(
        endpoint,
        params={"service": "WMS", "request": "GetCapabilities", "version": "1.1.1"},
        headers={"User-Agent": USER_AGENT, "Accept": "application/xml,text/xml"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise DataSourceError("MAP WMS capabilities returned invalid XML.") from exc
    candidates = {layer_ref}
    if "__" in layer_ref:
        prefix, suffix = layer_ref.split("__", 1)
        candidates.add(f"{prefix}:{suffix}")
    if ":" in layer_ref:
        prefix, suffix = layer_ref.split(":", 1)
        candidates.add(f"{prefix}__{suffix}")

    matched = None
    time_values = None
    for layer in root.iter():
        if layer.tag.rsplit("}", 1)[-1] != "Layer":
            continue
        direct = {
            child.tag.rsplit("}", 1)[-1]: child
            for child in list(layer)
        }
        name_node = direct.get("Name")
        if name_node is None or not name_node.text or name_node.text.strip() not in candidates:
            continue
        matched = name_node.text.strip()
        for child in list(layer):
            if child.tag.rsplit("}", 1)[-1] in {"Dimension", "Extent"} and child.attrib.get("name", "").lower() == "time":
                time_values = (child.text or "").strip() or None
                break
        break

    if not matched:
        raise DataSourceError(
            f"MAP WMS did not advertise the release layer '{layer_ref}'. "
            "The release may not expose this layer through WMS."
        )

    years = sorted({int(value) for value in re.findall(r"(?<!\d)(?:19|20|21)\d{2}(?!\d)", time_values or "")})
    if time_values and "/" in time_values and len(years) >= 2:
        available_years = list(range(years[0], years[-1] + 1))
    else:
        available_years = years
    return {
        "workspace": workspace,
        "endpoint": endpoint,
        "layer": matched,
        "time_values": time_values,
        "available_years": available_years,
        "min_year": min(available_years) if available_years else None,
        "max_year": max(available_years) if available_years else None,
    }


def map_wms_time_for_year(layer_info: dict[str, Any], year: int | None) -> str | None:
    """Return a WMS TIME value that is valid for the selected layer and year."""
    import re

    values = layer_info.get("time_values")
    if not values:
        if year is not None:
            raise ValueError("This MAP raster is static and does not accept a reference year.")
        return None
    if not isinstance(year, int):
        raise ValueError("Select a year for this time-varying MAP raster.")
    if year not in layer_info.get("available_years", []):
        raise ValueError(f"Year {year} is not available for this MAP raster layer.")
    # GeoServer may advertise a compact interval or a comma-separated list
    # of exact timestamps. Preserve the exact advertised timestamp when listed.
    if "/" not in values:
        matches = [
            item.strip() for item in values.split(",")
            if re.search(rf"(?<!\d){year}(?!\d)", item)
        ]
        if matches:
            return matches[0]
        raise DataSourceError(f"MAP WMS does not advertise a timestamp for {year}.")
    return f"{year}-01-01T00:00:00.000Z"

def fetch_map_wms_preview(layer_ref: str, year: int | None, width: int = 1600, height: int = 900) -> bytes:
    """Fetch a bounded Africa-wide WMS preview of a selected MAP 5 km raster."""
    if year is not None and (not isinstance(year, int) or year < 1900 or year > 2100):
        raise ValueError("Select a valid raster year.")
    if not (400 <= width <= 2000 and 300 <= height <= 1400):
        raise ValueError("Raster preview dimensions are outside the allowed limits.")
    resolved = resolve_map_wms_layer(layer_ref)
    time_value = map_wms_time_for_year(resolved, year)
    params = {
        "service": "WMS", "version": "1.1.1", "request": "GetMap",
        "layers": resolved["layer"], "styles": "", "srs": "EPSG:4326",
        "bbox": "-18,-36,52,38", "width": str(width), "height": str(height),
        "format": "image/png", "transparent": "true",
    }
    if time_value:
        params["time"] = time_value
    response = requests.get(
        resolved["endpoint"], params=params,
        headers={"User-Agent": USER_AGENT, "Accept": "image/png"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()
    if "image/png" not in content_type or not response.content.startswith(b"\x89PNG\r\n\x1a\n"):
        message = response.text[:240] if "text" in content_type or "xml" in content_type else "non-PNG response"
        raise DataSourceError(f"MAP WMS did not return a PNG raster image: {message}")
    return response.content



def fetch_dashboard_bundle(start_year: int = 1960, end_year: int | None = None) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[dict[str, str]]]:
    """Load dashboard sources independently so one outage cannot blank the whole app."""
    if end_year is None:
        from datetime import datetime, timezone
        end_year = datetime.now(timezone.utc).year
    countries: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    statuses: list[dict[str, str]] = []

    try:
        countries = fetch_african_countries()
        statuses.append({"code": "COUNTRY_METADATA", "status": "loaded", "records": str(len(countries)), "non_missing": str(len(countries)), "source": "World Bank"})
    except Exception as exc:
        statuses.append({"code": "COUNTRY_METADATA", "status": "unavailable", "records": "0", "non_missing": "0", "source": f"World Bank country metadata: {exc}"})

    try:
        wb_rows, wb_status = fetch_indicator_bundle(start_year, end_year)
        rows.extend(wb_rows)
        statuses.extend(wb_status)
    except Exception as exc:
        statuses.append({"code": "WORLD_BANK_BUNDLE", "status": "unavailable", "records": "0", "non_missing": "0", "source": f"World Bank indicators: {exc}"})

    try:
        owid_rows, owid_status = fetch_owid_bundle(start_year, end_year)
        rows.extend(owid_rows)
        statuses.extend(owid_status)
    except Exception as exc:
        statuses.append({"code": "OWID_BUNDLE", "status": "unavailable", "records": "0", "non_missing": "0", "source": f"Our World in Data: {exc}"})

    return countries, rows, statuses
