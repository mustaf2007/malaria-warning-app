import pandas as pd
import pytest

from malaria_intel.reports import build_africa_report_pdf


@pytest.fixture
def africa_data():
    return pd.DataFrame([
        {"iso3": "SOM", "country": "Somalia", "year": 2020, "indicator_code": "INC", "value": 100.0, "source": "World Bank"},
        {"iso3": "SOM", "country": "Somalia", "year": 2021, "indicator_code": "INC", "value": 80.0, "source": "World Bank"},
        {"iso3": "KEN", "country": "Kenya", "year": 2020, "indicator_code": "INC", "value": 40.0, "source": "World Bank"},
        {"iso3": "KEN", "country": "Kenya", "year": 2021, "indicator_code": "INC", "value": 30.0, "source": "World Bank"},
        {"iso3": "ETH", "country": "Ethiopia", "year": 2021, "indicator_code": "INC", "value": None, "source": "World Bank"},
        {"iso3": "SOM", "country": "Somalia", "year": 2021, "indicator_code": "CASES", "value": 2500.0, "source": "WHO GHO"},
        {"iso3": "KEN", "country": "Kenya", "year": 2021, "indicator_code": "CASES", "value": 1200.0, "source": "WHO GHO"},
    ])


def test_builds_africa_pdf_for_multiple_indicators(africa_data):
    pdf = build_africa_report_pdf(
        africa_data, 2020, 2021, ["INC", "CASES"],
        indicator_labels={"INC": "Malaria incidence", "CASES": "Reported cases"},
    )
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1500


def test_rejects_empty_indicator_selection(africa_data):
    with pytest.raises(ValueError, match="at least one indicator"):
        build_africa_report_pdf(africa_data, 2020, 2021, [])


def test_rejects_more_than_eight_indicators(africa_data):
    with pytest.raises(ValueError, match="no more than eight"):
        build_africa_report_pdf(africa_data, 2020, 2021, [f"I{i}" for i in range(9)])


def test_rejects_reversed_year_period(africa_data):
    with pytest.raises(ValueError, match="Start year"):
        build_africa_report_pdf(africa_data, 2022, 2020, ["INC"])


def test_rejects_period_without_observations(africa_data):
    with pytest.raises(ValueError, match="No non-missing observations"):
        build_africa_report_pdf(africa_data, 2010, 2012, ["INC"])
