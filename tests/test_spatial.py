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



def test_fetch_admin1_boundaries_uses_geo_boundaries_metadata_and_validates_geometry(monkeypatch):
    responses = iter([
        FakeResponse({
            "boundaryName": "Kenya",
            "boundaryYearRepresented": "2022",
            "boundarySource": "Survey of Kenya",
            "boundaryLicense": "CC BY 4.0",
            "simplifiedGeometryGeoJSON": "https://www.geoboundaries.org/files/ken_adm1.geojson",
        }),
        FakeResponse({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"shapeName": "Nairobi"},
                "geometry": _geojson()["features"][0]["geometry"],
            }],
        }),
    ])
    monkeypatch.setattr(spatial.requests, "get", lambda *args, **kwargs: next(responses))

    result = spatial.fetch_admin1_boundaries("ken")

    assert result["iso3"] == "KEN"
    assert result["boundary_year"] == "2022"
    assert len(result["geojson"]["features"]) == 1
    assert result["license"] == "CC BY 4.0"


def test_fetch_admin1_boundaries_rejects_untrusted_download_url(monkeypatch):
    monkeypatch.setattr(
        spatial.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({
            "gjDownloadURL": "https://attacker.example/kenya.geojson"
        }),
    )
    with pytest.raises(spatial.BoundaryDataError, match="untrusted"):
        spatial.fetch_admin1_boundaries("KEN")


def test_join_admin1_estimates_matches_unique_normalised_names():
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"shapeName": "Nairobi City"}, "geometry": _geojson()["features"][0]["geometry"]},
            {"type": "Feature", "properties": {"shapeName": "Mombasa"}, "geometry": _geojson()["features"][0]["geometry"]},
            {"type": "Feature", "properties": {"shapeName": "Unknown County"}, "geometry": _geojson()["features"][0]["geometry"]},
        ],
    }
    units = [{"id": 1, "name": "Nairobi City"}, {"id": 2, "name": "Mombasa"}]
    estimates = [
        {"admin1_id": "1", "year": 2022, "value": 10.0},
        {"admin1_id": "2", "year": 2022, "value": 20.0},
        {"admin1_id": "3", "year": 2022, "value": 30.0},
    ]

    result = spatial.join_admin1_estimates_to_geojson(geojson, units, estimates)

    assert result["matched_units"] == 2
    assert result["total_map_units"] == 2
    assert {row["map_admin1_id"] for row in result["rows"]} == {"1", "2"}
    assert result["unmatched_map_names"] == []


def test_join_admin1_estimates_does_not_guess_ambiguous_names():
    geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"shapeName": "Central"},
            "geometry": _geojson()["features"][0]["geometry"],
        }],
    }
    units = [{"id": 1, "name": "Central"}, {"id": 2, "name": "Central"}]
    result = spatial.join_admin1_estimates_to_geojson(geojson, units, [
        {"admin1_id": "1", "year": 2020, "value": 1}
    ])
    assert result["matched_units"] == 0
    assert result["rows"] == []
    assert len(result["unmatched_map_names"]) == 2



def test_join_admin1_estimates_excludes_duplicate_boundary_names():
    feature = {
        "type": "Feature",
        "properties": {"shapeName": "Central"},
        "geometry": _geojson()["features"][0]["geometry"],
    }
    geojson = {"type": "FeatureCollection", "features":[feature, dict(feature)]}
    units = [{"id": "10", "name": "Central"}]
    result = spatial.join_admin1_estimates_to_geojson(
        geojson, units, [{"admin1_id":"10","year":2021,"value":4.0}]
    )
    assert result["matched_units"] == 0
    assert result["rows"] == []
    assert result["unmatched_map_names"] == ["Central"]


def test_join_admin1_estimates_excludes_non_finite_values():
    geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"shapeName": "Nairobi"},
            "geometry": _geojson()["features"][0]["geometry"],
        }],
    }
    result = spatial.join_admin1_estimates_to_geojson(
        geojson, [{"id":"1","name":"Nairobi"}],
        [{"admin1_id":"1","year":2022,"value":float("nan")}],
    )
    assert result["matched_units"] == 1
    assert result["rows"] == []
