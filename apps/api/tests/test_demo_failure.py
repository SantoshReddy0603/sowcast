import httpx
import pytest

from sowcast.api.app import create_app
from sowcast.sources.services import SourceServices


@pytest.mark.asyncio
async def test_selected_source_fails_without_upstream_call(monkeypatch):
    monkeypatch.setenv("SOWCAST_UNAVAILABLE_SOURCE", "open_meteo_forecast")

    def reject(request):
        pytest.fail("Disabled source must not make an HTTP request")

    app = create_app(httpx.MockTransport(reject))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            response = await http.get("/v1/evidence/weather?latitude=12.97&longitude=77.59")
            assert response.status_code == 503
            error = response.json()["error"]
            assert error["code"] == "source_unavailable" and error["retryable"] is True
            assert error["source"] == "Open-Meteo forecast"
            assert error["request_id"] == response.headers["x-request-id"]
            assert "values" not in response.text and "Traceback" not in response.text
            health = (await http.get("/health/sources")).json()["sources"]
            assert health["open_meteo_forecast"]["status"] == "unavailable"
            assert health["open_meteo_forecast"]["request_count"] == 0
            assert health["open_meteo_flood"]["status"] == "unknown"


@pytest.mark.asyncio
async def test_invalid_switch_rejected_and_default_off(monkeypatch):
    async with httpx.AsyncClient() as http:
        monkeypatch.setenv("SOWCAST_UNAVAILABLE_SOURCE", "unrecognized")
        with pytest.raises(ValueError, match="source identifier"):
            SourceServices(http, None)
        monkeypatch.delenv("SOWCAST_UNAVAILABLE_SOURCE")
        sources = SourceServices(http, None)
        assert not any(t.unavailable for t in sources.transports.values())
        await sources.close()


@pytest.mark.asyncio
async def test_readiness_and_production_database_requirement(monkeypatch):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            assert (await http.get("/ready")).json() == {"status": "ready"}
    monkeypatch.setenv("SOWCAST_ENV", "production")
    production = create_app()
    with pytest.raises(ValueError, match="hosted PostgreSQL"):
        async with production.router.lifespan_context(production):
            pass


@pytest.mark.asyncio
async def test_storage_failure_envelope_hides_driver_details(monkeypatch):
    from sqlalchemy.exc import OperationalError

    app = create_app()
    async with app.router.lifespan_context(app):

        async def failure():
            raise OperationalError("secret query", {}, RuntimeError("private credentials"))

        monkeypatch.setattr(app.state.traces.database, "ready", failure)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            response = await http.get("/ready")
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "storage_unavailable"
            assert "private" not in response.text and "secret" not in response.text


@pytest.mark.asyncio
async def test_real_refused_postgres_connection_uses_error_envelope():
    from types import SimpleNamespace

    from sowcast.storage.database import Database

    app = create_app()
    database = Database("postgresql+asyncpg://sowcast:unused@127.0.0.1:1/sowcast")
    database.initialized = True
    app.state.traces = SimpleNamespace(database=database)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as http:
        response = await http.get("/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "storage_unavailable"
        assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
        assert response.json()["error"]["retryable"] is True
        assert "unused" not in response.text and "127.0.0.1" not in response.text
    await database.close()
