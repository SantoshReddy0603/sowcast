import json
from pathlib import Path

import httpx
import pytest

from sowcast.agent.provider import GeminiProvider, ProviderError, generation_schema
from sowcast.agent.service import AgentService, Draft, plan_facts
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
            plot = dict(latitude=13.14, longitude=78.13, crop="maize", sowing_status="not_sown")
            response = await client.post("/v1/plans", json=plot)
            assert response.status_code == 200
            plan = response.json()
            assert plan["actions"] and "unavailable" in plan["agent_note"]
            assert all(a["explanation_status"] == "unavailable" for a in plan["actions"])
            answer = (
                await client.post("/v1/chat", json=dict(question="What should I check?", plot=plot))
            ).json()
            assert answer["status"] == "unavailable" and answer["claims"] == []
            trace = (
                await client.get(
                    "/v1/traces/" + answer["trace_id"],
                    headers={"Authorization": "Bearer " + answer["trace_access_token"]},
                )
            ).json()["trace"]
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
            PlotContext(latitude=13.14, longitude=78.13, crop="maize", sowing_status="not_sown"),
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
@pytest.mark.parametrize(
    "model,thinking",
    [
        ("test-model", None),
        ("gemini-2.5-flash", {"thinkingBudget": 0}),
        ("gemini-2.5-pro", None),
        ("gemini-3.8-flash", None),
    ],
)
async def test_provider_uses_simpler_wire_schema_without_weakening_local_validation(
    model, thinking
):
    schema = Draft.model_json_schema()
    original = json.dumps(schema, sort_keys=True)

    def upstream(request):
        config = json.loads(request.content)["generationConfig"]
        assert config.get("thinkingConfig") == thinking
        wire_schema = config["responseJsonSchema"]
        assert "maxItems" not in json.dumps(wire_schema)
        assert "maxLength" not in json.dumps(wire_schema)
        assert wire_schema["$defs"]["Claim"]["required"] == schema["$defs"]["Claim"]["required"]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": '{"claims":[]}'}]},
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as http:
        assert await GeminiProvider(http, "test-credential", model).generate([], schema) == {
            "claims": []
        }
    assert json.dumps(schema, sort_keys=True) == original
    assert schema["properties"]["claims"]["maxItems"] == 30
    assert schema["$defs"]["Claim"]["properties"]["text"]["maxLength"] == 1200


def test_generation_schema_preserves_property_names_that_match_schema_keywords():
    schema = {
        "title": "Example",
        "type": "object",
        "properties": {
            "title": {"type": "string", "maxLength": 1200},
            "default": {"type": "array", "items": {"type": "string"}, "maxItems": 30},
        },
    }
    wire = generation_schema(schema)
    assert "title" not in wire
    assert wire["properties"]["title"] == {"type": "string"}
    assert wire["properties"]["default"] == {"type": "array", "items": {"type": "string"}}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,payload,code",
    [
        (400, {"error": {"details": [{"reason": "API_KEY_INVALID"}]}}, "provider_invalid_api_key"),
        (
            400,
            {"error": {"message": "API key not valid. Please pass a valid API key."}},
            "provider_invalid_api_key",
        ),
        (
            400,
            {"error": {"message": "API key expired. Please renew the API key."}},
            "provider_expired_api_key",
        ),
        (
            403,
            {"error": {"message": "Your API key was reported as leaked."}},
            "provider_key_revoked",
        ),
        (403, {"error": {"details": [{"reason": "SERVICE_DISABLED"}]}}, "provider_api_disabled"),
        (
            403,
            {"error": {"details": [{"reason": "API_KEY_SERVICE_BLOCKED"}]}},
            "provider_key_restricted",
        ),
        (400, {"error": {"message": "private provider response"}}, "provider_invalid_request"),
        (
            401,
            {"error": {"details": [{"reason": "private provider response"}]}},
            "provider_authentication_failed",
        ),
        (
            403,
            {"error": {"details": [None, "private provider response"]}},
            "provider_access_denied",
        ),
        (404, {"error": None}, "provider_model_not_found"),
        (503, [], "provider_request_failed"),
    ],
)
async def test_provider_rejection_exposes_only_safe_codes(status, payload, code):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=payload))
    ) as http:
        with pytest.raises(ProviderError) as error:
            await GeminiProvider(http, "test-credential", "test-model").generate([], {})
        assert error.value.code == code
        assert error.value.http_status == status
        assert str(error.value) == code


