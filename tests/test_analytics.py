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

def test_validate_drops_fractional_years_and_invalid_country_codes(observations):
    extra = pd.DataFrame([
        {"iso3":"SOM","country":"Somalia","year":2020.5,"indicator_code":"INC","value":1.0,"source":"Upload"},
        {"iso3":"nan","country":"Unknown","year":2021,"indicator_code":"INC","value":2.0,"source":"Upload"},
        {"iso3":" som ","country":"Somalia","year":2022,"indicator_code":"INC","value":3.0,"source":"Upload"},
        {"iso3":"KEN","country":"Kenya","year":"not-a-year","indicator_code":"INC","value":4.0,"source":"Upload"},
    ])
    clean, quality = validate_observations(pd.concat([observations, extra], ignore_index=True))
    assert len(clean) == len(observations) + 1
    accepted = clean[(clean["iso3"] == "SOM") & (clean["indicator_code"] == "INC")]
    assert len(accepted) == 1
    assert accepted.iloc[0]["year"] == 2022
    assert quality["invalid_rows_removed"] == 3
    assert quality["duplicate_keys_removed"] == 0


def test_validate_keeps_missing_values_but_rejects_invalid_keys(observations):
    extra = pd.DataFrame([{
        "iso3":"SOM","country":"Somalia","year":2024,"indicator_code":"INC",
        "value":None,"source":"Upload"
    }])
    clean, quality = validate_observations(pd.concat([observations, extra], ignore_index=True))
    assert len(clean) == len(observations) + 1
    assert quality["missing_values"] == 1
    assert quality["invalid_rows_removed"] == 0
    assert quality["duplicate_keys_removed"] == 0


def test_validate_requires_schema():
    with pytest.raises(ValueError, match="Missing required columns"):
        validate_observations(pd.DataFrame({"year":[2020]}))

def test_filter_and_latest(observations):
    filtered = filter_observations(observations, indicator="SH.MLR.INCD.P3", countries=["SOM"], start_year=2021, end_year=2022)
    assert filtered.year.tolist() == [2021, 2022]
    latest = latest_country_values(observations, "SH.MLR.INCD.P3")
    assert dict(zip(latest.iso3, latest.year)) == {"SOM":2023,"KEN":2023}

def test_latest_country_values_preserves_multiple_sources_for_latest_year(observations):
    extra = pd.DataFrame([{
        "iso3":"SOM", "country":"Somalia", "year":2023,
        "indicator_code":"SH.MLR.INCD.P3", "value":32.0, "source":"Second source"
    }])
    combined = pd.concat([observations, extra], ignore_index=True)
    latest = latest_country_values(combined, "SH.MLR.INCD.P3")
    somalia = latest[latest.iso3 == "SOM"]
    assert len(somalia) == 2
    assert set(somalia.source) == {"Test", "Second source"}
    assert set(somalia.value) == {35.0, 32.0}


def test_year_over_year(observations):
    result = year_over_year(observations, "SH.MLR.INCD.P3", "SOM")
    assert result.iloc[-1]["absolute_change"] == -5
    assert result.iloc[-1]["percent_change"] == pytest.approx(-12.5)

def test_year_over_year_does_not_treat_multi_year_gap_as_one_year(observations):
    sparse = observations[~((observations.iso3 == "SOM") & (observations.year == 2021))]
    result = year_over_year(sparse, "SH.MLR.INCD.P3", "SOM")
    row_2022 = result[result.year == 2022].iloc[0]
    assert row_2022["year_gap"] == 2
    assert pd.isna(row_2022["absolute_change"])
    assert pd.isna(row_2022["percent_change"])
    assert row_2022["change_status"] == "Gap or first observation"
    row_2023 = result[result.year == 2023].iloc[0]
    assert row_2023["year_gap"] == 1
    assert row_2023["absolute_change"] == -5
    assert row_2023["change_status"] == "Consecutive calendar year"


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



def test_data_quality_tables_report_missing_zero_and_freshness():
    from malaria_intel.analytics import build_data_quality_tables

    frame = pd.DataFrame([
        {"iso3":"SOM","country":"Somalia","year":2024,"indicator_code":"INC","value":0.0,"source":"World Bank"},
        {"iso3":"SOM","country":"Somalia","year":2025,"indicator_code":"INC","value":None,"source":"World Bank"},
        {"iso3":"KEN","country":"Kenya","year":2023,"indicator_code":"INC","value":12.0,"source":"OWID"},
        {"iso3":"KEN","country":"Kenya","year":2022,"indicator_code":"DEATHS","value":None,"source":"OWID"},
    ])

    result = build_data_quality_tables(frame, current_year=2026)
    overall = result["overall"].iloc[0]
    assert overall["rows_received"] == 4
    assert overall["non_missing_values"] == 2
    assert overall["missing_values"] == 2
    assert overall["zero_values"] == 1
    inc = result["indicators"].set_index("indicator_code").loc["INC"]
    assert inc["missing_pct"] == pytest.approx(100 / 3, abs=0.01)
    assert inc["latest_observation_year"] == 2024
    assert inc["years_behind_current"] == 2
    assert result["coverage"].set_index("iso3").loc["SOM", "INC"] == 1


