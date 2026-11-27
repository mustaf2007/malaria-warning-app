"""Transparent, testable analytics for malaria indicators."""
from __future__ import annotations
import pandas as pd

REQUIRED_COLUMNS = {"iso3", "country", "year", "indicator_code", "value", "source"}


def validate_observations(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    missing_columns = REQUIRED_COLUMNS - set(frame.columns)
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing_columns))}")
    clean = frame.copy()
    clean["year"] = pd.to_numeric(clean["year"], errors="coerce")
    clean["value"] = pd.to_numeric(clean["value"], errors="coerce")
    clean = clean.dropna(subset=["iso3", "year", "indicator_code"])
    clean["year"] = clean["year"].astype(int)
    clean["iso3"] = clean["iso3"].astype(str).str.upper().str.strip()
    clean = clean.drop_duplicates(subset=["iso3", "year", "indicator_code", "source"], keep="last")
    clean = clean.sort_values(["indicator_code", "country", "year"]).reset_index(drop=True)
    quality = {
        "rows": int(len(clean)),
        "missing_values": int(clean["value"].isna().sum()),
        "duplicate_keys_removed": int(len(frame) - len(clean)),
        "countries": int(clean["iso3"].nunique()),
        "indicators": int(clean["indicator_code"].nunique()),
        "years": int(clean["year"].nunique()),
    }
    return clean, quality


def filter_observations(frame: pd.DataFrame, indicator: str | None = None, countries: list[str] | None = None, start_year: int | None = None, end_year: int | None = None) -> pd.DataFrame:
    result = frame.copy()
    if indicator:
        result = result[result["indicator_code"] == indicator]
    if countries:
        result = result[result["iso3"].isin(countries)]
    if start_year is not None:
        result = result[result["year"] >= int(start_year)]
    if end_year is not None:
        result = result[result["year"] <= int(end_year)]
    return result


def latest_country_values(frame: pd.DataFrame, indicator: str) -> pd.DataFrame:
    data = frame[(frame["indicator_code"] == indicator) & frame["value"].notna()].copy()
    if data.empty:
        return data
    latest = data.groupby("iso3")["year"].max().rename("latest_year")
    data = data.join(latest, on="iso3")
    return data[data["year"] == data["latest_year"]].drop(columns="latest_year").sort_values("value", ascending=False)


def year_over_year(frame: pd.DataFrame, indicator: str, country: str) -> pd.DataFrame:
    data = frame[(frame["indicator_code"] == indicator) & (frame["iso3"] == country) & frame["value"].notna()].sort_values("year").copy()
    data["absolute_change"] = data["value"].diff()
    data["percent_change"] = data["value"].pct_change() * 100
    return data


def forecast_linear(frame: pd.DataFrame, indicator: str, country: str, horizon: int = 3) -> pd.DataFrame:
    """Exploratory linear extrapolation; not an outbreak prediction or clinical alert."""
    data = frame[(frame["indicator_code"] == indicator) & (frame["iso3"] == country) & frame["value"].notna()].sort_values("year")
    if len(data) < 4:
        raise ValueError("At least four non-missing annual observations are required for an exploratory trend.")
    if horizon < 1 or horizon > 5:
        raise ValueError("Forecast horizon must be between 1 and 5 years.")
    import numpy as np
    x = data["year"].to_numpy(dtype=float)
    y = data["value"].to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    residual = y - fitted
    rmse = float(np.sqrt(np.mean(residual ** 2)))
    future_years = list(range(int(x.max()) + 1, int(x.max()) + horizon + 1))
    predictions = [max(0.0, float(slope * year + intercept)) for year in future_years]
    return pd.DataFrame({"year": future_years, "forecast": predictions, "rmse_in_sample": rmse, "method": "ordinary least-squares linear trend"})


def answer_data_question(frame: pd.DataFrame, question: str, country_names: dict[str, str] | None = None) -> str:
    """Model-free assistant: answers supported questions by calculating from loaded observations."""
    q = (question or "").strip().lower()
    if not q:
        return "Enter a question about the currently loaded malaria dataset."
    if frame.empty:
        return "No observations are currently loaded. Refresh the data or upload a validated dataset first."
    indicators = sorted(frame["indicator_code"].dropna().unique())
    matched = next((code for code in indicators if code.lower() in q), None)
    if matched is None:
        for code, words in {
            "SH.MLR.INCD.P3": ("incidence", "rate"), "SH.MLR.CASES": ("cases",),
            "SH.MLR.DEATHS": ("deaths", "mortality"), "SH.MLR.NETS.ZS": ("nets", "bednet", "bed net"),
            "SH.MLR.PREV.ZS": ("prevalence",),
        }.items():
            if code in indicators and any(word in q for word in words):
                matched = code
                break
    if matched is None:
        return "I can calculate summaries, latest country values, trends and comparisons from loaded indicators. Specify an indicator (for example incidence, cases or deaths) and optionally a country or year."
    data = frame[(frame["indicator_code"] == matched) & frame["value"].notna()].copy()
    if data.empty:
        return f"No non-missing observations are available for {matched}."
    country = None
    for iso3, name in (country_names or {}).items():
        if iso3.lower() in q or name.lower() in q:
            country = iso3
            break
    if country:
        subset = data[data["iso3"] == country].sort_values("year")
        if subset.empty:
            return f"No observations for {country} and {matched} are loaded."
        latest = subset.iloc[-1]
        first = subset.iloc[0]
        return f"{latest['country']}: latest available {matched} value is {latest['value']:,.3g} in {int(latest['year'])}. The earliest loaded observation is {first['value']:,.3g} in {int(first['year'])}. Source: {latest['source']}."
    if any(term in q for term in ("highest", "top", "most")):
        latest = latest_country_values(data, matched).head(5)
        return "Highest latest available country values for " + matched + ": " + "; ".join(f"{r.country}: {r.value:,.3g} ({int(r.year)})" for r in latest.itertuples()) + ". Values are not necessarily from the same year."
    if any(term in q for term in ("average", "mean")):
        return f"The mean of {len(data)} non-missing observations for {matched} is {data['value'].mean():,.3g}. This pools country-years and should not be interpreted as a population-weighted continental rate."
    return f"For {matched}, {len(data)} non-missing observations are loaded across {data['iso3'].nunique()} countries and {data['year'].nunique()} years. The latest reference year in this indicator is {int(data['year'].max())}. Ask for a country, highest values, or average to narrow the analysis."
