import asyncio

import httpx

from wxspot.geocoding import NominatimProvider, PlaceSearchResult, RadarStationProvider
from wxspot.main import app


def test_nominatim_search_is_explicit_and_parses_coordinate_results():
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "place_id": 123,
                    "osm_type": "relation",
                    "osm_id": 456,
                    "display_name": "Charleston, South Carolina, United States",
                    "lat": "32.7765",
                    "lon": "-79.9311",
                },
                {"display_name": "Bad coordinates", "lat": "91", "lon": "0"},
            ],
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = NominatimProvider(client, "https://search.example")
            return await provider.search("Charleston, SC", 33.02, -80.18)

    results = asyncio.run(run())
    assert results == [
        PlaceSearchResult(
            id="relation:456",
            name="Charleston, South Carolina, United States",
            lat=32.7765,
            lon=-79.9311,
        )
    ]
    assert requests[0].url.path == "/search"
    assert requests[0].url.params["q"] == "Charleston, SC"
    assert requests[0].url.params["format"] == "jsonv2"
    assert requests[0].url.params["viewbox"]
    assert "WxSpot" in requests[0].headers["user-agent"]


def test_radar_station_provider_filters_tdwr_and_sorts_by_distance():
    async def handler(_request):
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "attributes": {
                            "siteidentifier": "KCLX",
                            "sitename": "Charleston, SC",
                            "radartype": "NEXRAD",
                        },
                        "geometry": {"x": -80.0, "y": 33.0},
                    },
                    {
                        "attributes": {
                            "siteidentifier": "TATL",
                            "sitename": "Atlanta TDWR",
                            "radartype": "TDWR",
                        },
                        "geometry": {"x": -84.0, "y": 33.0},
                    },
                    {
                        "attributes": {
                            "siteidentifier": "KCAE",
                            "sitename": "Columbia, SC",
                            "radartype": "NEXRAD",
                        },
                        "geometry": {"x": -81.1, "y": 33.95},
                    },
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = RadarStationProvider(client, "https://stations.example/query")
            return await provider.nearby(33.0, -80.0)

    response = asyncio.run(run())
    assert [station.id for station in response.stations] == ["KCLX", "KCAE"]
    assert response.stations[0].distance_km == 0
    assert response.stations[1].distance_km > 100


def test_location_search_caches_results_and_returns_global_rate_limit(client):
    class SearchProvider:
        calls = 0

        async def search(self, query, latitude=None, longitude=None):
            self.calls += 1
            return [PlaceSearchResult(id="city:1", name=query, lat=33.0, lon=-80.0)]

    provider = SearchProvider()
    app.state.geocoder = provider

    first = client.get("/weather/locations/search?q=Charleston")
    assert first.status_code == 200
    assert first.json()["state"] == "ready"
    assert first.json()["attribution"] == "© OpenStreetMap contributors"

    cached = client.get("/weather/locations/search?q=Charleston")
    assert cached.status_code == 200
    assert cached.json()["results"] == first.json()["results"]
    assert provider.calls == 1

    throttled = client.get("/weather/locations/search?q=Savannah")
    assert throttled.status_code == 200
    assert throttled.json()["state"] == "busy"
    assert throttled.json()["retry_after_seconds"] >= 1
    assert provider.calls == 1


def test_station_provider_failure_is_a_typed_source_state(client):
    class FailingStations:
        async def nearby(self, *_args):
            from wxspot.geocoding import ProviderUnavailable

            raise ProviderUnavailable("Station inventory is unavailable.")

    app.state.radar_stations = FailingStations()
    response = client.get("/weather/radar/stations/nearby?lat=33&lon=-80")
    assert response.status_code == 200
    assert response.json()["state"] == "source_unavailable"
    assert response.json()["stations"] == []
