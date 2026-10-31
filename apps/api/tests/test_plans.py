import json
import math
from pathlib import Path

import httpx
import pytest

from sowcast.agronomy.assessment import run_risk_assessment
from sowcast.agronomy.catalogue import load_catalogue
from sowcast.api.app import create_app
from sowcast.sources.forecast import ForecastClient
from sowcast.sources.models import Location
from sowcast.sources.transport import SourceTransport


def recorded():
    return json.loads(
        (Path(__file__).parent / "recorded/forecast.json").read_text(encoding="utf-8-sig"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("crop", ["ragi", "paddy", "maize", "tur", "groundnut", "tomato"])
async def test_plan_api_recorded(crop):
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/plans",
                json={
                    "latitude": 12.97,
                    "longitude": 77.59,
                    "crop": crop,
                    "sowing_status": "growing",
                    "growth_stage": "flowering",
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert len(body["actions"]) == 14
            assert body["rule_version"] == load_catalogue().version
            assert body["evidence"]["attribution_text"]
            assert response.headers["X-Request-ID"]
            for action in body["actions"]:
                assert action["explanation"] is None
                assert action["rule_version"] == body["rule_version"]
                assert len(action["inputs"]) == 4
                assert action["metrics"]["growing_degree_days"]["status"] == "insufficient_data"
                assert action["metrics"]["waterlogging_risk"]["value"] is None


@pytest.mark.asyncio
async def test_missing_input_stale_and_stage_gate():
    payload = recorded()
    payload["daily"]["precipitation_sum"][0] = None
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as http:
        evidence = await ForecastClient(SourceTransport(http)).fetch(
            Location(latitude=12.97, longitude=77.59),
        )
    catalogue = load_catalogue()
    plan = run_risk_assessment(evidence, "paddy", catalogue, "growing")
    assert plan.actions[0].metrics["rainfall_deficit_against_et0"].status == "insufficient_data"
    assert plan.actions[0].metrics["heat_stress_days"].status == "insufficient_data"
    assert plan.actions[0].kind == "review_evidence"
    assert plan.actions[0].inputs[2].value is None
    stale = run_risk_assessment(
        evidence.model_copy(update={"is_stale": True}),
        "paddy",
        catalogue,
        "growing",
        "flowering",
    )
    assert all(action.kind == "review_evidence" for action in stale.actions)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"crop": "unknown", "sowing_status": "growing"},
        {"crop": "paddy", "sowing_status": "not_sown", "growth_stage": "flowering"},
    ],
)
async def test_invalid_plan_input_never_calls_upstream(body):
    def unexpected(request):
        raise AssertionError("Invalid plan should not fetch")

    app = create_app(httpx.MockTransport(unexpected))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/plans",
                json={
                    "latitude": 12.97,
                    "longitude": 77.59,
                    **body,
                },
            )
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_plan_source_failure_is_explicit():
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(401)))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/plans",
                json={
                    "latitude": 12.97,
                    "longitude": 77.59,
                    "crop": "maize",
                    "sowing_status": "not_sown",
                },
            )
            assert response.status_code == 503
            assert "actions" not in response.json()
            assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_heat_action_follows_threshold_and_stage():
    catalogue = load_catalogue()
    threshold = float(catalogue.crops["paddy"]["heat_above_c"].value)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())),
    ) as http:
        evidence = await ForecastClient(SourceTransport(http)).fetch(
            Location(latitude=12.97, longitude=77.59),
        )
    for temperature, expected in [
        (threshold, "review_water_balance"),
        (math.nextafter(threshold, math.inf), "inspect_heat_exposure"),
    ]:
        values = dict(evidence.daily.values)
        values["temperature_2m_max"] = (temperature, *values["temperature_2m_max"][1:])
        boundary_evidence = evidence.model_copy(
            update={
                "daily": evidence.daily.model_copy(update={"values": values}),
            }
        )
        plan = run_risk_assessment(boundary_evidence, "paddy", catalogue, "growing", "flowering")
        assert plan.actions[0].kind == expected
        assert plan.actions[0].inputs[1].value == temperature
        assert plan.actions[0].citations[0].url.endswith("#page=68")
        other_stage = run_risk_assessment(boundary_evidence, "paddy", catalogue, "growing", "other")
        assert other_stage.actions[0].kind == "review_water_balance"
