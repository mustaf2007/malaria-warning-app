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


def test_benchmark_coverage_handles_compacted_categorical_dimensions():
    # Mirrors the production shape: 54 countries across 60 years (3,240 rows).
    import string
    from itertools import islice, product

    iso3_codes = ["".join(chars) for chars in islice(product(string.ascii_uppercase, repeat=3), 54)]
    rows = [
        {
            "iso3": iso3,
            "country": f"Country {index + 1}",
            "year": year,
            "indicator_code": "INC",
            "value": float(index + 1),
            "source": "Source A" if index % 2 == 0 else "Source B",
        }
        for year in range(1960, 2020)
        for index, iso3 in enumerate(iso3_codes)
    ]
    frame = pd.DataFrame(rows)
    frame["year"] = frame["year"].astype("int16")
    frame["iso3"] = frame["iso3"].astype("category")
    frame["source"] = frame["source"].astype("category")

    coverage = benchmark_coverage(frame, "INC")

    assert len(frame) == 54 * 60
    assert len(coverage) == 60
    assert coverage["countries"].eq(54).all()
    assert coverage["observations"].eq(54).all()
    assert coverage["sources"].eq(2).all()


def test_country_benchmark_handles_compacted_categorical_country_filter():
    # Production observations retain the full country category catalogue even
    # after filtering to one country and one reference year.
    import string
    from itertools import islice, product

    iso3_codes = ["".join(chars) for chars in islice(product(string.ascii_uppercase, repeat=3), 54)]
    rows = [
        {
            "iso3": iso3,
            "country": f"Country {index + 1}",
            "year": year,
            "indicator_code": "INC",
            "value": float(index + 1),
            "source": "Source A",
        }
        for year in range(1960, 2020)
        for index, iso3 in enumerate(iso3_codes)
    ]
    frame = pd.DataFrame(rows)
    frame["year"] = frame["year"].astype("int16")
    for column in ["iso3", "country", "indicator_code", "source"]:
        frame[column] = frame[column].astype("category")

    result = country_benchmark(frame, "INC", 2010, [iso3_codes[0]])

    assert len(result) == 1
    assert result.iloc[0]["iso3"] == iso3_codes[0]
    assert result.iloc[0]["country"] == "Country 1"
    assert result.iloc[0]["reference_year"] == 2010
    assert result.iloc[0]["value"] == 1.0
