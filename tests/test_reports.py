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