def test_data_quality_tables_empty_frame_returns_empty_tables():
    from malaria_intel.analytics import build_data_quality_tables

    frame = pd.DataFrame(columns=["iso3","country","year","indicator_code","value","source"])
    result = build_data_quality_tables(frame, current_year=2026)
    assert result["overall"].iloc[0]["rows_received"] == 0
    assert result["indicators"].empty
    assert result["sources"].empty
    assert result["coverage"].empty


def test_validate_excludes_conflicting_values_from_same_source(observations):
    extra = pd.DataFrame([{
        "iso3": "SOM", "country": "Somalia", "year": 2023,
        "indicator_code": "SH.MLR.INCD.P3", "value": 99.0, "source": "Test"
    }])
    clean, quality = validate_observations(pd.concat([observations, extra], ignore_index=True))
    somalia_latest = clean[(clean.iso3 == "SOM") & (clean.year == 2023)]
    assert somalia_latest.empty
    assert quality["conflicting_keys_excluded"] == 1
    assert quality["conflicting_rows_excluded"] == 2


def test_validate_prefers_observed_value_over_missing_duplicate(observations):
    extra = pd.DataFrame([{
        "iso3": "SOM", "country": "Somalia", "year": 2023,
        "indicator_code": "SH.MLR.INCD.P3", "value": None, "source": "Test"
    }])
    clean, quality = validate_observations(pd.concat([observations, extra], ignore_index=True))
    row = clean[(clean.iso3 == "SOM") & (clean.year == 2023)].iloc[0]
    assert row["value"] == 35.0
    assert quality["duplicate_keys_removed"] == 1
    assert quality["conflicting_keys_excluded"] == 0


def test_model_free_assistant_summarizes_all_loaded_indicators(observations):
    extra = pd.DataFrame([
        {"iso3":"KEN","country":"Kenya","year":2022,"indicator_code":"SH.MLR.DEATHS","value":12.0,"source":"WHO"},
        {"iso3":"SOM","country":"Somalia","year":2023,"indicator_code":"SH.MLR.DEATHS","value":None,"source":"WHO"},
    ])
    combined = pd.concat([observations, extra], ignore_index=True)
    answer = answer_data_question(combined, "summarize over all data", {"SOM":"Somalia","KEN":"Kenya"})
    assert "Dataset-wide summary" in answer
    assert "2 indicators" in answer
    assert "SH.MLR.INCD.P3" in answer
    assert "SH.MLR.DEATHS" in answer
    assert "missing values" in answer
    assert "not pooled" in answer


def test_model_free_assistant_summary_does_not_pool_different_indicators(observations):
    answer = answer_data_question(observations, "Give me an overall dataset overview")
    assert "Indicator-by-indicator results" in answer
    assert "not pooled" in answer
    assert "population-weighted" in answer


def test_dataset_summary_handles_no_numeric_values(observations):
    from malaria_intel.analytics import summarize_loaded_dataset
    empty_values = observations.copy()
    empty_values["value"] = None
    answer = summarize_loaded_dataset(empty_values)
    assert "No numeric observations" in answer



def test_prepare_who_observations_maps_country_names_and_filters_non_african_rows():
    from malaria_intel.analytics import prepare_who_observations

    rows = [
        {"iso3": "som", "country": "SOM", "year": "2024", "value": "12.5", "indicator_code": "WHO_MAL"},
        {"iso3": "KEN", "country": "KEN", "year": 2023, "value": None, "indicator_code": "WHO_MAL"},
        {"iso3": "USA", "country": "USA", "year": 2024, "value": 5, "indicator_code": "WHO_MAL"},
        {"iso3": "SOM", "country": "SOM", "year": 2024.5, "value": 9, "indicator_code": "WHO_MAL"},
    ]

    result = prepare_who_observations(rows, {"SOM": "Somalia", "KEN": "Kenya"})

    assert len(result) == 2
    assert result[0]["iso3"] == "SOM"
    assert result[0]["country"] == "Somalia"
    assert result[0]["year"] == 2024
    assert result[0]["value"] == 12.5
    assert result[1]["country"] == "Kenya"
    assert result[1]["value"] is None


def test_prepare_who_observations_handles_empty_input():
    from malaria_intel.analytics import prepare_who_observations

    assert prepare_who_observations([], {"SOM": "Somalia"}) == []
