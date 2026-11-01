import json
from datetime import datetime

import httpx
import pytest
from test_agent import recorded

from sowcast.agent.service import input_references
from sowcast.api.app import create_app
from sowcast.sources.models import Location


@pytest.mark.asyncio
async def test_unconfigured_plan_persists_bounded_inputs_version_and_latency():
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/plans",
                json=dict(latitude=13.14, longitude=78.13, crop="maize", sowing_status="not_sown"),
            )
            assert response.status_code == 200
            plan = response.json()
            trace = await app.state.traces.get_authorized(
                plan["trace_id"], plan["trace_access_token"]
            )
    assert trace["error"] == "provider_unconfigured"
    assert trace["rule_version"] == plan["rule_version"]
    assert trace["location"] == plan["location"]
    assert trace["latency_ms"] >= 0
    expected = [item for action in plan["actions"] for item in action["inputs"]]
    assert trace["input_reference_count"] == len(expected)
    assert len(trace["input_references"]) == min(64, len(expected))
    for actual, original in zip(trace["input_references"], expected):
        assert actual["field"] == original["field"]
        assert actual["value"] == original["value"]
        assert datetime.fromisoformat(actual["fetched_at"]) == datetime.fromisoformat(
            original["fetched_at"]
        )
    assert plan["trace_access_token"] not in json.dumps(trace)


@pytest.mark.asyncio
async def test_trace_references_keep_missing_values_and_strip_url_credentials():
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):
        from sowcast.agronomy.assessment import run_risk_assessment

        evidence = await app.state.weather.get(Location(latitude=13.14, longitude=78.13))
        plan = run_risk_assessment(evidence, "maize", app.state.catalogue, "not_sown")
        plan.actions[0].inputs[0].value = None
        plan.actions[0].inputs[0].request_url = "https://user:private@example.org/data?key=private"
        plan.actions = plan.actions * 100
        references = input_references(plan)
        assert len(references) == 64
        assert references[0]["value"] is None
        assert references[0]["source_url"] == "https://example.org/data"
        assert "private" not in json.dumps(references)
        enriched, answer = await app.state.agent.explain_plan(plan, "en")
        trace = await app.state.traces.get_authorized(answer.trace_id, answer.trace_access_token)
        assert trace["input_reference_count"] > len(trace["input_references"])
        assert len(json.dumps(trace).encode()) < 64000
        assert enriched.trace_id == answer.trace_id
