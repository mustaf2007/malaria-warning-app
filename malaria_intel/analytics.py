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
    clean["iso3"] = clean["iso3"].astype("string").str.upper().str.strip()
    clean["indicator_code"] = clean["indicator_code"].astype("string").str.strip()
    clean["source"] = clean["source"].astype("string").str.strip()
    valid_year = clean["year"].notna() & clean["year"].mod(1).eq(0)
    placeholder_iso3 = {"NAN", "NULL", "NONE", "UNK", "UNKNOWN", "XXX"}
    valid_iso3 = clean["iso3"].str.fullmatch(r"[A-Z]{3}", na=False) & ~clean["iso3"].isin(placeholder_iso3)
    valid_indicator = clean["indicator_code"].notna() & clean["indicator_code"].ne("")
    valid_source = clean["source"].notna() & clean["source"].ne("")
    valid_rows = clean[valid_year & valid_iso3 & valid_indicator & valid_source].copy()
    invalid_rows_removed = int(len(clean) - len(valid_rows))
    valid_rows["year"] = valid_rows["year"].astype(int)
    key_columns = ["iso3", "year", "indicator_code", "source"]
    # A key with multiple distinct reported values is ambiguous: exclude the
    # entire key rather than selecting an arbitrary row based on input order.
    non_missing_values = valid_rows.groupby(key_columns, dropna=False)["value"].nunique(dropna=True)
    conflicting_keys = non_missing_values[non_missing_values > 1].index
    if len(conflicting_keys):
        conflict_index = pd.MultiIndex.from_frame(valid_rows[key_columns])
        conflict_mask = conflict_index.isin(conflicting_keys)
        conflicting_rows_excluded = int(conflict_mask.sum())
        unambiguous = valid_rows.loc[~conflict_mask].copy()
    else:
        conflicting_rows_excluded = 0
        unambiguous = valid_rows
    conflicting_keys_excluded = int(len(conflicting_keys))
    # If duplicate rows contain one observed value and one missing value,
    # retain the observed record; otherwise exact duplicate keys are equivalent.
    unambiguous = unambiguous.sort_values("value", na_position="first")
    deduplicated = unambiguous.drop_duplicates(subset=key_columns, keep="last")
    duplicate_keys_removed = int(len(unambiguous) - len(deduplicated))
    clean = deduplicated.sort_values(["indicator_code", "country", "year"]).reset_index(drop=True)
    quality = {
        "rows": int(len(clean)),
        "missing_values": int(clean["value"].isna().sum()),
        "invalid_rows_removed": invalid_rows_removed,
        "duplicate_keys_removed": duplicate_keys_removed,
        "conflicting_keys_excluded": conflicting_keys_excluded,
        "conflicting_rows_excluded": conflicting_rows_excluded,
        "countries": int(clean["iso3"].nunique()),
        "indicators": int(clean["indicator_code"].nunique()),
        "years": int(clean["year"].nunique()),
    }
    return clean, quality


def compact_observations(frame: pd.DataFrame) -> pd.DataFrame:
    """Reduce dataframe memory without changing epidemiological values or row grain.

    Repeated text dimensions are stored as categoricals and whole-number years use
    int16 where safe. Indicator values remain float64 to avoid precision loss.
    The supplied frame is compacted in place to avoid creating another full copy.
    """
    if frame.empty:
        return frame

    if "year" in frame.columns:
        years = pd.to_numeric(frame["year"], errors="coerce")
        if years.notna().all() and years.mod(1).eq(0).all():
            minimum, maximum = int(years.min()), int(years.max())
            if -32768 <= minimum and maximum <= 32767:
                frame["year"] = years.astype("int16")

    text_columns = (
        "iso3", "country", "indicator_code", "source", "source_url",
        "last_updated",
    )
    row_count = len(frame)
    for column in text_columns:
        if column not in frame.columns:
            continue
        values = frame[column]
        if not (pd.api.types.is_object_dtype(values.dtype)
                or pd.api.types.is_string_dtype(values.dtype)):
            continue
        unique_count = int(values.nunique(dropna=False))
        if unique_count < row_count * 0.5 and unique_count <= 10000:
            frame[column] = values.astype("category")
    return frame


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
    data["year_gap"] = data["year"].diff()
    consecutive = data["year_gap"].eq(1)
    data["absolute_change"] = data["value"].diff().where(consecutive)
    data["percent_change"] = (data["value"].pct_change() * 100).where(consecutive)
    data["change_status"] = consecutive.map({True: "Consecutive calendar year", False: "Gap or first observation"})
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



