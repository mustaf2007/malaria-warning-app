import pytest
from malaria_intel import data_sources

def _jsonstat():
    return {
        "class":"dataset",
        "dimension":{
            "ID":{"category":{"index":{"103":"0","104":"1"},"label":{"103":"Kano","104":"Lagos"}}},
            "Year":{"category":{"index":{"2020":0,"2021":1},"label":{"2020":"2020","2021":"2021"}}}
        },
        "value":[10,11,20,21]
    }

def test_map_jsonstat_decodes_admin1_and_year_order():
    rows=data_sources._jsonstat_rows(_jsonstat(),"admin1","Pf_incidence-count","mean","https://example.test")
    assert len(rows)==4
    assert rows[0]["admin1_id"]=="103"
    assert rows[0]["country"]=="Kano"
    assert rows[0]["year"]==2020
    assert rows[0]["value"]==10.0
    assert rows[3]["value"]==21.0

def test_map_jsonstat_supports_value_dictionary():
    payload=_jsonstat()
    payload["value"]={"0":3,"1":4,"2":5,"3":6}
    rows=data_sources._jsonstat_rows(payload,"admin1","Pf_incidence-count","mean","https://example.test")
    assert [r["value"] for r in rows]==[3.0,4.0,5.0,6.0]

def test_map_series_requires_explicit_geography(monkeypatch):
    with pytest.raises(ValueError,match="exactly one geography"):
        data_sources.fetch_map_series("Pf_incidence-count","202608","admin0")

def test_map_series_rejects_unknown_metric():
    with pytest.raises(ValueError,match="Unsupported MAP metric"):
        data_sources.fetch_map_series("unknown","202608","admin0",iso3="SOM")

def test_map_series_builds_filtered_api_request(monkeypatch):
    captured={}
    def fake_get(url,params=None):
        captured["url"]=url
        captured["params"]=params
        return _jsonstat()
    monkeypatch.setattr(data_sources,"_get_json",fake_get)
    rows=data_sources.fetch_map_series("Pf_incidence-count","202608","admin1",iso3="NGA")
    assert "/malaria/Pf_incidence-count/admin1/mean" in captured["url"]
    assert captured["params"]=={"version":"202608","iso3":"NGA"}
    assert len(rows)==4

def test_map_admin1_filters_by_iso3(monkeypatch):
    payload=[
        {"id":103,"name":"Kano","countryName":"Nigeria","iso3":"NGA"},
        {"id":104,"name":"Lagos","countryName":"Nigeria","iso3":"NGA"},
        {"id":105,"name":"Nairobi","countryName":"Kenya","iso3":"KEN"},
    ]
    monkeypatch.setattr(data_sources,"_get_json",lambda *args,**kwargs:payload)
    rows=data_sources.fetch_map_admin1("NGA","2023_mg_5k")
    assert [r["name"] for r in rows]==["Kano","Lagos"]
    assert all(r["iso3"]=="NGA" for r in rows)

def test_map_jsonstat_supports_array_category_indexes():
    payload = {
        "dimension": {
            "ID": {"category": {"index": ["103", "104"], "label": {"103": "Kano", "104": "Lagos"}}},
            "Year": {"category": {"index": ["2020", "2021"], "label": {"2020": "2020", "2021": "2021"}}},
        },
        "value": [1, 2, 3, 4],
    }
    rows = data_sources._jsonstat_rows(payload, "admin1", "Pf_incidence-count", "mean", "https://example.test")
    assert [(r["admin1_id"], r["year"], r["value"]) for r in rows] == [
        ("103", 2020, 1.0), ("103", 2021, 2.0), ("104", 2020, 3.0), ("104", 2021, 4.0)
    ]
