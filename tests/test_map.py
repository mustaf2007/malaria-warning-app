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

def test_resolve_map_wms_layer_matches_release_reference(monkeypatch):
    class Response:
        content = b'<WMS_Capabilities><Capability><Layer><Layer><Name>Malaria:202508_Global_Pf_Incidence_Rate</Name><Dimension name="time" units="ISO8601">2000-01-01T00:00:00.000Z/2025-01-01T00:00:00.000Z/P1Y</Dimension></Layer></Layer></Capability></WMS_Capabilities>'
        def raise_for_status(self):
            pass
    captured={}
    def fake_get(url, **kwargs):
        captured["url"]=url
        return Response()
    monkeypatch.setattr(data_sources.requests,"get",fake_get)
    result=data_sources.resolve_map_wms_layer("Malaria__202508_Global_Pf_Incidence_Rate")
    assert result["workspace"]=="Malaria"
    assert result["layer"]=="Malaria:202508_Global_Pf_Incidence_Rate"
    assert captured["url"].endswith("/Malaria/ows")

def test_resolve_map_wms_layer_rejects_unadvertised_layer(monkeypatch):
    class Response:
        content=b'<WMS_Capabilities><Capability><Layer><Name>some:other_layer</Name></Layer></Capability></WMS_Capabilities>'
        def raise_for_status(self):
            pass
    monkeypatch.setattr(data_sources.requests,"get",lambda *args,**kwargs:Response())
    with pytest.raises(data_sources.DataSourceError,match="did not advertise"):
        data_sources.resolve_map_wms_layer("Malaria__202508_Global_Pf_Incidence_Rate")

def test_map_wms_preview_checks_image_and_requests_selected_year(monkeypatch):
    png=bytes([137,80,78,71,13,10,26,10]) + bytes([0,0,0,13]) + b"IHDR" + (1600).to_bytes(4,"big") + (900).to_bytes(4,"big") + bytes([8,6,0,0,0]) + bytes([0,0,0,0])
    class Capabilities:
        content=b'<WMS_Capabilities><Capability><Layer><Name>Malaria:202508_Global_Pf_Incidence_Rate</Name><Dimension name="time" units="ISO8601">2000-01-01T00:00:00.000Z/2025-01-01T00:00:00.000Z/P1Y</Dimension></Layer></Capability></WMS_Capabilities>'
        headers={"Content-Type":"text/xml"}
        def raise_for_status(self):
            pass
    class ImageResponse:
        content=png
        headers={"Content-Type":"image/png"}
        def raise_for_status(self):
            pass
    calls=[]
    def fake_get(url,params=None,**kwargs):
        calls.append((url,params))
        return Capabilities() if len(calls)==1 else ImageResponse()
    monkeypatch.setattr(data_sources.requests,"get",fake_get)
    result=data_sources.fetch_map_wms_preview("Malaria__202508_Global_Pf_Incidence_Rate",2024)
    assert result==png
    assert calls[1][1]["time"]=="2024-01-01T00:00:00.000Z"
    assert calls[1][1]["layers"]=="Malaria:202508_Global_Pf_Incidence_Rate"

def test_map_wms_preview_rejects_html_error(monkeypatch):
    class Capabilities:
        content=b'<WMS_Capabilities><Capability><Layer><Name>Malaria:202508_Global_Pf_Incidence_Rate</Name><Dimension name="time" units="ISO8601">2000-01-01T00:00:00.000Z/2025-01-01T00:00:00.000Z/P1Y</Dimension></Layer></Capability></WMS_Capabilities>'
        headers={"Content-Type":"text/xml"}
        def raise_for_status(self):
            pass
    class ErrorResponse:
        content=b"<html>WMS error</html>"
        headers={"Content-Type":"text/html"}
        text="<html>WMS error</html>"
        def raise_for_status(self):
            pass
    calls=[]
    def fake_get(*args,**kwargs):
        calls.append(1)
        return Capabilities() if len(calls)==1 else ErrorResponse()
    monkeypatch.setattr(data_sources.requests,"get",fake_get)
    with pytest.raises(data_sources.DataSourceError,match="did not return a PNG"):
        data_sources.fetch_map_wms_preview("Malaria__202508_Global_Pf_Incidence_Rate",2024)


def test_map_wms_layer_reads_published_time_range(monkeypatch):
    class Response:
        content=b'<WMS_Capabilities><Capability><Layer><Layer><Name>Malaria:layer_a</Name><Dimension name="time">2001-01-01T00:00:00.000Z/2023-01-01T00:00:00.000Z/P1Y</Dimension></Layer></Layer></Capability></WMS_Capabilities>'
        def raise_for_status(self):
            pass
    monkeypatch.setattr(data_sources.requests,"get",lambda *args,**kwargs:Response())
    info=data_sources.resolve_map_wms_layer("Malaria__layer_a")
    assert info["min_year"]==2001
    assert info["max_year"]==2023
    assert data_sources.map_wms_time_for_year(info,2015)=="2015-01-01T00:00:00.000Z"

