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
