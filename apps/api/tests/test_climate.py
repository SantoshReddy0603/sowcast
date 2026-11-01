import asyncio
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from sowcast.api.app import create_app
from sowcast.api.limits import RateLimiter
from sowcast.sources.climate import ClimateClient, aggregate
from sowcast.sources.models import Location, SourceError
from sowcast.sources.transport import SourceTransport

LOCATION = Location(latitude=13.14, longitude=78.13)


def recorded():
    return json.loads((Path(__file__).parent / "recorded/climate.json").read_text(encoding="utf-8"))


def test_complete_calendar_means_and_leap_day_counts():
    payload = recorded()
    result = aggregate(payload, LOCATION, {})
    assert result.data_status == "complete" and len(result.days) == 366
    october = next(day for day in result.days if day.month_day == "10-31")
    expected = [
        payload["daily"]["precipitation_sum"][index]
        for index, stamp in enumerate(payload["daily"]["time"])
        if datetime.fromtimestamp(stamp, UTC).strftime("%m-%d") == "10-31"
    ]
    assert october.values["precipitation_sum"] == math.fsum(expected) / 30
    assert october.samples["precipitation_sum"] == october.expected_samples == 30
    leap = next(day for day in result.days if day.month_day == "02-29")
    assert leap.expected_samples == leap.samples["temperature_2m_min"] == 8
    assert result.days[0].month_day == "01-01" and result.days[-1].month_day == "12-31"
    assert result.grid_location != result.location


def test_incomplete_coverage_does_not_present_a_partial_mean_as_normal():
    payload = recorded()
    payload["daily"]["temperature_2m_min"][0] = None
    result = aggregate(payload, LOCATION, {})
    assert result.data_status == "partial"
    assert result.days[0].samples["temperature_2m_min"] == 29
    assert result.days[0].values["temperature_2m_min"] is None
    assert result.days[0].values["temperature_2m_max"] is not None
    for values in payload["daily"].values():
        values.pop(1)
    result = aggregate(payload, LOCATION, {})
    assert all(value is None for value in result.days[1].values.values())
    assert all(count == 29 for count in result.days[1].samples.values())


def test_no_values_produce_empty_baseline_without_zero_defaults():
    payload = recorded()
    for field in ("temperature_2m_min", "temperature_2m_max", "precipitation_sum"):
        payload["daily"][field] = [None] * len(payload["daily"]["time"])
    result = aggregate(payload, LOCATION, {})
    assert result.data_status == "empty"
    assert all(value is None for day in result.days for value in day.values.values())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "units",
        "duplicate",
        "non_midnight",
        "negative_rain",
        "offset",
        "range",
        "nonfinite",
        "reversed",
        "boolean",
        "numeric_string",
    ],
)
async def test_invalid_archive_data_is_a_typed_source_failure(case):
    payload = recorded()
    if case == "units":
        payload["daily_units"]["precipitation_sum"] = "inch"
    elif case == "duplicate":
        payload["daily"]["time"][1] = payload["daily"]["time"][0]
    elif case == "non_midnight":
        payload["daily"]["time"][0] += 3600
    elif case == "negative_rain":
        payload["daily"]["precipitation_sum"][0] = -1
    elif case == "offset":
        payload["utc_offset_seconds"] = 19800
    elif case == "range":
        payload["daily"]["time"][0] -= 86400
    elif case == "nonfinite":
        payload["daily"]["temperature_2m_min"][0] = float("inf")
    elif case == "boolean":
        payload["daily"]["temperature_2m_min"][0] = True
    elif case == "numeric_string":
        payload["daily"]["temperature_2m_min"][0] = "19.5"
    else:
        payload["daily"]["temperature_2m_min"][0] = 90
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=json.dumps(payload))
        )
    ) as http:
        with pytest.raises(SourceError) as error:
            await ClimateClient(SourceTransport(http)).fetch(LOCATION)
        assert error.value.code == "invalid_response"


@pytest.mark.asyncio
async def test_api_coalesces_and_caches_full_period_request():
    calls = []

    def upstream(request):
        calls.append(request)
        assert request.url.params["models"] == "era5"
        assert request.url.params["start_date"] == "1991-01-01"
        assert request.url.params["end_date"] == "2020-12-31"
        return httpx.Response(200, json=recorded())

    app = create_app(httpx.MockTransport(upstream))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            url = "/v1/climate-normals?latitude=13.14&longitude=78.13"
            first, second = await asyncio.gather(client.get(url), client.get(url))
            assert first.status_code == second.status_code == 200
            assert first.json() == second.json()
            assert (await client.get(url)).json() == first.json()
            assert len(calls) == 1
            assert len(first.json()["days"]) == 366
            assert (
                await client.get("/v1/climate-normals?latitude=nan&longitude=78")
            ).status_code == 422


def test_climate_route_has_independent_expensive_request_budget(monkeypatch):
    monkeypatch.setenv("SOWCAST_BACKTEST_LIMIT", "1")
    monkeypatch.setenv("SOWCAST_CLIMATE_LIMIT", "1")
    limiter = RateLimiter()
    assert limiter.check("plot", "/v1/climate-normals") is None
    assert limiter.check("plot", "/v1/backtests") is None
    assert limiter.check("plot", "/v1/backtests") is not None
    assert limiter.check("plot", "/v1/climate-normals") is not None


@pytest.mark.asyncio
async def test_archive_outage_does_not_block_weather_plan(monkeypatch):
    monkeypatch.setenv("SOWCAST_UNAVAILABLE_SOURCE", "open_meteo_archive")
    forecast = json.loads(
        (Path(__file__).parent / "recorded/forecast.json").read_text(encoding="utf-8-sig")
    )
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=forecast)))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/v1/climate-normals?latitude=13.14&longitude=78.13")
            assert response.status_code == 503
            assert response.json()["error"]["source"] == "Open-Meteo ERA5 archive"
            plan = await client.post(
                "/v1/plans",
                json={
                    "latitude": 13.14,
                    "longitude": 78.13,
                    "crop": "maize",
                    "sowing_status": "not_sown",
                },
            )
            assert plan.status_code == 200 and len(plan.json()["actions"]) == 14
            assert app.state.sources.health()["open_meteo_archive"].request_count == 0
