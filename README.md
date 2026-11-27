# 🦟 Africa Malaria Intelligence

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://gdp-dashboard-template.streamlit.app/)

A Streamlit-based, open-data research and programme-intelligence workspace for malaria burden, trends and contextual health indicators across African countries.

## Current implementation

- Executive overview with latest available observations and country coverage.
- Country profiles and historical indicator trends.
- Country comparisons and year-on-year change calculations.
- Country-level choropleth maps, MAP national/subnational time-series analysis, an admin-1 malaria choropleth using geoBoundaries administrative polygons, and a country-focused high-resolution raster explorer with ADM0 overlays.
- Prevention, population vulnerability and health-system context indicators where data is available.
- Exploratory linear trend extrapolation with an explicit non-operational warning.
- Model-free analyst that computes answers from loaded observations rather than inventing unsupported facts.
- Country-specific and Africa-wide PDF intelligence reports with indicator summaries, country comparisons, annual regional medians, trend charts, source coverage and interpretation safeguards; CSV and Excel exports, supplementary CSV upload, source status and data-quality reporting.
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
- [geoBoundaries](https://www.geoboundaries.org/) — open ADM0 and ADM1 administrative boundary geometry used for country-focused raster views and subnational choropleths. The app uses each boundary record's source and licence metadata; check country-specific terms and attribution.
- [World Bank Open Data](https://data.worldbank.org/)
- [UNICEF Data](https://data.unicef.org/)
- [Our World in Data — Malaria](https://ourworldindata.org/malaria)

No API key is required for the core World Bank, WHO GHO, Our World in Data and MAP public requests. MAP estimates are release-specific modelled data. The application selects an explicit release, checks metric availability from release metadata, resolves admin-1 units against that release's boundary version, decodes JSON-stat dimensions by their published category indexes, and resolves raster layer names against GeoServer WMS capabilities before display. The raster explorer retrieves a simplified country ADM0 GeoJSON boundary from geoBoundaries, validates the download host and polygon coordinates, and zooms the interactive WMS view to that country. For MAP admin-1 estimates, the subnational workspace can retrieve geoBoundaries ADM1 polygons and join them to MAP units only through unique exact administrative-name matches after conservative text normalisation. Ambiguous and unmatched names are excluded from the choropleth rather than guessed; the interface reports match coverage and keeps the original MAP time series and table available. Zero values are flagged because MAP documents that zero can also mean no estimate is available. Lower/upper bounds are fetched only where the source provides genuine uncertainty bounds; effective treatment and IRS do not have such bounds. Source availability, API uptime, country coverage and indicator coverage vary. The application reports unavailable indicators rather than silently filling or fabricating values. Some World Bank indicator codes may return no observations for a given period or country; verify the live connector status before interpretation.

## Country intelligence PDF reports

The Reports & Downloads workspace can generate a country-specific PDF from the currently loaded observations and a selected reference period. Reports include latest and earliest available values by indicator, compact historical trend charts, source-level observation coverage and explicit interpretation safeguards. The report does not impute missing values or fetch new data independently; it reflects the active in-memory dataset, including any validated session upload or selected WHO observations. Indicator identifiers are retained so definitions can be verified in the source catalogue. Install dependencies from `requirements.txt` (including ReportLab) to enable PDF generation.

## Africa-wide annual intelligence reports

The Reports & Downloads workspace can generate a continental PDF using up to eight selected indicators and a chosen reference period. It includes indicator coverage, annual unweighted medians across available country observations, contributing-country counts, and each country's latest available value with its own reference year and source. The median is descriptive and is not a population-weighted continental rate or total. Country values are not forced onto a common year, and the country table is explicitly not a performance ranking. Reports use only observations already loaded in the application; they do not refresh sources, impute missing values or harmonise distinct indicator definitions. Modelled malaria estimates, reported cases and contextual indicators remain separate evidence types.

## Supplementary CSV format

Required columns: `iso3,country,year,indicator_code,value,source`. Optional columns: `source_url,last_updated`. Uploads are held in the current Streamlit session and are not written to a server-side database. Missing values are retained as missing; they are never converted to zero.

## Interpretation and safety

- Modelled estimates, reported counts and contextual health indicators are not interchangeable. MAP national and admin-1 outputs are modelled estimates, not individually reported surveillance records.
- Latest available years can differ between countries and indicators; comparisons should show the reference year.
- A missing observation is not evidence of zero burden or zero intervention coverage.
- MAP admin-1 choropleths are modelled estimates joined to third-party administrative reference boundaries. Only unique name matches are mapped; unmatched units are disclosed, and boundary vintages may differ from the MAP administrative release. These maps do not identify local outbreaks or provide real-time outbreak detection. Country and admin-1 boundary overlays are administrative reference geometry, not epidemiological boundaries; the MAP raster remains a modelled surface.
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
