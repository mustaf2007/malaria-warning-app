import pandas as pd
import pytest

from malaria_intel.reports import build_country_report_pdf


@pytest.fixture
def report_data():
    return pd.DataFrame([
        {"iso3": "SOM", "country": "Somalia", "year": 2020, "indicator_code": "SH.MLR.INCD.P3", "value": 50.0, "source": "World Bank", "source_url": "https://data.worldbank.org/"},
        {"iso3": "SOM", "country": "Somalia", "year": 2021, "indicator_code": "SH.MLR.INCD.P3", "value": 45.0, "source": "World Bank", "source_url": "https://data.worldbank.org/"},
        {"iso3": "SOM", "country": "Somalia", "year": 2021, "indicator_code": "SH.STA.MALR", "value": None, "source": "WHO GHO", "source_url": "https://www.who.int/data/gho"},
        {"iso3": "KEN", "country": "Kenya", "year": 2021, "indicator_code": "SH.MLR.INCD.P3", "value": 20.0, "source": "World Bank", "source_url": "https://data.worldbank.org/"},
    ])


def test_builds_valid_pdf_with_country_only_data(report_data):
    result = build_country_report_pdf(report_data, "SOM", "Somalia", 2020, 2021)
    assert result.startswith(b"%PDF")
    assert len(result) > 1000


def test_rejects_missing_country_period(report_data):
    with pytest.raises(ValueError, match="No observations"):
        build_country_report_pdf(report_data, "ETH", "Ethiopia", 2020, 2021)


def test_rejects_invalid_iso3(report_data):
    with pytest.raises(ValueError, match="ISO3"):
        build_country_report_pdf(report_data, "Somalia", "Somalia", 2020, 2021)


def test_rejects_reversed_year_range(report_data):
    with pytest.raises(ValueError, match="Start year"):
        build_country_report_pdf(report_data, "SOM", "Somalia", 2022, 2020)


def test_handles_all_missing_indicator_values(report_data):
    data = report_data[report_data["indicator_code"] == "SH.STA.MALR"]
    result = build_country_report_pdf(data, "SOM", "Somalia", 2021, 2021)
    assert result.startswith(b"%PDF")



def test_country_year_summary_gives_each_country_one_value_per_year():
    from malaria_intel.reports import _country_year_summary

    frame = pd.DataFrame([
        {"iso3":"SOM","country":"Somalia","year":2022,"value":10.0,"source":"Source A"},
        {"iso3":"SOM","country":"Somalia","year":2022,"value":20.0,"source":"Source B"},
        {"iso3":"SOM","country":"Somalia","year":2022,"value":30.0,"source":"Source C"},
        {"iso3":"KEN","country":"Kenya","year":2022,"value":40.0,"source":"Source A"},
    ])
    result = _country_year_summary(frame)

    assert len(result) == 2
    som = result[result.iso3 == "SOM"].iloc[0]
    assert som.value == 20.0
    assert som.source_count == 3
    assert som.sources == "Source A, Source B, Source C"


def test_country_year_summary_ignores_missing_values_without_creating_zero():
    from malaria_intel.reports import _country_year_summary

    frame = pd.DataFrame([
        {"iso3":"SOM","country":"Somalia","year":2022,"value":None,"source":"Source A"},
        {"iso3":"SOM","country":"Somalia","year":2022,"value":12.0,"source":"Source B"},
    ])
    result = _country_year_summary(frame)

    assert len(result) == 1
    assert result.iloc[0].value == 12.0
    assert result.iloc[0].source_count == 1


def test_country_report_handles_multiple_sources_for_same_year(report_data):
    extra = pd.DataFrame([{
        "iso3":"SOM","country":"Somalia","year":2021,
        "indicator_code":"SH.MLR.INCD.P3","value":35.0,
        "source":"Second source","source_url":"https://example.org/"
    }])
    result = build_country_report_pdf(
        pd.concat([report_data, extra], ignore_index=True), "SOM", "Somalia", 2020, 2021
    )
    assert result.startswith(b"%PDF")
    assert len(result) > 1000


def test_africa_report_collapses_sources_before_continental_median():
    from malaria_intel.reports import build_africa_report_pdf

    frame = pd.DataFrame([
        {"iso3":"SOM","country":"Somalia","year":2022,"indicator_code":"INC","value":10.0,"source":"A"},
        {"iso3":"SOM","country":"Somalia","year":2022,"indicator_code":"INC","value":20.0,"source":"B"},
        {"iso3":"SOM","country":"Somalia","year":2022,"indicator_code":"INC","value":30.0,"source":"C"},
        {"iso3":"KEN","country":"Kenya","year":2022,"indicator_code":"INC","value":40.0,"source":"A"},
    ])
    result = build_africa_report_pdf(frame, 2022, 2022, ["INC"])
    assert result.startswith(b"%PDF")
    assert len(result) > 1000
