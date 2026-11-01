import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from sowcast.api.app import create_app


@pytest.mark.asyncio
async def test_weather_evidence_and_cache():
    payload = json.loads(
        (Path(__file__).parent / "recorded/forecast.json").read_text(encoding="utf-8-sig"),
    )
    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        assert request.url.host == "api.open-meteo.com"
        return httpx.Response(200, json=payload)

    app = create_app(httpx.MockTransport(respond))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            health = await client.get("/health")
            assert health.json() == {"status": "ok"}
            assert calls == 0
            first = await client.get("/v1/evidence/weather?latitude=12.97&longitude=77.59")
            second = await client.get("/v1/evidence/weather?latitude=12.97&longitude=77.59")
            assert first.status_code == 200
            assert first.json() == second.json()
            assert calls == 1
            body = first.json()
            assert body["attribution_text"] == "Weather data by Open-Meteo.com"
            assert body["licence_url"] == "https://creativecommons.org/licenses/by/4.0/"
            assert (
                body["daily"]["values"]["precipitation_sum"]
                == payload["daily"]["precipitation_sum"]
            )
            assert body["is_stale"] is False
            UUID(first.headers["X-Request-ID"])
            assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_source_failure_envelope():
    def respond(request):
        raise httpx.ConnectError("Private upstream details", request=request)

    app = create_app(httpx.MockTransport(respond))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/v1/evidence/weather?latitude=12.97&longitude=77.59")
            assert response.status_code == 503
            assert response.json() == {
                "api_version": "1.0",
                "error": {
                    "code": "network_error",
                    "source": "Open-Meteo forecast",
                    "retryable": True,
                    "request_id": response.headers["X-Request-ID"],
                    "message": "Open-Meteo forecast: network error (retryable)",
                },
            }
            assert "Private" not in response.text
            assert "values" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["", "latitude=nan&longitude=0", "latitude=91&longitude=0"])
async def test_invalid_input_does_not_call_source(query):
    def unexpected(request):
        raise AssertionError("Invalid input must not call upstream")

    app = create_app(httpx.MockTransport(unexpected))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/v1/evidence/weather?{query}")
            assert response.status_code == 422
            error = response.json()["error"]
            assert error["request_id"] == response.headers["X-Request-ID"]
            assert error["retryable"] is False


def test_cli_error_envelope():
    from sowcast.sources.models import SourceError

    error = SourceError("network_error", "Source request failed", True).envelope("request")
    assert error.error.source == "Open-Meteo forecast"
    assert error.error.retryable is True
    assert error.error.request_id == "request"
    assert error.error.message == "Open-Meteo forecast: network error (retryable)"
