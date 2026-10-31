import json
from pathlib import Path

import httpx
import pytest

from sowcast.agent.provider import GeminiProvider, ProviderError
from sowcast.agent.service import AgentService, plan_facts
from sowcast.agent.tools import PlotContext, ToolCall, ToolRunner
from sowcast.api.app import create_app
from sowcast.guardrails.claims import Claim
from sowcast.storage.traces import TraceStore, redact


def recorded():
    return json.loads(
        (Path(__file__).parent / "recorded/forecast.json").read_text(encoding="utf-8-sig")
    )


@pytest.mark.asyncio
async def test_unconfigured_plan_chat_and_persisted_trace():
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            plot = dict(latitude=12.97, longitude=77.59, crop="maize", sowing_status="not_sown")
            response = await client.post("/v1/plans", json=plot)
            assert response.status_code == 200
            plan = response.json()
            assert plan["actions"] and "unavailable" in plan["agent_note"]
            assert all(a["explanation_status"] == "unavailable" for a in plan["actions"])
            answer = (
                await client.post("/v1/chat", json=dict(question="What should I check?", plot=plot))
            ).json()
            assert answer["status"] == "unavailable" and answer["claims"] == []
            trace = (await client.get("/v1/traces/" + answer["trace_id"])).json()["trace"]
            assert trace["error"] == "provider_unconfigured"
            assert [t["name"] for t in trace["tools"]] == ["get_forecast", "run_risk_assessment"]
            assert all(t["latency_ms"] >= 0 for t in trace["tools"])
            assert "What should I check?" not in json.dumps(trace)
            assert (await client.get("/v1/traces/not-a-uuid")).status_code == 422
            assert (
                await client.get("/v1/traces/00000000-0000-0000-0000-000000000000")
            ).status_code == 404


@pytest.mark.asyncio
async def test_tool_arguments_unavailable_and_timeout(monkeypatch):
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):
        runner = ToolRunner(
            app.state.sources,
            app.state.catalogue,
            PlotContext(latitude=12.97, longitude=77.59, crop="maize", sowing_status="not_sown"),
        )
        bad = await runner.execute(ToolCall(name="get_forecast", arguments={"latitude": "90"}))
        assert bad["code"] == "invalid_tool_arguments"
        assert (await runner.execute(ToolCall(name="get_backtest")))["code"] == "invalid_response"

        async def timeout(call):
            raise TimeoutError

        monkeypatch.setattr(runner, "_run", timeout)
        assert (await runner.execute(ToolCall(name="get_soil")))["code"] == "tool_timeout"


@pytest.mark.asyncio
async def test_provider_no_key_and_bounded_quota_retry(monkeypatch):
    calls = []

    async def no_wait(seconds):
        calls.append(seconds)

    monkeypatch.setattr("sowcast.agent.provider.asyncio.sleep", no_wait)

    def quota(request):
        assert request.headers["x-goog-api-key"] == "test-credential"
        return httpx.Response(429)

    async with httpx.AsyncClient(transport=httpx.MockTransport(quota)) as http:
        with pytest.raises(ProviderError, match="provider_unconfigured"):
            await GeminiProvider(http, None, None).generate([], {})
        with pytest.raises(ProviderError, match="provider_quota_exceeded"):
            await GeminiProvider(http, "test-credential", "test-model").generate([], {})
    assert calls == [1]


@pytest.mark.asyncio
async def test_regeneration_cache_and_foreign_day_rejection():
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):
        runner = ToolRunner(
            app.state.sources,
            app.state.catalogue,
            PlotContext(latitude=12.97, longitude=77.59, crop="maize", sowing_status="not_sown"),
        )
        await runner.execute(ToolCall(name="run_risk_assessment"))
        plan = runner.plan
        facts = plan_facts(plan)
        valid = []
        for action in plan.actions:
            fact = next(f for f in facts.values() if f.date == action.date.isoformat())
            valid.append(
                Claim(
                    text="Review the supplied field evidence.",
                    evidence_id=fact.id,
                    date=fact.date,
                    latitude=fact.latitude,
                    longitude=fact.longitude,
                ).model_dump()
            )

        class AdversarialDrafts:
            calls = 0

            async def generate(self, contents, schema):
                self.calls += 1
                if self.calls == 1:
                    return {"claims": [valid[0] | {"date": "1900-01-01"}]}
                return {"claims": valid}

        provider = AdversarialDrafts()
        service = AgentService(provider, app.state.sources, app.state.catalogue, app.state.traces)
        enriched, answer = await service.explain_plan(plan.model_copy(deep=True), "en")
        assert provider.calls == 2 and answer.status == "verified"
        assert all(a.explanation_status == "verified" for a in enriched.actions)
        await service.explain_plan(plan.model_copy(deep=True), "en")
        assert provider.calls == 2
        changed = plan.model_copy(deep=True)
        changed.actions[0].reason = "Changed rule action based on critical growth stage."
        await service.explain_plan(changed, "en")
        assert provider.calls == 3

        class RejectedDrafts:
            calls = 0

            async def generate(self, contents, schema):
                self.calls += 1
                return {"claims": [valid[0] | {"text": "999 mm"}]}

        rejected = RejectedDrafts()
        service.provider = rejected
        _, answer = await service.explain_plan(plan.model_copy(deep=True), "kn")
        assert rejected.calls == 2 and answer.status == "unavailable" and not answer.claims


