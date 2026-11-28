"""Comparable-year country benchmarking for malaria indicators."""
from __future__ import annotations

import pandas as pd

from .analytics import REQUIRED_COLUMNS


def country_benchmark(
    observations: pd.DataFrame,
    indicator: str,
    reference_year: int,
    countries: list[str] | None = None,
) -> pd.DataFrame:
    """Return an exact-year country comparison; never substitutes each country's latest year.

    Multiple source rows for the same country/indicator/year are collapsed to their
    median to prevent countries with more source records from receiving extra weight.
    The output rank is a numerical ordering only, not a judgement of better/worse.
    """
    missing = REQUIRED_COLUMNS - set(observations.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    if not str(indicator).strip():
        raise ValueError("Select an indicator.")
    data = observations.copy()
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data["value"] = pd.to_numeric(data["value"], errors="coerce")
    data["iso3"] = data["iso3"].astype(str).str.upper().str.strip()
    data = data[
        data["indicator_code"].astype(str).eq(str(indicator))
        & data["year"].eq(int(reference_year))
        & data["iso3"].str.fullmatch(r"[A-Z]{3}", na=False)
    ].dropna(subset=["value", "country"])
    if countries:
        selected = {str(code).upper() for code in countries}
        data = data[data["iso3"].isin(selected)]
    if data.empty:
        raise ValueError(f"No comparable country observations are available for {indicator} in {int(reference_year)}.")
    result = (
        # Country labels are categorical in the compacted production frame.
        # observed=True prevents pandas from materialising unused category combinations
        # (e.g. one selected country expanded across every country label in the dataset).
        data.groupby(["iso3", "country"], as_index=False, observed=True)
        .agg(
            value=("value", "median"),
            source_count=("source", "nunique"),
            observation_count=("value", "size"),
            sources=("source", lambda values: ", ".join(sorted(set(values.dropna().astype(str))))),
        )
        .sort_values(["value", "iso3"], ascending=[False, True])
        .reset_index(drop=True)
    )
    result["numerical_order"] = range(1, len(result) + 1)
    result["percentile"] = result["value"].rank(method="average", pct=True) * 100
    result["reference_year"] = int(reference_year)
    result["indicator_code"] = str(indicator)
    result["comparison_method"] = "Exact reference year; median across available source rows within country"
    return result


def benchmark_coverage(
    observations: pd.DataFrame,
    indicator: str,
    years: list[int] | None = None,
) -> pd.DataFrame:
    """Show country coverage by year to help choose a defensible comparison year."""
    missing = REQUIRED_COLUMNS - set(observations.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    data = observations.copy()
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data["value"] = pd.to_numeric(data["value"], errors="coerce")
    data = data[
        data["indicator_code"].astype(str).eq(str(indicator))
        & data["value"].notna()
        & data["iso3"].astype(str).str.fullmatch(r"[A-Za-z]{3}", na=False)
    ]
    if years is not None:
        data = data[data["year"].isin([int(year) for year in years])]
    if data.empty:
        return pd.DataFrame(columns=["year", "countries", "observations", "sources"])
    # The core observations frame uses categoricals to reduce memory. Group only
    # observed year groups and build the result from the grouped index explicitly;
    # this avoids categorical cartesian expansion in pandas groupby operations.
    grouped = data.groupby("year", observed=True, sort=True).agg(
        countries=("iso3", "nunique"),
        observations=("value", "size"),
        sources=("source", "nunique"),
    )
    return grouped.reset_index().sort_values("year").reset_index(drop=True)
