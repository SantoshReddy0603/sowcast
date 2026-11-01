import asyncio

import httpx
import pytest

from sowcast.api.app import create_app
from sowcast.api.limits import RateLimiter


def test_sliding_window_and_shared_agent_budget(monkeypatch):
    monkeypatch.setenv("SOWCAST_RATE_LIMIT", "100")
    monkeypatch.setenv("SOWCAST_AGENT_LIMIT", "2")
    monkeypatch.setenv("SOWCAST_AGENT_GLOBAL_LIMIT", "3")
    now = [0.0]
    limiter = RateLimiter(lambda: now[0])
    assert limiter.check("a", "/v1/plans") is None
    assert limiter.check("a", "/v1/chat") is None
    assert limiter.check("a", "/v1/chat") == 60
    assert limiter.check("b", "/v1/chat") is None
    assert limiter.check("c", "/v1/chat") == 60
    now[0] = 60
    assert limiter.check("a", "/v1/chat") is None


@pytest.mark.asyncio
async def test_envelope_cors_and_concurrent_budget(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://example.org")
    monkeypatch.setenv("SOWCAST_RATE_LIMIT", "2")
    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            headers = {"Origin": "https://example.org"}
            preflight = await http.options(
                "/v1/plans",
                headers=headers
                | {
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert preflight.status_code == 200
            results = await asyncio.gather(
                *(http.get("/health/sources", headers=headers) for _ in range(3))
            )
            assert sorted(r.status_code for r in results) == [200, 200, 429]
            limited = next(r for r in results if r.status_code == 429)
            assert limited.headers["access-control-allow-origin"] == "https://example.org"
            assert 1 <= int(limited.headers["retry-after"]) <= 60
            error = limited.json()["error"]
            assert error["code"] == "rate_limited" and error["retryable"] is True
            assert error["request_id"] == limited.headers["x-request-id"]
            assert (await http.get("/health")).status_code == 200
            assert (await http.get("/ready")).status_code == 429
            denied = await http.options(
                "/v1/plans",
                headers={"Origin": "https://other.org", "Access-Control-Request-Method": "POST"},
            )
            assert "access-control-allow-origin" not in denied.headers


@pytest.mark.asyncio
async def test_expensive_routes_limit_before_work(monkeypatch):
    monkeypatch.setenv("SOWCAST_BACKTEST_LIMIT", "1")
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.limiter.check("127.0.0.1", "/v1/backtests")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            response = await http.get(
                "/v1/backtests?latitude=12&longitude=77", headers={"X-Forwarded-For": "other"}
            )
            assert response.status_code == 429
            assert all(h.request_count == 0 for h in app.state.sources.health().values())


@pytest.mark.parametrize("route", ["/v1/plans", "/v1/chat", "/v1/backtests", "/v1/climate-normals"])
def test_expensive_budgets_are_isolated(monkeypatch, route):
    for name in (
        "AGENT",
        "AGENT_GLOBAL",
        "BACKTEST",
        "BACKTEST_GLOBAL",
        "CLIMATE",
        "CLIMATE_GLOBAL",
    ):
        monkeypatch.setenv("SOWCAST_" + name + "_LIMIT", "1")
    limiter = RateLimiter(lambda: 0.0)
    assert limiter.check("a", route) is None
    assert limiter.check("a", route) == 60
    assert limiter.check("b", route) == 60
    for other in ("/v1/plans", "/v1/backtests", "/v1/climate-normals"):
        if (other.startswith("/v1/plans") and route in {"/v1/plans", "/v1/chat"}) or other == route:
            continue
        assert limiter.check("a", other) is None


@pytest.mark.parametrize("route", ["/v1/plans", "/v1/backtests", "/v1/climate-normals"])
def test_general_budget_still_bounds_all_routes(monkeypatch, route):
    monkeypatch.setenv("SOWCAST_RATE_LIMIT", "1")
    limiter = RateLimiter(lambda: 0.0)
    assert limiter.check("a", "/health/sources") is None
    assert limiter.check("a", route) == 60
