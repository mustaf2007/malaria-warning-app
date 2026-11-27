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


def test_who_odata_reader_rejects_nonstandard_initial_port(monkeypatch):
    import pytest

    def should_not_fetch(*args, **kwargs):
        raise AssertionError("Invalid initial URL must be rejected before HTTP")

    monkeypatch.setattr(data_sources, "_get_json", should_not_fetch)
    with pytest.raises(data_sources.DataSourceError, match="official HTTPS API host and port"):
        data_sources._get_odata_rows("https://ghoapi.azureedge.net:444/api/Indicator")


def test_who_odata_reader_accepts_relative_same_host_next_link(monkeypatch):
    requested = []

    def fake_get_json(url, params=None):
        requested.append((url, params))
        if len(requested) == 1:
            return {"value": [{"id": 1}], "@odata.nextLink": "?$skip=1000"}
        return {"value": [{"id": 2}]}

    monkeypatch.setattr(data_sources, "_get_json", fake_get_json)
    rows = data_sources._get_odata_rows(f"{data_sources.WHO_GHO_BASE}/Indicator")

    assert rows == [{"id": 1}, {"id": 2}]
    assert requested[1][0] == f"{data_sources.WHO_GHO_BASE}/Indicator?$skip=1000"
    assert requested[1][1] is None


def test_get_json_retries_transient_http_failure(monkeypatch):
    calls = []
    responses = [data_sources.requests.ConnectionError("temporary outage"), {"ok": True}]

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return result

        return Response()

    monkeypatch.setattr(data_sources.requests, "get", fake_get)
    monkeypatch.setattr(data_sources.time, "sleep", lambda *_: None)

    assert data_sources._get_json("https://example.org/data") == {"ok": True}
    assert len(calls) == 2