def build_data_quality_tables(
    frame: pd.DataFrame,
    current_year: int | None = None,
) -> dict[str, pd.DataFrame]:
    """Build transparent quality, indicator, source and coverage summaries.

    Missingness is measured only among rows supplied by a source. The coverage
    matrix counts non-missing country-indicator combinations; it does not infer
    that an absent row is a confirmed zero or a source-reported missing value.
    """
    required = {"iso3", "country", "year", "indicator_code", "value", "source"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    data = frame.copy()
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data["value"] = pd.to_numeric(data["value"], errors="coerce")
    data["iso3"] = data["iso3"].astype(str).str.upper().str.strip()
    data["indicator_code"] = data["indicator_code"].astype(str)
    # Categorical columns require new labels to be registered before fillna.
    source = data["source"]
    if isinstance(source.dtype, pd.CategoricalDtype):
        if "Unknown source" not in source.cat.categories:
            source = source.cat.add_categories(["Unknown source"])
        data["source"] = source.fillna("Unknown source")
    else:
        data["source"] = source.astype("string").fillna("Unknown source").astype(str)
    data = data.dropna(subset=["year", "indicator_code", "iso3"])
    data["year"] = data["year"].astype(int)
    reference_year = int(current_year if current_year is not None else pd.Timestamp.now(tz="UTC").year)

    def summarise(group: pd.DataFrame, key: str) -> pd.DataFrame:
        rows = []
        for value, part in group.groupby(key, dropna=False):
            total = len(part)
            non_missing = int(part["value"].notna().sum())
            observed_years = part.loc[part["value"].notna(), "year"]
            rows.append({
                key: value,
                "rows_received": int(total),
                "non_missing_values": non_missing,
                "missing_values": int(total - non_missing),
                "missing_pct": round((total - non_missing) / total * 100, 2) if total else 0.0,
                "zero_values": int((part["value"] == 0).sum()),
                "countries": int(part.loc[part["value"].notna(), "iso3"].nunique()),
                "first_observation_year": int(observed_years.min()) if not observed_years.empty else pd.NA,
                "latest_observation_year": int(observed_years.max()) if not observed_years.empty else pd.NA,
                "years_behind_current": reference_year - int(observed_years.max()) if not observed_years.empty else pd.NA,
            })
        columns = [
            key, "rows_received", "non_missing_values", "missing_values",
            "missing_pct", "zero_values", "countries", "first_observation_year",
            "latest_observation_year", "years_behind_current",
        ]
        return pd.DataFrame(rows, columns=columns)

    indicator_summary = summarise(data, "indicator_code")
    source_summary = summarise(data, "source")
    valid = data[data["value"].notna()]
    if valid.empty:
        coverage = pd.DataFrame()
    else:
        coverage = valid.pivot_table(
            index="iso3", columns="indicator_code", values="value",
            aggfunc="count", fill_value=0,
        ).reset_index()
        coverage.columns.name = None
        names = data.drop_duplicates("iso3").set_index("iso3")["country"].to_dict()
        coverage.insert(1, "country", coverage["iso3"].map(names))
    summary = pd.DataFrame([{
        "rows_received": int(len(data)),
        "non_missing_values": int(data["value"].notna().sum()),
        "missing_values": int(data["value"].isna().sum()),
        "missing_pct": round(float(data["value"].isna().mean() * 100), 2) if len(data) else 0.0,
        "zero_values": int((data["value"] == 0).sum()),
        "countries": int(data["iso3"].nunique()),
        "indicators": int(data["indicator_code"].nunique()),
        "sources": int(data["source"].nunique()),
        "latest_observation_year": int(valid["year"].max()) if not valid.empty else pd.NA,
        "reference_calendar_year": reference_year,
    }])
    return {
        "overall": summary,
        "indicators": indicator_summary.sort_values("indicator_code").reset_index(drop=True),
        "sources": source_summary.sort_values("source").reset_index(drop=True),
        "coverage": coverage.sort_values("iso3").reset_index(drop=True) if not coverage.empty else coverage,
    }



def summarize_loaded_dataset(
    frame: pd.DataFrame,
    country_names: dict[str, str] | None = None,
) -> str:
    """Summarise the complete loaded dataset without pooling unlike indicators."""
    required = {"iso3", "country", "year", "indicator_code", "value", "source"}
    missing_columns = required - set(frame.columns)
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing_columns))}")
    if frame.empty:
        return "No observations are currently loaded. Refresh the data or upload a validated dataset first."

    data = frame.copy()
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data["value"] = pd.to_numeric(data["value"], errors="coerce")
    data = data.dropna(subset=["iso3", "year", "indicator_code"])
    if data.empty:
        return "The loaded dataset contains no usable country, year and indicator records."

    observed = data[data["value"].notna()]
    total_rows = len(data)
    missing_values = int(data["value"].isna().sum())
    country_count = int(data["iso3"].nunique())
    indicator_count = int(data["indicator_code"].nunique())
    source_count = int(data["source"].nunique())
    year_min = int(data["year"].min())
    year_max = int(data["year"].max())
    lines = [
        "**Dataset-wide summary**",
        f"- Records: {total_rows:,} ({len(observed):,} with numeric values; {missing_values:,} missing values, {missing_values / total_rows * 100:.1f}%).",
        f"- Coverage: {country_count:,} countries, {indicator_count:,} indicators and {source_count:,} sources.",
        f"- Reference years represented: {year_min}–{year_max}.",
    ]
    if observed.empty:
        lines.append("- No numeric observations are available, so indicator statistics cannot be calculated.")
        return "\n".join(lines)

    lines.append("")
    lines.append("**Indicator-by-indicator results**")
    for code, part in observed.groupby("indicator_code", sort=True):
        values = part["value"]
        countries = int(part["iso3"].nunique())
        first_year = int(part["year"].min())
        last_year = int(part["year"].max())
        lines.append(
            f"- **{code}**: {len(part):,} numeric observations across {countries:,} countries "
            f"({first_year}–{last_year}); minimum {values.min():,.4g}, "
            f"median {values.median():,.4g}, maximum {values.max():,.4g}."
        )
    lines.append("")
    lines.append("**Data interpretation**")
    lines.append(
        "- Statistics are calculated separately for each indicator. Values from different indicators "
        "are not pooled because their units and definitions may differ."
    )
    lines.append(
        "- These are descriptive summaries of the loaded rows, not population-weighted continental "
        "rates. Multiple source records may represent the same country-year."
    )
    lines.append("- Missing values are not treated as zero; source definitions and reference years should be checked before policy use.")
    return "\n".join(lines)

