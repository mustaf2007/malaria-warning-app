import pytest
from malaria_intel import data_sources

class FakeResponse:
    def __init__(self, text):
        self.text = text
    def raise_for_status(self):
        return None

def test_owid_grapher_normalizes_country_rows(monkeypatch):
    csv = "Entity,Code,Year,Death rate from malaria\nSomalia,SOM,2020,12.5\nKenya,KEN,2021,8.2\nAfrica,,2021,14.0\n"
    monkeypatch.setattr(data_sources.requests, "get", lambda *args, **kwargs: FakeResponse(csv))
    rows = data_sources.fetch_owid_grapher("death-rate-from-malaria", 2020, 2021)
    assert len(rows) == 2
    assert rows[0]["iso3"] == "SOM"
    assert rows[0]["indicator_code"] == "OWID:death-rate-from-malaria"
    assert rows[1]["value"] == 8.2

def test_owid_grapher_rejects_unapproved_slug():
    with pytest.raises(ValueError, match="not in the approved catalogue"):
        data_sources.fetch_owid_grapher("unknown-malaria-series")


def test_dashboard_bundle_keeps_indicator_data_when_country_metadata_fails(monkeypatch):
    expected_rows = [{"iso3": "SOM", "country": "Somalia", "year": 2022, "indicator_code": "TEST", "value": 1.0, "source": "test"}]
    monkeypatch.setattr(data_sources, "fetch_african_countries", lambda: (_ for _ in ()).throw(RuntimeError("metadata timeout")))
    monkeypatch.setattr(data_sources, "fetch_indicator_bundle", lambda start, end: (expected_rows, [{"code": "TEST", "status": "loaded", "records": "1", "non_missing": "1", "source": "World Bank"}]))
    monkeypatch.setattr(data_sources, "fetch_owid_bundle", lambda start, end: ([], []))

    countries, rows, statuses = data_sources.fetch_dashboard_bundle(2000, 2024)

    assert countries == []
    assert rows == expected_rows
    assert any(item["code"] == "COUNTRY_METADATA" and item["status"] == "unavailable" for item in statuses)
    assert any(item["code"] == "TEST" and item["status"] == "loaded" for item in statuses)


def test_dashboard_bundle_keeps_world_bank_rows_when_owid_fails(monkeypatch):
    expected_rows = [{"iso3": "SOM", "country": "Somalia", "year": 2022, "indicator_code": "TEST", "value": 1.0, "source": "test"}]
    monkeypatch.setattr(data_sources, "fetch_african_countries", lambda: [{"iso3": "SOM", "name": "Somalia"}])
    monkeypatch.setattr(data_sources, "fetch_indicator_bundle", lambda start, end: (expected_rows, []))
    monkeypatch.setattr(data_sources, "fetch_owid_bundle", lambda start, end: (_ for _ in ()).throw(RuntimeError("OWID unavailable")))

    countries, rows, statuses = data_sources.fetch_dashboard_bundle(2000, 2024)

    assert countries[0]["iso3"] == "SOM"
    assert rows == expected_rows
    assert any(item["code"] == "OWID_BUNDLE" and item["status"] == "unavailable" for item in statuses)


def test_dashboard_bundle_returns_status_when_all_sources_fail(monkeypatch):
    monkeypatch.setattr(data_sources, "fetch_african_countries", lambda: (_ for _ in ()).throw(RuntimeError("metadata offline")))
    monkeypatch.setattr(data_sources, "fetch_indicator_bundle", lambda start, end: (_ for _ in ()).throw(RuntimeError("World Bank offline")))
    monkeypatch.setattr(data_sources, "fetch_owid_bundle", lambda start, end: (_ for _ in ()).throw(RuntimeError("OWID offline")))

    countries, rows, statuses = data_sources.fetch_dashboard_bundle(2000, 2024)

    assert countries == []
    assert rows == []
    assert len(statuses) == 3
    assert all(item["status"] == "unavailable" for item in statuses)


def test_dashboard_bundle_defaults_to_1960_through_current_year(monkeypatch):
    from datetime import datetime, timezone
    from malaria_intel import config

    expected_end = datetime.now(timezone.utc).year
    assert config.DEFAULT_START_YEAR == 1960
    assert config.DEFAULT_END_YEAR == expected_end


def test_african_country_catalogue_includes_sub_saharan_and_north_africa(monkeypatch):
    payload = [
        {"id": "header"},
        [
            {"id": "SOM", "iso2Code": "SO", "name": "Somalia", "region": {"value": "Sub-Saharan Africa"}},
            {"id": "NGA", "iso2Code": "NG", "name": "Nigeria", "region": {"value": "Sub-Saharan Africa"}},
            {"id": "DZA", "iso2Code": "DZ", "name": "Algeria", "region": {"value": "Middle East & North Africa"}},
            {"id": "EGY", "iso2Code": "EG", "name": "Egypt", "region": {"value": "Middle East & North Africa"}},
            {"id": "FRA", "iso2Code": "FR", "name": "France", "region": {"value": "Europe & Central Asia"}},
        ],
    ]
    monkeypatch.setattr(data_sources, "_get_json", lambda *args, **kwargs: payload)
    countries = data_sources.fetch_african_countries()
    codes = {country["iso3"] for country in countries}
    assert {"SOM", "NGA", "DZA", "EGY"}.issubset(codes)
    assert "FRA" not in codes
