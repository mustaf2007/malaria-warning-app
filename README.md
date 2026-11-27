# 🦟 Africa Malaria Intelligence

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://gdp-dashboard-template.streamlit.app/)

A Streamlit-based, open-data research and programme-intelligence workspace for malaria burden, trends and contextual health indicators across African countries.

## Current implementation

- Executive overview with latest available observations and country coverage.
- Country profiles and historical indicator trends.
- Country comparisons and year-on-year change calculations.
- Country-level choropleth maps, a MAP national/subnational time-series workspace, and an interactive country-focused high-resolution raster explorer with ADM0 boundary overlays and release-advertised GeoServer WMS layers.
- Prevention, population vulnerability and health-system context indicators where data is available.
- Exploratory linear trend extrapolation with an explicit non-operational warning.
- Model-free analyst that computes answers from loaded observations rather than inventing unsupported facts.
- CSV and Excel exports, supplementary CSV upload, source status and data-quality reporting.
- Emerald, navy, light and dark appearance themes.
- World Bank API connector and WHO GHO malaria-indicator catalogue discovery.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Data and provenance

The application requests country metadata and indicator observations from the World Bank API, retrieves selected WHO Global Health Observatory (GHO) malaria series through its OData API, and imports approved Our World in Data Grapher CSV series (estimated cases, estimated deaths and malaria death rate). The indicator catalogue is maintained in `malaria_intel/config.py`; each indicator has a code, definition, unit, group and interpretation type. The WHO GHO OData catalogue can be queried from the Data Quality & Sources workspace to discover additional malaria-related indicators and fetch selected series.

The following authoritative resources are linked for data integration, further verification and future expansion:

- [MAP public data access guide](https://data.malariaatlas.org/llms.txt) — service endpoints, metric tokens, release handling, spatial services and attribution requirements.

- [WHO Global Health Observatory](https://www.who.int/data/gho)
- [WHO World Malaria Report](https://www.who.int/teams/global-malaria-programme/reports/world-malaria-report)
- [Malaria Atlas Project Data Platform](https://data.malariaatlas.org/) — integrated MAP Trends API for explicit-release national and admin-1 estimates, plus an interactive WMS raster explorer for release-advertised high-resolution layers. Raster layers are resolved against WMS GetCapabilities before display.
- [geoBoundaries](https://www.geoboundaries.org/) — open ADM0 boundary geometry used to focus the interactive map on a selected country; check the boundary metadata for dataset-specific licensing and citation.
- [World Bank Open Data](https://data.worldbank.org/)
- [UNICEF Data](https://data.unicef.org/)
- [Our World in Data — Malaria](https://ourworldindata.org/malaria)

No API key is required for the core World Bank, WHO GHO, Our World in Data and MAP public requests. MAP estimates are release-specific modelled data. The application selects an explicit release, checks metric availability from release metadata, resolves admin-1 units against that release's boundary version, decodes JSON-stat dimensions by their published category indexes, and resolves raster layer names against GeoServer WMS capabilities before display. The raster explorer retrieves a simplified country ADM0 GeoJSON boundary from geoBoundaries, validates the download host and polygon coordinates, and zooms the interactive WMS view to that country. Zero values are flagged because MAP documents that zero can also mean no estimate is available. Lower/upper bounds are fetched only where the source provides genuine uncertainty bounds; effective treatment and IRS do not have such bounds. Source availability, API uptime, country coverage and indicator coverage vary. The application reports unavailable indicators rather than silently filling or fabricating values. Some World Bank indicator codes may return no observations for a given period or country; verify the live connector status before interpretation.

## Supplementary CSV format

Required columns: `iso3,country,year,indicator_code,value,source`. Optional columns: `source_url,last_updated`. Uploads are held in the current Streamlit session and are not written to a server-side database. Missing values are retained as missing; they are never converted to zero.

## Interpretation and safety

- Modelled estimates, reported counts and contextual health indicators are not interchangeable. MAP national and admin-1 outputs are modelled estimates, not individually reported surveillance records.
- Latest available years can differ between countries and indicators; comparisons should show the reference year.
- A missing observation is not evidence of zero burden or zero intervention coverage.
- Country-level choropleths do not identify local outbreaks or subnational transmission risk. MAP admin-1 estimates provide subnational modelled summaries, not real-time outbreak detection. Country boundary overlays are administrative reference geometry, not epidemiological boundaries; the MAP raster remains a modelled surface.
- Linear extrapolation is exploratory and is not an outbreak prediction, early-warning alert, clinical decision aid or substitute for national surveillance.
- The platform is for research, policy analysis and programme intelligence. It does not diagnose malaria or recommend individual treatment.

## Testing

```bash
pytest -q
python -m compileall -q main.py streamlit_app.py malaria_intel tests
```

GitHub Actions runs compile checks and unit tests on Python 3.10–3.12 for pushes and pull requests.

## Deployment

Deploy the repository to Streamlit Community Cloud using `streamlit_app.py` as the app entry point. No secrets are required for the public data connectors. Check the application logs and Data Quality & Sources workspace after deployment. A successful GitHub Actions run does not by itself verify Streamlit Cloud availability or live upstream API health.
