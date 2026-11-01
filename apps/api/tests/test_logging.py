import asyncio
import json

import httpx
import pytest
from test_agent import recorded

from sowcast.api.app import create_app
from sowcast.sources.models import SourceError
from sowcast.sources.transport import SourceTransport


@pytest.mark.asyncio
async def test_request_logs_correlate_sources_without_payloads_or_credentials(capsys):
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/plans?key=private-query",
                headers={"Authorization": "Bearer private-header", "X-Request-ID": "private-id"},
                json=dict(latitude=13.14, longitude=78.13, crop="maize", sowing_status="not_sown"),
            )
            unknown = await client.get("/private-path?password=private-query")
    logs = capsys.readouterr().err
    for sensitive in (
        "private-query",
        "private-header",
        "private-path",
        "private-id",
        "precipitation_sum",
        "latitude",
    ):
        assert sensitive not in logs
    records = [json.loads(line) for line in logs.splitlines()]
    request_id = response.headers["x-request-id"]
    correlated = [row for row in records if row.get("request_id") == request_id]
    assert any(
        row["event"] == "source_request" and row["source"] == "Open-Meteo forecast"
        for row in correlated
    )
    assert any(row.get("route") == "/v1/plans" and row["http_status"] == 200 for row in correlated)
    assert all(row["latency_ms"] >= 0 for row in correlated)
    assert any(
        row.get("request_id") == unknown.headers["x-request-id"] and row.get("route") == "unmatched"
        for row in records
    )


@pytest.mark.asyncio
async def test_concurrent_request_contexts_do_not_leak(capsys):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            responses = await asyncio.gather(client.get("/health"), client.get("/health"))
    records = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert {row["request_id"] for row in records} == {r.headers["x-request-id"] for r in responses}
    assert len(records) == 2


@pytest.mark.asyncio
async def test_unhandled_error_has_safe_envelope_and_no_exception_payload(capsys, monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://example.org")
    app = create_app()

    @app.get("/failing")
    async def failing():
        raise RuntimeError("private-payload")

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/failing", headers={"Origin": "https://example.org"})
    logs = capsys.readouterr().err
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "https://example.org"
    assert response.json()["error"]["code"] == "internal_error"
    assert "private-payload" not in logs + response.text
    record = json.loads(logs)
    assert record["http_status"] == 500 and record["request_id"] == response.headers["x-request-id"]


@pytest.mark.asyncio
async def test_source_retry_logs_only_safe_metadata(capsys):
    create_app()

    def fail(request):
        raise httpx.ConnectError("private-exception", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as http:
        with pytest.raises(SourceError):
            await SourceTransport(http, attempts=1).get(
                "https://example.org/private-path", {"key": "private-query"}
            )
    logs = capsys.readouterr().err
    assert "private" not in logs
    row = json.loads(logs)
    assert row["error_code"] == "network_error" and row["attempt"] == 1
    assert row["latency_ms"] >= 0


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["run", "run_backtest"])
async def test_cli_failure_envelope_matches_source_log_request_id(monkeypatch, capsys, command):
    from sowcast import __main__ as cli
    from sowcast.logging import configure_logging

    configure_logging()
    original = httpx.AsyncClient

    def fail(request):
        raise httpx.ConnectError("private-exception", request=request)

    monkeypatch.setattr(
        cli.httpx, "AsyncClient", lambda: original(transport=httpx.MockTransport(fail))
    )
    with pytest.raises(SystemExit) as error:
        await getattr(cli, command)(13.14, 78.13)
    assert error.value.code == 1
    output = capsys.readouterr()
    envelope = json.loads(output.out)
    records = [json.loads(line) for line in output.err.splitlines()]
    assert records
    assert all(record["request_id"] == envelope["error"]["request_id"] for record in records)
    assert "private-exception" not in output.err + output.out
