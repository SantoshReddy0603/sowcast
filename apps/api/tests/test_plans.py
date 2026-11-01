import json
import math
from datetime import UTC, date, datetime, time, timedelta
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
                    "latitude": 13.14,
                    "longitude": 78.13,
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
            Location(latitude=13.14, longitude=78.13),
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
@pytest.mark.parametrize("crop", ["ragi", "paddy", "maize", "tur", "groundnut", "tomato"])
async def test_unsown_crop_has_weather_reviews_not_crop_water_tasks(crop):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=recorded()))
    ) as http:
        evidence = await ForecastClient(SourceTransport(http)).fetch(
            Location(latitude=13.14, longitude=78.13)
        )
    plan = run_risk_assessment(evidence, crop, load_catalogue(), "not_sown")
    assert all(action.kind == "review_evidence" for action in plan.actions)
    assert all("not yet sown" in action.reason for action in plan.actions)
    assert all("not a safe-to-sow recommendation" in action.reason for action in plan.actions)
    assert all(action.water_balance.crop_et_mm.value is None for action in plan.actions)
    assert all("Confirm the stage" not in action.reason for action in plan.actions)


@pytest.mark.asyncio
@pytest.mark.parametrize("crop", ["ragi", "tur"])
async def test_unsupported_growing_crop_stays_weather_only(crop):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=recorded()))
    ) as http:
        evidence = await ForecastClient(SourceTransport(http)).fetch(
            Location(latitude=13.14, longitude=78.13)
        )
    plan = run_risk_assessment(evidence, crop, load_catalogue(), "growing")
    assert all(action.kind == "review_evidence" for action in plan.actions)
    assert all("crop water need cannot be assessed" in action.reason for action in plan.actions)
    assert all(action.water_balance.coefficient.value is None for action in plan.actions)


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
                    "latitude": 13.14,
                    "longitude": 78.13,
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
                    "latitude": 13.14,
                    "longitude": 78.13,
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
            Location(latitude=13.14, longitude=78.13),
        )
    for temperature, expected in [
        (threshold, "review_evidence"),
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
        if expected == "inspect_heat_exposure":
            assert "not calibrated" in plan.actions[0].reason
        assert plan.actions[0].inputs[1].value == temperature
        assert plan.actions[0].citations[0].url.endswith("#page=68")
        other_stage = run_risk_assessment(boundary_evidence, "paddy", catalogue, "growing", "other")
        assert other_stage.actions[0].kind == "review_evidence"


def reliability_upstream(request):
    if request.url.host.startswith("previous-runs"):
        name = "previous_runs"
    elif request.url.host.startswith("archive"):
        name = "era5"
    else:
        return httpx.Response(200, json=recorded())
    path = Path(__file__).parent / f"recorded/{name}.json"
    return httpx.Response(200, json=json.loads(path.read_text(encoding="utf-8-sig")))


PLAN_BODY = {
    "latitude": 13.14,
    "longitude": 78.13,
    "crop": "ragi",
    "sowing_status": "growing",
    "growth_stage": "flowering",
}


@pytest.mark.asyncio
async def test_plan_carries_cached_backtest_sentences_only_when_stored():
    meta = json.loads(
        (Path(__file__).parent / "recorded/previous_runs.meta.json").read_text(encoding="utf-8")
    )
    now = datetime.combine(date.fromisoformat(meta["end_date"]) + timedelta(days=6), time(), UTC)
    calls = []

    def upstream(request):
        calls.append(request.url.host)
        return reliability_upstream(request)

    app = create_app(httpx.MockTransport(upstream))
    async with app.router.lifespan_context(app):
        app.state.sources.backtest.clock = lambda: now
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            before = await client.post("/v1/plans", json=PLAN_BODY)
            assert before.status_code == 200
            assert before.json()["forecast_reliability"] == []
            assert not any(host.startswith(("previous-runs", "archive")) for host in calls)
            backtest = await client.get("/v1/backtests?latitude=13.14&longitude=78.13")
            assert backtest.status_code == 200
            after = await client.post("/v1/plans", json=PLAN_BODY)
            sentences = after.json()["forecast_reliability"]
            assert sentences and len(sentences) <= 7
            assert all("GFS model" in line and "ERA5" in line for line in sentences)
            assert all("different model from the plan forecast" in line for line in sentences)


@pytest.mark.asyncio
async def test_reliability_leads_follow_dates_when_forecast_is_a_day_old():
    meta = json.loads(
        (Path(__file__).parent / "recorded/previous_runs.meta.json").read_text(encoding="utf-8")
    )
    now = datetime.combine(date.fromisoformat(meta["end_date"]) + timedelta(days=6), time(), UTC)

    def upstream(request):
        if request.url.host.startswith(("previous-runs", "archive")):
            return reliability_upstream(request)
        body = recorded()
        body["daily"]["time"] = [moment - 86400 for moment in body["daily"]["time"]]
        return httpx.Response(200, json=body)

    app = create_app(httpx.MockTransport(upstream))
    async with app.router.lifespan_context(app):
        app.state.sources.backtest.clock = lambda: now
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (
                await client.get("/v1/backtests?latitude=13.14&longitude=78.13")
            ).status_code == 200
            response = await client.post("/v1/plans", json=PLAN_BODY)
            sentences = response.json()["forecast_reliability"]
            today = now.date()
            assert sentences
            assert not any(line.startswith(f"{today.isoformat()}:") for line in sentences)
            assert sentences[0].startswith(
                f"{(today + timedelta(days=1)).isoformat()}: GFS model 24h"
            )