@pytest.mark.asyncio
async def test_rejected_key_has_safe_plan_and_chat_traces(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-credential")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")

    def upstream(request):
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "private provider response test-credential",
                        "details": [{"reason": "API_KEY_INVALID"}],
                    }
                },
            )
        return httpx.Response(200, json=recorded())

    app = create_app(httpx.MockTransport(upstream))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            plot = dict(latitude=13.14, longitude=78.13, crop="maize", sowing_status="not_sown")
            plan_response = await client.post("/v1/plans", json=plot)
            chat_response = await client.post(
                "/v1/chat", json=dict(question="What should I check?", plot=plot)
            )
            for response in (plan_response, chat_response):
                assert response.status_code == 200
                result = response.json()
                actions = result.get("actions", result.get("plan", {}).get("actions", []))
                assert len(actions) == 14
                assert all(a["explanation_status"] == "unavailable" for a in actions)
                trace_response = await client.get(
                    "/v1/traces/" + result["trace_id"],
                    headers={"Authorization": "Bearer " + result["trace_access_token"]},
                )
                trace = trace_response.json()["trace"]
                assert trace["error"] == "provider_invalid_api_key"
                assert trace["provider_http_status"] == 400
                assert "private provider response" not in trace_response.text
                assert "test-credential" not in trace_response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "kn", "te"])
async def test_quota_failure_preserves_api_plan_and_chat(monkeypatch, language):
    monkeypatch.setenv("GEMINI_API_KEY", "test-credential")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    calls = []

    async def no_wait(seconds):
        assert seconds == 1

    monkeypatch.setattr("sowcast.agent.provider.asyncio.sleep", no_wait)

    def upstream(request):
        if request.url.host == "generativelanguage.googleapis.com":
            calls.append(request)
            return httpx.Response(429)
        return httpx.Response(200, json=recorded())

    app = create_app(httpx.MockTransport(upstream))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            plot = dict(
                latitude=13.14,
                longitude=78.13,
                crop="maize",
                sowing_status="growing",
                sowing_date="2026-10-01",
                language=language,
                agronomy_context={"district": "Kolar", "allow_fao_reference": True},
            )
            response = await client.post("/v1/plans", json=plot)
            assert response.status_code == 200
            plan = response.json()
            assert len(plan["actions"]) == 14
            assert "unavailable" in plan["agent_note"].lower()
            assert "quota limit" in plan["agent_note"].lower()
            assert all(a["explanation"] is None for a in plan["actions"])
            assert all(a["explanation_status"] == "unavailable" for a in plan["actions"])
            response = await client.post(
                "/v1/chat", json=dict(question="What should I check?", plot=plot, language=language)
            )
            assert response.status_code == 200
            answer = response.json()
            assert answer["status"] == "unavailable" and answer["claims"] == []
            assert "quota limit" in answer["note"].lower()
            assert answer["plan"]["actions"] == plan["actions"]
            for result in (plan, answer):
                trace_id = result["trace_id"]
                trace = (
                    await client.get(
                        "/v1/traces/" + trace_id,
                        headers={"Authorization": "Bearer " + result["trace_access_token"]},
                    )
                ).json()["trace"]
                assert trace["error"] == "provider_quota_exceeded"
                assert trace["guardrail"] == "not_run"
            assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", ["missing", "duplicate", "empty", "tools"])
