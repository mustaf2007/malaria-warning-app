from malaria_intel import data_sources


def test_who_discovery_uses_odata_default_json_and_filters_malaria(monkeypatch):
    calls = []

    def fake_rows(url, params=None):
        calls.append((url, params))
        return [
            {"IndicatorCode": "MALARIA_1", "IndicatorName": "Malaria incidence"},
            {"IndicatorCode": "OTHER_1", "IndicatorName": "Tuberculosis incidence"},
            {"IndicatorCode": "MALARIA_2", "IndicatorName": "Severe malaria cases"},
        ]

    monkeypatch.setattr(data_sources, "_get_odata_rows", fake_rows)
    result = data_sources.discover_who_malaria_indicators()

    assert calls == [
        (f"{data_sources.WHO_GHO_BASE}/Indicator", {"$top": 1000})
    ]
    assert [item["code"] for item in result] == ["MALARIA_1", "MALARIA_2"]
    assert all(item["source"] == "WHO Global Health Observatory" for item in result)


def test_who_odata_reader_follows_server_next_link(monkeypatch):
    requested = []

    def fake_get_json(url, params=None):
        requested.append((url, params))
        if url.endswith("/Indicator"):
            return {
                "value": [{"IndicatorCode": "A"}],
                "@odata.nextLink": "https://ghoapi.azureedge.net/api/Indicator?page=2",
            }
        return {"value": [{"IndicatorCode": "B"}]}

    monkeypatch.setattr(data_sources, "_get_json", fake_get_json)
    rows = data_sources._get_odata_rows(
        f"{data_sources.WHO_GHO_BASE}/Indicator", {"$top": 1000}
    )

    assert [row["IndicatorCode"] for row in rows] == ["A", "B"]
    assert requested == [
        (f"{data_sources.WHO_GHO_BASE}/Indicator", {"$top": 1000}),
        ("https://ghoapi.azureedge.net/api/Indicator?page=2", None),
    ]



def test_selected_who_indicator_uses_bounded_odata_pagination(monkeypatch):
    calls = []

    def fake_rows(url, params=None):
        calls.append((url, params))
        return [{
            "TimeDim": 2024,
            "SpatialDim": "SOM",
            "NumericValue": "12.5",
            "TimeDimensionValue": "2024",
        }]

    monkeypatch.setattr(data_sources, "_get_odata_rows", fake_rows)
    result = data_sources.fetch_who_gho_indicator("MALARIA_1")

    assert calls == [
        (f"{data_sources.WHO_GHO_BASE}/MALARIA_1", {"$top": 1000})
    ]
    assert result == [{
        "iso3": "SOM",
        "country": "SOM",
        "year": 2024,
        "indicator_code": "MALARIA_1",
        "value": 12.5,
        "source": "WHO Global Health Observatory",
        "source_url": "https://www.who.int/data/gho/data/indicators/indicator-details/GHO/MALARIA_1",
        "last_updated": "2024",
    }]



def test_who_odata_reader_rejects_external_pagination_host(monkeypatch):
    requested = []

    def fake_get_json(url, params=None):
        requested.append(url)
        return {
            "value": [{"IndicatorCode": "A"}],
            "@odata.nextLink": "https://attacker.example/steal",
        }

    monkeypatch.setattr(data_sources, "_get_json", fake_get_json)
    import pytest

    with pytest.raises(data_sources.DataSourceError, match="outside the official"):
        data_sources._get_odata_rows(f"{data_sources.WHO_GHO_BASE}/Indicator")
    assert requested == [f"{data_sources.WHO_GHO_BASE}/Indicator"]


def test_who_odata_reader_rejects_malformed_records(monkeypatch):
    import pytest

    monkeypatch.setattr(data_sources, "_get_json", lambda *args, **kwargs: {"value": "not-a-list"})
    with pytest.raises(data_sources.DataSourceError, match="valid records list"):
        data_sources._get_odata_rows(f"{data_sources.WHO_GHO_BASE}/Indicator")


def test_who_odata_reader_fails_instead_of_silently_truncating(monkeypatch):
    import pytest

    def fake_get_json(url, params=None):
        return {
            "value": [{"IndicatorCode": "A"}],
            "@odata.nextLink": f"{data_sources.WHO_GHO_BASE}/Indicator?page=next",
        }

    monkeypatch.setattr(data_sources, "_get_json", fake_get_json)
    with pytest.raises(data_sources.DataSourceError, match="safety limit"):
        data_sources._get_odata_rows(f"{data_sources.WHO_GHO_BASE}/Indicator")
