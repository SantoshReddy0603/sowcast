import asyncio
import json

import httpx
import pytest
from test_agent import recorded

from sowcast.agent.provider import GeminiProvider, ProviderError, RequestBudget
from sowcast.api.app import create_app


@pytest.mark.asyncio
@pytest.mark.parametrize("path,limit", [("/v1/plans", 2), ("/v1/chat", 6)])
async def test_retry_and_regeneration_share_wire_budget(monkeypatch, path, limit):
    monkeypatch.setenv("GEMINI_API_KEY", "test-credential")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")

    async def no_wait(seconds):
        pass

    monkeypatch.setattr("sowcast.agent.provider.asyncio.sleep", no_wait)
    calls = []

    def upstream(request):
        if request.url.host != "generativelanguage.googleapis.com":
            return httpx.Response(200, json=recorded())
        calls.append(request)
        if len(calls) % 2 == 0:
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": json.dumps({"unknown": True})}]},
                    }
                ]
            },
        )

    app = create_app(httpx.MockTransport(upstream))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            plot = dict(latitude=13.14, longitude=78.13, crop="maize", sowing_status="not_sown")
            body = plot if path == "/v1/plans" else dict(question="Check evidence", plot=plot)
            response = await client.post(path, json=body)
            assert response.status_code == 200
            result = response.json()
            trace = await app.state.traces.get_authorized(
                result["trace_id"], result["trace_access_token"]
            )
    assert trace["provider_request_limit"] == limit
    assert trace["provider_requests"] == len(calls) <= limit
    assert len(calls) == (2 if path == "/v1/plans" else 3)
    assert trace["error"] == ("provider_request_limit" if limit == 2 else "invalid_draft")


@pytest.mark.asyncio
async def test_retry_checks_budget_before_second_http_request(monkeypatch):
    async def no_wait(seconds):
        pass

    monkeypatch.setattr("sowcast.agent.provider.asyncio.sleep", no_wait)
    calls = []

    def upstream(request):
        calls.append(request)
        return httpx.Response(429)

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as http:
        with pytest.raises(ProviderError, match="provider_request_limit"):
            await GeminiProvider(http, "test", "test-model").generate([], {}, RequestBudget(1))
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_independent_concurrent_budgets_count_each_wire_request():
    calls = []

    def upstream(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "{}"}]}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as http:
        provider = GeminiProvider(http, "test", "test-model")
        first, second = RequestBudget(1), RequestBudget(1)
        await asyncio.gather(provider.generate([], {}, first), provider.generate([], {}, second))
        with pytest.raises(ProviderError, match="provider_request_limit"):
            await provider.generate([], {}, first)
    assert first.used == second.used == 1
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_chat_retries_across_iterations_stop_at_six(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-credential")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    now = [0.0]

    async def no_wait(seconds):
        now[0] += seconds + 1

    monkeypatch.setattr("sowcast.agent.provider.asyncio.sleep", no_wait)
    calls = []

    def upstream(request):
        if request.url.host != "generativelanguage.googleapis.com":
            return httpx.Response(200, json=recorded())
        calls.append(request)
        if len(calls) % 2:
            return httpx.Response(429)
        draft = {"tools": [{"name": "get_forecast"}]}
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(draft)}]}}
                ]
            },
        )

    app = create_app(httpx.MockTransport(upstream))
    async with app.router.lifespan_context(app):
        app.state.agent.provider.clock = lambda: now[0]
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/chat",
                json={
                    "question": "Check evidence",
                    "plot": dict(
                        latitude=13.14, longitude=78.13, crop="maize", sowing_status="not_sown"
                    ),
                },
            )
            assert response.status_code == 200
            result = response.json()
            trace = await app.state.traces.get_authorized(
                result["trace_id"], result["trace_access_token"]
            )
    assert len(calls) == trace["provider_requests"] == trace["provider_request_limit"] == 6
    assert trace["error"] == "provider_request_limit"
    assert result["status"] == "unavailable" and result["claims"] == []


def stop_response():
    return httpx.Response(
        200,
        json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "{}"}]}}]},
    )


def truncated_response(reason):
    return httpx.Response(200, json={"candidates": [{"finishReason": reason}]})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first",
    [lambda: httpx.Response(503), lambda: truncated_response("MAX_TOKENS")],
)
async def test_transient_failure_is_retried_once_inside_budget(monkeypatch, first):
    async def no_wait(seconds):
        pass

    monkeypatch.setattr("sowcast.agent.provider.asyncio.sleep", no_wait)
    replies = [first, stop_response]
    calls = []

    def upstream(request):
        calls.append(request)
        return replies[len(calls) - 1]()

    budget = RequestBudget(2)
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as http:
        result = await GeminiProvider(http, "test", "test-model").generate([], {}, budget)
    assert result == {}
    assert len(calls) == budget.used == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply,code,expected_calls",
    [
        (lambda: httpx.Response(502), "provider_request_failed", 2),
        (lambda: truncated_response("MAX_TOKENS"), "provider_incomplete_response", 2),
        (lambda: truncated_response("SAFETY"), "provider_incomplete_response", 1),
    ],
)
async def test_transient_failure_is_not_retried_twice_or_when_blocked(
    monkeypatch, reply, code, expected_calls
):
    async def no_wait(seconds):
        pass

    monkeypatch.setattr("sowcast.agent.provider.asyncio.sleep", no_wait)
    calls = []

    def upstream(request):
        calls.append(request)
        return reply()

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as http:
        with pytest.raises(ProviderError) as error:
            await GeminiProvider(http, "test", "test-model").generate([], {}, RequestBudget(6))
    assert error.value.code == code
    assert len(calls) == expected_calls
