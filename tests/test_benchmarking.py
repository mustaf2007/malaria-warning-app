import pandas as pd
import pytest

from malaria_intel.benchmarking import benchmark_coverage, country_benchmark


@pytest.fixture
def observations():
    return pd.DataFrame([
        {"iso3":"SOM","country":"Somalia","year":2020,"indicator_code":"INC","value":100,"source":"Source A"},
        {"iso3":"SOM","country":"Somalia","year":2020,"indicator_code":"INC","value":80,"source":"Source B"},
        {"iso3":"KEN","country":"Kenya","year":2020,"indicator_code":"INC","value":40,"source":"Source A"},
        {"iso3":"ETH","country":"Ethiopia","year":2021,"indicator_code":"INC","value":20,"source":"Source A"},
        {"iso3":"SOM","country":"Somalia","year":2021,"indicator_code":"INC","value":70,"source":"Source A"},
        {"iso3":"KEN","country":"Kenya","year":2021,"indicator_code":"INC","value":30,"source":"Source A"},
        {"iso3":"SOM","country":"Somalia","year":2020,"indicator_code":"CASES","value":2000,"source":"Source A"},
    ])


def test_benchmark_uses_exact_same_reference_year(observations):
    result = country_benchmark(observations, "INC", 2020)
    assert set(result.iso3) == {"SOM", "KEN"}
    assert set(result.reference_year) == {2020}
    # Somalia's multiple source rows are collapsed to the median.
    som = result[result.iso3 == "SOM"].iloc[0]
    assert som.value == 90
    assert som.observation_count == 2
    assert som.source_count == 2


def test_country_filter_is_applied(observations):
    result = country_benchmark(observations, "INC", 2020, ["ken"])
    assert result.iso3.tolist() == ["KEN"]


def test_does_not_substitute_each_country_latest_year(observations):
    result = country_benchmark(observations, "INC", 2020)
    assert "ETH" not in result.iso3.tolist()
    assert set(result.reference_year) == {2020}


def test_rejects_year_with_no_comparable_data(observations):
    with pytest.raises(ValueError, match="No comparable"):
        country_benchmark(observations, "INC", 2010)


def test_rejects_missing_indicator(observations):
    with pytest.raises(ValueError, match="Select an indicator"):
        country_benchmark(observations, "", 2020)


def test_benchmark_coverage_counts_available_countries(observations):
    coverage = benchmark_coverage(observations, "INC")
    assert coverage.set_index("year").loc[2020, "countries"] == 2
    assert coverage.set_index("year").loc[2021, "countries"] == 3


def test_empty_coverage_returns_expected_schema(observations):
    coverage = benchmark_coverage(observations, "UNKNOWN")
    assert coverage.empty
    assert list(coverage.columns) == ["year", "countries", "observations", "sources"]
