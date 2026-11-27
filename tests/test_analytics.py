import pandas as pd
import pytest
from malaria_intel.analytics import (
    answer_data_question, filter_observations, forecast_linear,
    latest_country_values, validate_observations, year_over_year,
)

@pytest.fixture
def observations():
    return pd.DataFrame([
        {"iso3":"SOM","country":"Somalia","year":2020,"indicator_code":"SH.MLR.INCD.P3","value":50.0,"source":"Test"},
        {"iso3":"SOM","country":"Somalia","year":2021,"indicator_code":"SH.MLR.INCD.P3","value":45.0,"source":"Test"},
        {"iso3":"SOM","country":"Somalia","year":2022,"indicator_code":"SH.MLR.INCD.P3","value":40.0,"source":"Test"},
        {"iso3":"SOM","country":"Somalia","year":2023,"indicator_code":"SH.MLR.INCD.P3","value":35.0,"source":"Test"},
        {"iso3":"KEN","country":"Kenya","year":2023,"indicator_code":"SH.MLR.INCD.P3","value":20.0,"source":"Test"},
    ])

def test_validate_removes_duplicate_and_counts_missing(observations):
    duplicate = pd.concat([observations, observations.iloc[[0]]], ignore_index=True)
    duplicate.loc[1,"value"] = None
    clean, quality = validate_observations(duplicate)
    assert len(clean) == 5
    assert quality["duplicate_keys_removed"] == 1
    assert quality["missing_values"] == 1

def test_validate_requires_schema():
    with pytest.raises(ValueError, match="Missing required columns"):
        validate_observations(pd.DataFrame({"year":[2020]}))

def test_filter_and_latest(observations):
    filtered = filter_observations(observations, indicator="SH.MLR.INCD.P3", countries=["SOM"], start_year=2021, end_year=2022)
    assert filtered.year.tolist() == [2021, 2022]
    latest = latest_country_values(observations, "SH.MLR.INCD.P3")
    assert dict(zip(latest.iso3, latest.year)) == {"SOM":2023,"KEN":2023}

def test_year_over_year(observations):
    result = year_over_year(observations, "SH.MLR.INCD.P3", "SOM")
    assert result.iloc[-1]["absolute_change"] == -5
    assert result.iloc[-1]["percent_change"] == pytest.approx(-12.5)

def test_forecast_requires_four_observations(observations):
    with pytest.raises(ValueError, match="four non-missing"):
        forecast_linear(observations.iloc[:2], "SH.MLR.INCD.P3", "SOM")

def test_forecast_is_nonnegative_and_bounded(observations):
    result = forecast_linear(observations, "SH.MLR.INCD.P3", "SOM", 2)
    assert result.year.tolist() == [2024, 2025]
    assert (result.forecast >= 0).all()

def test_model_free_assistant_uses_loaded_values(observations):
    answer = answer_data_question(observations, "What is malaria incidence in Somalia?", {"SOM":"Somalia"})
    assert "35" in answer and "2023" in answer

def test_model_free_assistant_does_not_invent_indicator(observations):
    answer = answer_data_question(observations, "Tell me the vaccine coverage", {"SOM":"Somalia"})
    assert "Specify an indicator" in answer
