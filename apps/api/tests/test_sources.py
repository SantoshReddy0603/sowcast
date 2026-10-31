import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from sowcast.api.app import create_app
from sowcast.sources.base import metadata
from sowcast.sources.flood import FloodClient
from sowcast.sources.geocoding import GeocodingClient
from sowcast.sources.mandi import MandiClient
from sowcast.sources.models import Location, SourceError
from sowcast.sources.power import PowerClient
from sowcast.sources.soil import SoilClient
from sowcast.sources.transport import SourceTransport

RECORDINGS = Path(__file__).parent / "recorded"
LOCATION = Location(latitude=13.14, longitude=78.13)


def recorded(name):
    return json.loads((RECORDINGS / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_geocoding_recording_and_empty_response():
    payload = recorded("geocoding")

    def respond(request):
        assert request.url.params["countryCode"] == "IN"
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = GeocodingClient(SourceTransport(http, source="Open-Meteo geocoding"))
        evidence = await client.fetch("Kolar")
        assert evidence.places[0].latitude == payload["results"][0]["latitude"]
        assert evidence.data_status == "complete"
        payload.pop("results")
        empty = await client.fetch("Kolar")
        assert empty.places == ()
        assert empty.data_status == "empty"


@pytest.mark.asyncio
async def test_flood_preserves_values_and_unit_provenance():
    payload = recorded("flood")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as http:
        client = FloodClient(SourceTransport(http, source="Open-Meteo flood"))
        evidence = await client.fetch(LOCATION)
        assert evidence.daily.values["river_discharge"] == tuple(
            payload["daily"]["river_discharge"]
        )
        assert evidence.original_unit == payload["daily_units"]["river_discharge"]
        assert evidence.daily.units["river_discharge"] == "m³/s"
        payload["daily_units"]["river_discharge"] = "mm"
        with pytest.raises(SourceError) as error:
            await client.fetch(LOCATION)
        assert error.value.source == "Open-Meteo flood"
        assert error.value.code == "invalid_response"


@pytest.mark.asyncio
async def test_power_source_fill_values_remain_missing():
    payload = recorded("power")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as http:
        client = PowerClient(SourceTransport(http, source="NASA POWER"))
        evidence = await client.fetch(LOCATION, date(2026, 10, 15), date(2026, 10, 21))
        assert evidence.daily.values["T2M"] == tuple(
            payload["properties"]["parameter"]["T2M"].values()
        )
        assert all(v is None for v in evidence.daily.values["ALLSKY_SFC_SW_DWN"])
        assert evidence.data_status == "partial"
        assert evidence.service_version == payload["header"]["api"]["version"]
        for series in payload["properties"]["parameter"].values():
            series.pop("20261016")
        incomplete = await client.fetch(LOCATION, date(2026, 10, 15), date(2026, 10, 21))
        assert any("dates were not returned" in reason for reason in incomplete.missing_reasons)
        payload["header"]["time_standard"] = "LST"
        with pytest.raises(SourceError):
            await client.fetch(LOCATION, date(2026, 10, 15), date(2026, 10, 21))


@pytest.mark.asyncio
async def test_soil_nulls_and_returned_scale():
    payload = recorded("soil")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as http:
        client = SoilClient(SourceTransport(http, source="SoilGrids"))
        evidence = await client.fetch(LOCATION)
        assert evidence.data_status == "empty"
        assert all(p.value is None and p.mapped_value is None for p in evidence.properties)
        assert (
            evidence.properties[0].conversion_factor
            == payload["properties"]["layers"][0]["unit_measure"]["d_factor"]
        )
        payload["properties"]["layers"][0]["unit_measure"]["d_factor"] = 0
        with pytest.raises(SourceError):
            await client.fetch(LOCATION)


@pytest.mark.asyncio
async def test_mandi_without_key_never_contacts_source():
    def unexpected(request):
        raise AssertionError("No credential must mean no upstream request")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as http:
        transport = SourceTransport(http, source="Agmarknet")
        client = MandiClient(transport, None)
        with pytest.raises(SourceError) as error:
            await client.fetch("Kolar", "Tomato")
        assert error.value.code == "missing_api_key"
        assert error.value.source == "Agmarknet"
        assert transport.health.status == "unconfigured"
        assert transport.health.checked_at is None
        assert transport.request_count == 0


def test_source_provenance_does_not_publish_api_key():
    result = metadata(
        "agmarknet",
        "https://api.data.gov.in/resource",
        {"api-key": "not-a-credential", "limit": 10},
        "publisher",
        "https://data.gov.in",
        None,
        "Credential omitted.",
    )
    assert "not-a-credential" not in result["request_url"]
    assert "api-key" not in result["request_url"]


@pytest.mark.asyncio
async def test_health_reports_only_requested_sources(monkeypatch):
    monkeypatch.delenv("AGMARKNET_API_KEY", raising=False)
    app = create_app(
        httpx.MockTransport(lambda request: httpx.Response(200, json=recorded("geocoding")))
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as api:
            before = (await api.get("/health/sources")).json()["sources"]
            assert before["agmarknet"]["status"] == "unconfigured"
            assert all(value["request_count"] == 0 for value in before.values())
            result = await api.get("/v1/places?name=Kolar")
            assert result.status_code == 200
            after = (await api.get("/health/sources")).json()["sources"]
            assert after["open_meteo_geocoding"]["status"] == "available"
            assert after["open_meteo_geocoding"]["request_count"] == 1
            assert after["open_meteo_forecast"]["status"] == "unknown"
            await api.get("/v1/places?name=Kolar")
            assert (await api.get("/health/sources")).json()["sources"] == after