@pytest.mark.asyncio
async def test_trace_redaction_size_and_persistence(tmp_path):
    path = str(tmp_path / "trace.sqlite3")
    store = TraceStore(path)
    await store.save(
        "one", {"api_key": "secret-value", "url": "https://example.org/?token=private"}
    )
    text = json.dumps(await TraceStore(path).get("one"))
    assert "secret-value" not in text and "private" not in text
    assert redact({"authorization": "secret"}) == {"authorization": "[redacted]"}
    with pytest.raises(ValueError, match="storage limit"):
        await store.save("huge", {"items": ["a" * 2000] * 40})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"candidates": [None]},
        {"candidates": []},
        {"candidates": [{"finishReason": "STOP", "content": {"parts": [None]}}]},
        [],
    ],
)
async def test_malformed_provider_is_typed_failure(payload):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as http:
        with pytest.raises(ProviderError, match="provider_invalid_response"):
            await GeminiProvider(http, "test-credential", "test-model").generate([], {})


@pytest.mark.asyncio
async def test_loop_registers_new_tool_facts_and_corrects_errors():
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):

        class ToolDrafts:
            calls = 0

            async def generate(self, contents, schema):
                self.calls += 1
                if self.calls == 1:
                    return {"tools": [{"name": "get_forecast", "arguments": {"latitude": "90"}}]}
                if self.calls == 2:
                    assert "invalid_tool_arguments" in contents[-1]["parts"][0]["text"]
                    return {"tools": [{"name": "get_forecast"}]}
                result = json.loads(contents[-1]["parts"][0]["text"])["tool_results"][0]
                fact = result["citable_facts"][0]
                return {
                    "claims": [
                        dict(
                            text="Review this forecast evidence.",
                            evidence_id=fact["id"],
                            date=fact["date"],
                            latitude=fact["latitude"],
                            longitude=fact["longitude"],
                        )
                    ]
                }

        provider = ToolDrafts()
        service = AgentService(provider, app.state.sources, app.state.catalogue, app.state.traces)
        answer = await service.ask(
            "Explain this plot",
            PlotContext(latitude=12.97, longitude=77.59, crop="maize", sowing_status="not_sown"),
            "en",
        )
        assert answer.status == "verified" and provider.calls == 3
        assert answer.claims[0].evidence_id.startswith("get_forecast:")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "width,expected_calls,code",
    [(1, 4, "iteration_budget_exhausted"), (6, 2, "tool_budget_exhausted")],
)
async def test_loop_budgets(width, expected_calls, code):
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):

        class RepeatedTools:
            calls = 0

            async def generate(self, contents, schema):
                self.calls += 1
                return {"tools": [{"name": "get_backtest"}] * width}

        provider = RepeatedTools()
        service = AgentService(provider, app.state.sources, app.state.catalogue, app.state.traces)
        answer = await service.ask(
            "Check",
            PlotContext(latitude=12.97, longitude=77.59, crop="maize", sowing_status="not_sown"),
            "en",
        )
        assert answer.status == "unavailable" and not answer.claims
        assert provider.calls == expected_calls
        trace = await app.state.traces.get(answer.trace_id)
        assert trace["error"] == code and len(trace["tools"]) <= 8


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "बीस लीटर सिंचाई करें",
        "ಇಪ್ಪತ್ತು ಲೀಟರ್",
        "ఇరవై లీటర్లు",
        "இருபது லிட்டர்",
        "वीस लिटर",
        "a dozen litres",
        "Ⅻ litres",
        "12.5 mm",
    ],
)
async def test_quantity_bypass_never_reaches_answer(text):
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):

        class QuantityDrafts:
            calls = 0

            async def generate(self, contents, schema):
                self.calls += 1
                initial = json.loads(contents[0]["parts"][0]["text"])
                assert initial["allowed_words"]
                fact = initial["facts"][0]
                return {
                    "claims": [
                        {
                            "text": text,
                            "evidence_id": fact["id"],
                            "date": fact["date"],
                            "latitude": fact["latitude"],
                            "longitude": fact["longitude"],
                        }
                    ]
                }

        provider = QuantityDrafts()
        service = AgentService(provider, app.state.sources, app.state.catalogue, app.state.traces)
        answer = await service.ask(
            "Explain",
            PlotContext(latitude=12.97, longitude=77.59, crop="maize", sowing_status="not_sown"),
            "en",
        )
        assert provider.calls == 2 and answer.status == "unavailable" and not answer.claims
        assert answer.plan.actions
        trace = await app.state.traces.get(answer.trace_id)
        assert trace["error"] == "guardrail_rejected"