def answer_data_question(frame: pd.DataFrame, question: str, country_names: dict[str, str] | None = None) -> str:
    """Model-free assistant: answers supported questions by calculating from loaded observations."""
    q = (question or "").strip().lower()
    if not q:
        return "Enter a question about the currently loaded malaria dataset."
    if frame.empty:
        return "No observations are currently loaded. Refresh the data or upload a validated dataset first."
    broad_summary_terms = ("summarize", "summarise", "summary", "overview", "all data", "whole dataset", "entire dataset")
    if any(term in q for term in broad_summary_terms):
        return summarize_loaded_dataset(frame, country_names)
    indicators = sorted(frame["indicator_code"].dropna().unique())
    matched = next((code for code in indicators if code.lower() in q), None)
    if matched is None:
        for code, words in {
            "SH.MLR.INCD.P3": ("incidence", "rate"), "SH.STA.MALR": ("cases", "reported cases"),
             
            
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



def prepare_who_observations(
    rows: list[dict],
    country_names: dict[str, str],
) -> list[dict]:
    """Normalize selected WHO rows to known African ISO3 codes and display names."""
    prepared = []
    allowed = {str(code).strip().upper(): str(name) for code, name in country_names.items()}
    for item in rows or []:
        iso3 = str(item.get("iso3") or "").strip().upper()
        if iso3 not in allowed:
            continue
        try:
            year_value = float(item.get("year"))
            if not year_value.is_integer():
                continue
            year = int(year_value)
        except (TypeError, ValueError):
            continue
        raw_value = item.get("value")
        try:
            value = float(raw_value) if raw_value is not None else None
        except (TypeError, ValueError):
            value = None
        prepared.append({
            **item,
            "iso3": iso3,
            "country": allowed[iso3],
            "year": year,
            "value": value,
        })
    return prepared
