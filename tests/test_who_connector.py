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
                "@odata.nextLink": "https://example.test/Indicator?page=2",
            }
        return {"value": [{"IndicatorCode": "B"}]}

    monkeypatch.setattr(data_sources, "_get_json", fake_get_json)
    rows = data_sources._get_odata_rows(
        f"{data_sources.WHO_GHO_BASE}/Indicator", {"$top": 1000}
    )

    assert [row["IndicatorCode"] for row in rows] == ["A", "B"]
    assert requested == [
        (f"{data_sources.WHO_GHO_BASE}/Indicator", {"$top": 1000}),
        ("https://example.test/Indicator?page=2", None),
    ]
