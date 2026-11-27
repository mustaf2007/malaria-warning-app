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