async def test_plan_structure_rejection_has_actionable_trace(shape):
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):
        runner = ToolRunner(
            app.state.sources,
            app.state.catalogue,
            PlotContext(latitude=13.14, longitude=78.13, crop="maize", sowing_status="not_sown"),
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
        invalid = {
            "missing": {"claims": valid[:-1]},
            "duplicate": {"claims": valid + [valid[0]]},
            "empty": {"claims": []},
            "tools": {"claims": valid, "tools": [{"name": "get_forecast"}]},
        }[shape]

        class IncompleteDrafts:
            calls = 0

            async def generate(self, contents, schema, budget=None):
                self.calls += 1
                if self.calls % 2 == 0:
                    correction = json.loads(contents[-1]["parts"][0]["text"])["correction"]
                    expected = {
                        "missing": "Missing action dates:",
                        "duplicate": "Duplicate claim dates:",
                        "empty": "Cited claims required",
                        "tools": "Plan explanations cannot call tools",
                    }[shape]
                    assert any(expected in item for item in correction)
                return invalid

        provider = IncompleteDrafts()
        service = AgentService(provider, app.state.sources, app.state.catalogue, app.state.traces)
        for _ in range(2):
            enriched, answer = await service.explain_plan(plan.model_copy(deep=True), "en")
            assert answer.status == "unavailable"
            assert all(a.explanation is None for a in enriched.actions)
            trace = await app.state.traces.get(answer.trace_id)
            assert trace["error"] == "guardrail_rejected"
            assert trace["guardrail"]["passed"] is False
            assert trace["guardrail"]["discrepancies"]
            assert not trace["cache_hit"]
        assert provider.calls == 4


@pytest.mark.asyncio
async def test_regeneration_cache_and_foreign_day_rejection():
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):
        runner = ToolRunner(
            app.state.sources,
            app.state.catalogue,
            PlotContext(latitude=13.14, longitude=78.13, crop="maize", sowing_status="not_sown"),
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

            async def generate(self, contents, schema, budget=None):
                self.calls += 1
                if self.calls == 1:
                    return {"claims": [valid[0] | {"date": "1900-01-01"}]}
                return {"claims": valid}

        provider = AdversarialDrafts()
        service = AgentService(provider, app.state.sources, app.state.catalogue, app.state.traces)
        enriched, answer = await service.explain_plan(plan.model_copy(deep=True), "en")
        assert provider.calls == 2 and answer.status == "verified"
        assert all(a.explanation_status == "verified" for a in enriched.actions)
        _, cached_answer = await service.explain_plan(plan.model_copy(deep=True), "en")
        cached_trace = await app.state.traces.get(cached_answer.trace_id)
        assert cached_trace["cache_hit"]
        assert cached_trace["rule_version"] == plan.rule_version
        assert cached_trace["latency_ms"] >= 0
        assert cached_trace["input_references"]
        assert provider.calls == 2
        changed = plan.model_copy(deep=True)
        changed.actions[0].reason = "Changed rule action based on critical growth stage."
        await service.explain_plan(changed, "en")
        assert provider.calls == 3

        class RejectedDrafts:
            calls = 0

            async def generate(self, contents, schema, budget=None):
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

            async def generate(self, contents, schema, budget=None):
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
            PlotContext(latitude=13.14, longitude=78.13, crop="maize", sowing_status="not_sown"),
            "en",
        )
        assert answer.status == "verified" and provider.calls == 3
        assert answer.claims[0].evidence_id.startswith("get_forecast:")


@pytest.mark.asyncio
async def test_chat_prompts_carry_task_and_citing_instruction():
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):

        class Prompted:
            calls = 0

            async def generate(self, contents, schema, budget=None):
                self.calls += 1
                if self.calls == 1:
                    first = json.loads(contents[0]["parts"][0]["text"])
                    assert first["task"].strip()
                    return {"tools": [{"name": "get_forecast"}]}
                message = json.loads(contents[-1]["parts"][0]["text"])
                assert "Cite citable_facts" in message["instruction"]
                fact = message["tool_results"][0]["citable_facts"][0]
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

        provider = Prompted()
        service = AgentService(provider, app.state.sources, app.state.catalogue, app.state.traces)
        answer = await service.ask(
            "Explain this plot",
            PlotContext(latitude=13.14, longitude=78.13, crop="maize", sowing_status="not_sown"),
            "en",
        )
        assert answer.status == "verified" and provider.calls == 2


@pytest.mark.asyncio
async def test_sowing_timing_question_uses_several_tools_without_a_date():
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):

        class Timing:
            calls = 0

            async def generate(self, contents, schema, budget=None):
                self.calls += 1
                first = json.loads(contents[0]["parts"][0]["text"])
                if self.calls == 1:
                    assert "do not recommend a sowing date" in first["task"]
                    return {"tools": [{"name": "get_backtest"}]}
                fact = first["facts"][0]
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

        service = AgentService(Timing(), app.state.sources, app.state.catalogue, app.state.traces)
        answer = await service.ask(
            "When should I sow ragi?",
            PlotContext(latitude=13.14, longitude=78.13, crop="ragi", sowing_status="not_sown"),
            "en",
        )
        trace = await app.state.traces.get_authorized(answer.trace_id, answer.trace_access_token)
        assert [t["name"] for t in trace["tools"]] == [
            "get_forecast",
            "run_risk_assessment",
            "get_backtest",
        ]
        assert answer.status == "verified"
        assert "crop-water need is not estimated" in answer.plan.water_balance_availability


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

            async def generate(self, contents, schema, budget=None):
                self.calls += 1
                return {"tools": [{"name": "get_backtest"}] * width}

        provider = RepeatedTools()
        service = AgentService(provider, app.state.sources, app.state.catalogue, app.state.traces)
        answer = await service.ask(
            "Check",
            PlotContext(latitude=13.14, longitude=78.13, crop="maize", sowing_status="not_sown"),
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

            async def generate(self, contents, schema, budget=None):
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
            PlotContext(latitude=13.14, longitude=78.13, crop="maize", sowing_status="not_sown"),
            "en",
        )
        assert provider.calls == 2 and answer.status == "unavailable" and not answer.claims
        assert answer.plan.actions
        trace = await app.state.traces.get(answer.trace_id)
        assert trace["error"] == "guardrail_rejected"


