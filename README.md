# Africa Malaria Intelligence

A Streamlit-based, open-data research and programme-intelligence workspace for malaria burden, trends and contextual health indicators across African countries.

## Current implementation

- Executive overview with latest available observations and country coverage.
- Country profiles and historical indicator trends.
- Country comparisons and year-on-year change calculations.
- Country-level choropleth maps (not subnational risk maps).
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

The application requests country metadata and indicator observations from the World Bank API. The indicator catalogue is maintained in `malaria_intel/config.py`; each indicator has a code, definition, unit, group and interpretation type. The WHO Global Health Observatory OData catalogue can be queried from the Data Quality & Sources workspace to discover malaria-related indicators.

The following authoritative resources are linked for further data integration and verification:

- [WHO Global Health Observatory](https://www.who.int/data/gho)
- [WHO World Malaria Report](https://www.who.int/teams/global-malaria-programme/reports/world-malaria-report)
- [Malaria Atlas Project](https://malariaatlas.org/)
- [World Bank Open Data](https://data.worldbank.org/)
- [UNICEF Data](https://data.unicef.org/)
- [Our World in Data — Malaria](https://ourworldindata.org/malaria)

No API key is required for the core World Bank and WHO catalogue requests. Source availability, API uptime, country coverage and indicator coverage vary. The application reports unavailable indicators rather than silently filling or fabricating values. Some World Bank indicator codes may return no observations for a given period or country; verify the live connector status before interpretation.

## Supplementary CSV format

Required columns: `iso3,country,year,indicator_code,value,source`. Optional columns: `source_url,last_updated`. Uploads are held in the current Streamlit session and are not written to a server-side database. Missing values are retained as missing; they are never converted to zero.

## Interpretation and safety

- Modelled estimates, reported counts and contextual health indicators are not interchangeable.
- Latest available years can differ between countries and indicators; comparisons should show the reference year.
- A missing observation is not evidence of zero burden or zero intervention coverage.
- Country-level choropleths do not identify local outbreaks or subnational transmission risk.
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
