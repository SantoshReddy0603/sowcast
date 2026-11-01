import asyncio
import json
from pathlib import Path

import httpx
import pytest

from sowcast.cache.forecast import ForecastCache
from sowcast.sources.forecast import ForecastClient
from sowcast.sources.models import Location, SourceError
from sowcast.sources.transport import SourceTransport

RECORDING = Path(__file__).parent / "recorded" / "forecast.json"
LOCATION = Location(latitude=12.97, longitude=77.59)


def recorded() -> dict:
    return json.loads(RECORDING.read_text(encoding="utf-8-sig"))


@pytest.mark.asyncio
async def test_recorded_forecast_and_provenance():
    def respond(request):
        assert request.url.params["forecast_days"] == "14"
        assert request.url.params["timeformat"] == "unixtime"
        return httpx.Response(200, json=recorded())

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        transport = SourceTransport(http)
        assert transport.health.status == "unknown"
        result = await ForecastClient(transport).fetch(LOCATION)
        assert len(result.daily.time) == 14
        assert result.hourly.units["temperature_2m"] == "°C"
        assert result.fetched_at.tzinfo is not None
        assert result.location == LOCATION
        assert not result.is_stale
        assert transport.health.status == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["units", "length", "empty", "missing", "null_units"])
async def test_bad_payload_rejected(damage):
    payload = recorded()
    if damage == "units":
        payload["daily_units"]["precipitation_sum"] = "inch"
    elif damage == "length":
        payload["daily"]["precipitation_sum"].pop()
    elif damage == "empty":
        payload["hourly"]["time"] = []
    elif damage == "null_units":
        payload["daily_units"] = None
    else:
        del payload["daily"]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as http:
        transport = SourceTransport(http)
        with pytest.raises(SourceError, match="schema"):
            await ForecastClient(transport).fetch(LOCATION)
        assert transport.health.status == "degraded"


@pytest.mark.asyncio
async def test_retry_and_circuit_breaker():
    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        transport = SourceTransport(http, attempts=2, failure_threshold=1)
        with pytest.raises(SourceError) as first:
            await transport.get("https://api.open-meteo.com/v1/forecast", {})
        assert first.value.code == "http_503"
        assert calls == 2
        with pytest.raises(SourceError) as second:
            await transport.get("https://api.open-meteo.com/v1/forecast", {})
        assert second.value.code == "circuit_open"
        assert calls == 2


@pytest.mark.asyncio
async def test_auth_failure_not_retried():
    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(SourceError):
            await SourceTransport(http).get("https://api.open-meteo.com/v1/forecast", {})
        assert calls == 1


@pytest.mark.asyncio
async def test_network_timeout_is_typed_and_circuit_recovers():
    failing = True

    def respond(request):
        if failing:
            raise httpx.ReadTimeout("Timeout", request=request)
        return httpx.Response(200, json=recorded())

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        transport = SourceTransport(http, attempts=1, failure_threshold=1, cooldown=0)
        source = ForecastClient(transport)
        with pytest.raises(SourceError) as error:
            await source.fetch(LOCATION)
        assert error.value.code == "network_error"
        assert transport.health.status == "unavailable"
        failing = False
        await source.fetch(LOCATION)
        assert transport.health.status == "available"
        assert transport.opened_at is None


@pytest.mark.asyncio
async def test_cache_returns_isolated_data_and_bounds_capacity():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())),
    ) as http:
        source = ForecastClient(SourceTransport(http))
        cache = ForecastCache(source.fetch, capacity=1)
        first = await cache.get(LOCATION)
        first.hourly.units.clear()
        assert (await cache.get(LOCATION)).hourly.units
        other = Location(latitude=13, longitude=78)
        await cache.get(other)
        assert len(cache.entries) == 1
        assert (other.latitude, other.longitude) in cache.entries
        await cache.close()


@pytest.mark.asyncio
async def test_cache_coalesces_refresh_preserves_timestamp_and_expires():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())),
    ) as http:
        source = ForecastClient(SourceTransport(http))
        now = [0.0]
        calls = 0
        fail = False

        async def fetch(location):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)
            if fail:
                raise SourceError("network_error", "Unavailable", True)
            return await source.fetch(location)

        cache = ForecastCache(fetch, ttl=10, stale_for=20, clock=lambda: now[0])
        first, second = await asyncio.gather(cache.get(LOCATION), cache.get(LOCATION))
        assert calls == 1
        assert first == second
        assert not (await cache.get(LOCATION)).is_stale
        now[0] = 11
        fail = True
        stale = await cache.get(LOCATION)
        assert stale.is_stale
        assert stale.fetched_at == first.fetched_at
        await asyncio.gather(*list(cache.pending.values()), return_exceptions=True)
        assert cache.last_error.code == "network_error"
        now[0] = 31
        with pytest.raises(SourceError):
            await cache.get(LOCATION)
        await cache.close()


@pytest.mark.parametrize("latitude,longitude", [(91, 0), (0, 181), (float("nan"), 0)])
def test_invalid_coordinates(latitude, longitude):
    with pytest.raises(ValueError):
        Location(latitude=latitude, longitude=longitude)


@pytest.mark.asyncio
async def test_missing_forecast_values_are_not_reported_complete():
    payload = recorded()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as http:
        source = ForecastClient(SourceTransport(http))
        payload["daily"]["precipitation_sum"][0] = None
        partial = await source.fetch(LOCATION)
        assert partial.data_status == "partial"
        assert partial.missing_reasons
        for section in ("hourly", "daily"):
            for field, values in payload[section].items():
                if field != "time":
                    payload[section][field] = [None] * len(values)
        empty = await source.fetch(LOCATION)
        assert empty.data_status == "empty"
        assert source.transport.health.status == "degraded"
        assert source.transport.health.error_code == "empty_data"


@pytest.mark.asyncio
async def test_truncated_forecast_is_partial_not_a_complete_horizon():
    payload = recorded()
    for section in ("hourly", "daily"):
        for field, values in payload[section].items():
            payload[section][field] = values[: len(values) // 2]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as http:
        source = ForecastClient(SourceTransport(http))
        evidence = await source.fetch(LOCATION)
        assert evidence.data_status == "partial"
        assert "coverage is incomplete" in evidence.missing_reasons[0]
        assert len(evidence.daily.time) == len(payload["daily"]["time"])
        assert source.transport.health.status == "degraded"
