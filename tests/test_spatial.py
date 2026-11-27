import pytest
from malaria_intel import spatial


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self.payload


def _geojson():
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [40.0, -2.0], [42.0, -2.0], [42.0, 1.0],
                    [40.0, 1.0], [40.0, -2.0]
                ]]
            }
        }]
    }


def test_fetch_country_boundary_returns_valid_geojson_and_leaflet_bounds(monkeypatch):
    calls = []
    def fake_get(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return FakeResponse([{
                "boundaryName": "Kenya",
                "simplifiedGeometryGeoJSON": "https://www.geoboundaries.org/files/kenya.geojson",
                "license": "CC BY 4.0",
            }])
        return FakeResponse(_geojson())
    monkeypatch.setattr(spatial.requests, "get", fake_get)

    result = spatial.fetch_country_boundary("ken")

    assert result["iso3"] == "KEN"
    assert result["name"] == "Kenya"
    assert result["bounds"] == [[-2.0, 40.0], [1.0, 42.0]]
    assert result["bbox"] == [40.0, -2.0, 42.0, 1.0]
    assert len(calls) == 2


@pytest.mark.parametrize("code", ["", "SO", "SOM1", "S0M"])
def test_fetch_country_boundary_rejects_invalid_iso3(code):
    with pytest.raises(ValueError, match="ISO3"):
        spatial.fetch_country_boundary(code)


def test_fetch_country_boundary_rejects_untrusted_download_host(monkeypatch):
    monkeypatch.setattr(
        spatial.requests,
        "get",
        lambda *args, **kwargs: FakeResponse([{
            "gjDownloadURL": "https://attacker.example/boundary.geojson"
        }]),
    )
    with pytest.raises(spatial.BoundaryDataError, match="untrusted"):
        spatial.fetch_country_boundary("SOM")


def test_fetch_country_boundary_rejects_non_polygon_geojson(monkeypatch):
    responses = iter([
        FakeResponse([{"gjDownloadURL": "https://www.geoboundaries.org/files/som.geojson"}]),
        FakeResponse({"type": "FeatureCollection", "features": []}),
    ])
    monkeypatch.setattr(spatial.requests, "get", lambda *args, **kwargs: next(responses))
    with pytest.raises(spatial.BoundaryDataError, match="no features"):
        spatial.fetch_country_boundary("SOM")