def test_map_wms_layer_preserves_exact_advertised_time(monkeypatch):
    class Response:
        content=b'<WMS_Capabilities><Capability><Layer><Layer><Name>Malaria:layer_a</Name><Dimension name="time">2019-01-01T00:00:00.000Z,2021-01-01T00:00:00.000Z</Dimension></Layer></Layer></Capability></WMS_Capabilities>'
        def raise_for_status(self):
            pass
    monkeypatch.setattr(data_sources.requests,"get",lambda *args,**kwargs:Response())
    info=data_sources.resolve_map_wms_layer("Malaria__layer_a")
    assert data_sources.map_wms_time_for_year(info,2021)=="2021-01-01T00:00:00.000Z"
    with pytest.raises(ValueError,match="not available"):
        data_sources.map_wms_time_for_year(info,2020)

def test_static_map_raster_does_not_accept_year():
    info={"time_values":None,"min_year":None,"max_year":None}
    assert data_sources.map_wms_time_for_year(info,None) is None
    with pytest.raises(ValueError,match="static"):
        data_sources.map_wms_time_for_year(info,2020)


def test_map_jsonstat_rejects_non_contiguous_category_positions():
    payload = _jsonstat()
    payload["dimension"]["ID"]["category"]["index"] = {"103": 0, "104": 2}
    with pytest.raises(data_sources.DataSourceError, match="unique and contiguous"):
        data_sources._jsonstat_rows(payload, "admin1", "Pf_incidence-count", "mean", "https://example.test")


def test_map_jsonstat_rejects_duplicate_category_positions():
    payload = _jsonstat()
    payload["dimension"]["Year"]["category"]["index"] = {"2020": 0, "2021": 0}
    with pytest.raises(data_sources.DataSourceError, match="unique and contiguous"):
        data_sources._jsonstat_rows(payload, "admin1", "Pf_incidence-count", "mean", "https://example.test")


def test_map_jsonstat_rejects_missing_dimension_or_invalid_values():
    with pytest.raises(data_sources.DataSourceError, match="dimension metadata"):
        data_sources._jsonstat_rows({}, "admin1", "Pf_incidence-count", "mean", "https://example.test")
    payload = _jsonstat()
    payload["value"] = "not-an-array"
    with pytest.raises(data_sources.DataSourceError, match="array or indexed object"):
        data_sources._jsonstat_rows(payload, "admin1", "Pf_incidence-count", "mean", "https://example.test")


def test_map_jsonstat_rejects_invalid_year_category():
    payload = _jsonstat()
    payload["dimension"]["Year"]["category"]["index"] = {"unknown": 0}
    with pytest.raises(data_sources.DataSourceError, match="invalid positions or years"):
        data_sources._jsonstat_rows(payload, "admin1", "Pf_incidence-count", "mean", "https://example.test")


def test_map_wms_capabilities_rejects_unrelated_xml_document(monkeypatch):
    class Response:
        content=b"<html><body>temporary upstream error</body></html>"
        def raise_for_status(self):
            pass
    monkeypatch.setattr(data_sources.requests,"get",lambda *args,**kwargs:Response())
    with pytest.raises(data_sources.DataSourceError,match="unexpected XML document"):
        data_sources.resolve_map_wms_layer("Malaria__layer_a")


def test_map_wms_preview_rejects_truncated_png_header(monkeypatch):
    class Capabilities:
        content=b'<WMS_Capabilities><Capability><Layer><Name>Malaria:layer_a</Name><Dimension name="time">2000-01-01T00:00:00.000Z/2025-01-01T00:00:00.000Z/P1Y</Dimension></Layer></Capability></WMS_Capabilities>'
        def raise_for_status(self):
            pass
    class ImageResponse:
        content=bytes([137,80,78,71,13,10,26,10])
        headers={"Content-Type":"image/png"}
        def raise_for_status(self):
            pass
    calls=[]
    def fake_get(*args,**kwargs):
        calls.append(1)
        return Capabilities() if len(calls)==1 else ImageResponse()
    monkeypatch.setattr(data_sources.requests,"get",fake_get)
    with pytest.raises(data_sources.DataSourceError,match="truncated or invalid PNG header"):
        data_sources.fetch_map_wms_preview("Malaria__layer_a",2024)


def test_map_wms_preview_rejects_wrong_png_dimensions(monkeypatch):
    png=bytes([137,80,78,71,13,10,26,10]) + bytes([0,0,0,13]) + b"IHDR" + (800).to_bytes(4,"big") + (450).to_bytes(4,"big") + bytes([8,6,0,0,0]) + bytes([0,0,0,0])
    class Capabilities:
        content=b'<WMS_Capabilities><Capability><Layer><Name>Malaria:layer_a</Name><Dimension name="time">2000-01-01T00:00:00.000Z/2025-01-01T00:00:00.000Z/P1Y</Dimension></Layer></Capability></WMS_Capabilities>'
        def raise_for_status(self):
            pass
    class ImageResponse:
        content=png
        headers={"Content-Type":"image/png"}
        def raise_for_status(self):
            pass
    calls=[]
    def fake_get(*args,**kwargs):
        calls.append(1)
        return Capabilities() if len(calls)==1 else ImageResponse()
    monkeypatch.setattr(data_sources.requests,"get",fake_get)
    with pytest.raises(data_sources.DataSourceError,match="dimensions do not match"):
        data_sources.fetch_map_wms_preview("Malaria__layer_a",2024)