@pytest.mark.asyncio
async def test_quota_cooldown_and_retry_after(monkeypatch):
    monkeypatch.setattr("sowcast.agent.provider.asyncio.sleep", _no_sleep)
    now = [100.0]
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"}, json={"error": {"code": 429}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = GeminiProvider(http, "test", "gemini-test", clock=lambda: now[0])
        for _ in range(3):
            with pytest.raises(ProviderError, match="provider_quota_exceeded"):
                await provider.generate([], {})
        assert len(calls) == 1
        now[0] += 121
        with pytest.raises(ProviderError):
            await provider.generate([], {})
        assert len(calls) == 2


async def _no_sleep(_seconds):
    pass


@pytest.mark.asyncio
async def test_trace_capability_access_delete_and_cors(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            plot = dict(latitude=13.14, longitude=78.13, crop="ragi", sowing_status="not_sown")
            first = (
                await client.post(
                    "/v1/chat", json={"question": "What should I check?", "plot": plot}
                )
            ).json()
            second = (
                await client.post(
                    "/v1/chat", json={"question": "What should I check?", "plot": plot}
                )
            ).json()
            path = "/v1/traces/" + first["trace_id"]
            owner = {"Authorization": "Bearer " + first["trace_access_token"]}
            other = {"Authorization": "Bearer " + second["trace_access_token"]}
            assert (await client.get(path)).status_code == 404
            assert (await client.get(path, headers=other)).status_code == 404
            result = await client.get(path, headers=owner)
            assert result.status_code == 200
            assert "access_digest" not in result.text
            assert first["trace_access_token"] not in result.text
            assert (await client.delete(path, headers=other)).status_code == 404
            assert (await client.delete(path, headers=owner)).status_code == 204
            assert (await client.get(path, headers=owner)).status_code == 404
            response = await client.options(
                path,
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "DELETE",
                    "Access-Control-Request-Headers": "authorization",
                },
            )
            assert response.status_code == 200


@pytest.mark.asyncio
async def test_trace_capability_restart_hash_and_legacy(tmp_path):
    from uuid import uuid4

    from sqlalchemy import select

    from sowcast.storage.models import AgentTrace

    path = str(tmp_path / "capabilities.sqlite3")
    identifier, legacy = str(uuid4()), str(uuid4())
    store = TraceStore(path)
    await store.save(identifier, {"guardrail": "passed"}, "owner-token")
    await store.save(legacy, {"guardrail": "passed"})
    async with store.database.transaction() as session:
        row = (
            await session.execute(select(AgentTrace).where(AgentTrace.id == identifier))
        ).scalar_one()
        assert "owner-token" not in row.body
    await store.close()
    reopened = TraceStore(path)
    assert await reopened.get_authorized(identifier, "owner-token") == {"guardrail": "passed"}
    assert await reopened.get_authorized(legacy, "owner-token") is None
    assert await reopened.get(legacy) == {"guardrail": "passed"}
    await reopened.close()


@pytest.mark.parametrize(
    "headers,body,expected",
    [
        ({"Retry-After": "3"}, {}, 3),
        ({"Retry-After": "-1"}, {}, None),
        ({"Retry-After": "NaN"}, {}, None),
        ({"Retry-After": "9999999"}, {}, 86400),
        (
            {},
            {
                "error": {
                    "details": [
                        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "90.5s"}
                    ]
                }
            },
            90.5,
        ),
        (
            {},
            {
                "error": {
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": "invalid",
                        }
                    ]
                }
            },
            None,
        ),
        ({}, {"error": "invalid"}, None),
    ],
)
def test_provider_retry_hints(headers, body, expected):
    from sowcast.agent.provider import retry_delay

    assert retry_delay(httpx.Response(429, headers=headers, json=body)) == expected


def test_provider_retry_http_date():
    from datetime import UTC, datetime, timedelta
    from email.utils import format_datetime

    from sowcast.agent.provider import retry_delay

    value = format_datetime(datetime.now(UTC) + timedelta(seconds=120), usegmt=True)
    delay = retry_delay(httpx.Response(429, headers={"Retry-After": value}, json={}))
    assert delay is not None and 118 < delay <= 120
