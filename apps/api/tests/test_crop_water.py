from datetime import date, timedelta

import httpx
import pytest
from test_plans import recorded

from sowcast.agronomy.catalogue import load_catalogue
from sowcast.agronomy.rules import available, insufficient
from sowcast.agronomy.water_balance import (
    AgronomyContext,
    coefficient_for_day,
    crop_water_balance,
)
from sowcast.api.app import create_app


@pytest.mark.parametrize(
    "crop,stage,value",
    [
        ("maize", "initial", 0.3),
        ("maize", "mid", 1.2),
        ("paddy", "initial", 1.05),
        ("paddy", "mid", 1.2),
        ("groundnut", "initial", 0.4),
        ("groundnut", "mid", 1.15),
        ("groundnut", "end", 0.6),
        ("tomato", "initial", 0.6),
        ("tomato", "mid", 1.15),
    ],
)
def test_every_enabled_coefficient_and_interval(crop, stage, value):
    parameters = load_catalogue().crops[crop]
    on = date(2026, 10, 30)
    context = AgronomyContext(
        district="Kolar",
        allow_fao_reference=True,
        water_stage=stage,
        stage_valid_from=on,
        stage_valid_until=on,
        paddy_standing_water=True,
        tomato_tall_staked=False,
    )
    result, selected, basis, citations = coefficient_for_day(crop, parameters, on, context)
    assert result.value == value
    assert selected == stage
    assert "Caller" in basis
    assert citations[0].number_as_written
    for outside in (on - timedelta(days=1), on + timedelta(days=1)):
        assert coefficient_for_day(crop, parameters, outside, context)[0].value is None
    for rain in range(10):
        previous = 0
        for et0 in range(10):
            need, shortfall = crop_water_balance(rain, et0, result)
            assert need.value == pytest.approx(value * et0)
            assert shortfall.value == pytest.approx(max(0, value * et0 - rain))
            assert shortfall.value >= previous
            previous = shortfall.value


def test_maize_duration_boundaries_and_interpolation():
    parameters = load_catalogue().crops["maize"]
    assert [parameters[f"days_{s}"].value for s in ("initial", "development", "mid", "late")] == [
        20,
        35,
        40,
        30,
    ]
    planting = date(2026, 10, 1)
    context = AgronomyContext(district="Kolar", allow_fao_reference=True, planting_date=planting)
    for day, stage, expected in [
        (1, "initial", 0.3),
        (20, "initial", 0.3),
        (21, "development", 0.3 + 0.9 / 35),
        (55, "development", 1.2),
        (56, "mid", 1.2),
        (95, "mid", 1.2),
        (96, "late", None),
        (125, "late", None),
    ]:
        result, selected, _, _ = coefficient_for_day(
            "maize",
            parameters,
            planting + timedelta(days=day - 1),
            context,
        )
        assert selected == stage
        if expected is None:
            assert result.status == "insufficient_data"
        else:
            assert result.value == pytest.approx(expected)
    for day in (0, 126):
        assert (
            coefficient_for_day(
                "maize",
                parameters,
                planting + timedelta(days=day - 1),
                context,
            )[0].value
            is None
        )
    wrong_month = context.model_copy(update={"planting_date": date(2026, 6, 1)})
    assert coefficient_for_day("maize", parameters, planting, wrong_month)[0].value is None


@pytest.mark.parametrize(
    "rain,et0,kc",
    [
        (None, 4, available(1.2, "dimensionless", "test")),
        (2, None, available(1.2, "dimensionless", "test")),
        (2, 4, insufficient("dimensionless", "missing")),
    ],
)
def test_missing_water_inputs(rain, et0, kc):
    assert all(result.status == "insufficient_data" for result in crop_water_balance(rain, et0, kc))


def test_invalid_water_inputs():
    for rain, et0, kc in [(-1, 2, 1), (1, float("nan"), 1), (1, 2, -1)]:
        need, shortfall = crop_water_balance(rain, et0, available(kc, "dimensionless", "test"))
        assert need.value is None
        assert shortfall.value is None


def test_reference_permission_and_management_conditions():
    on = date(2026, 10, 30)
    catalogue = load_catalogue()
    for crop, stage in [("tomato", "mid"), ("paddy", "initial")]:
        context = AgronomyContext(
            district="Kolar",
            allow_fao_reference=True,
            water_stage=stage,
            stage_valid_from=on,
            stage_valid_until=on,
        )
        assert coefficient_for_day(crop, catalogue.crops[crop], on, context)[0].value is None
    assert (
        coefficient_for_day("maize", catalogue.crops["maize"], on, AgronomyContext())[0].value
        is None
    )
    for crop in ("ragi", "tur"):
        context = AgronomyContext(
            district="Kolar",
            allow_fao_reference=True,
            water_stage="mid",
            stage_valid_from=on,
            stage_valid_until=on,
        )
        assert coefficient_for_day(crop, catalogue.crops[crop], on, context)[0].value is None


@pytest.mark.asyncio
async def test_plan_water_context_and_regional_scope():
    payload = recorded()
    on = date.fromtimestamp(payload["daily"]["time"][0])
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            body = {
                "latitude": 12.97,
                "longitude": 77.59,
                "crop": "maize",
                "sowing_status": "growing",
                "agronomy_context": {
                    "district": "Kolar",
                    "allow_fao_reference": True,
                    "water_stage": "mid",
                    "stage_valid_from": on.isoformat(),
                    "stage_valid_until": on.isoformat(),
                },
            }
            response = await client.post("/v1/plans", json=body)
            assert response.status_code == 200
            plan = response.json()
            first, second = plan["actions"][:2]
            expected = 1.2 * payload["daily"]["et0_fao_evapotranspiration"][0]
            assert first["water_balance"]["crop_et_mm"]["value"] == pytest.approx(expected)
            assert "Kc 1.200" in first["reason"]
            assert "not an irrigation dose" in first["reason"]
            assert second["water_balance"]["coefficient"]["status"] == "insufficient_data"
            assert plan["regional_sowing_window"]["districts"] == ["Kolar"]
            body["agronomy_context"]["district"] = "Ramanagara"
            assert (await client.post("/v1/plans", json=body)).json()[
                "regional_sowing_window"
            ] is None
            body["agronomy_context"]["district"] = "outside"
            assert (await client.post("/v1/plans", json=body)).status_code == 422


@pytest.mark.parametrize(
    "context",
    [
        {"water_stage": "mid"},
        {"water_stage": "end", "stage_valid_from": "2026-10-30", "stage_valid_until": "2026-11-01"},
        {"stage_valid_from": "2026-10-30"},
    ],
)
def test_invalid_stage_context(context):
    with pytest.raises(ValueError):
        AgronomyContext.model_validate(context)


def test_enabled_parameter_count_and_exact_written_values():
    enabled = [
        entry
        for parameters in load_catalogue().crops.values()
        for entry in parameters.values()
        if entry.enabled
    ]
    assert len(enabled) == 18
    for entry in enabled:
        assert entry.citation is not None
        assert entry.citation.locator
        if entry.reference_only:
            assert entry.citation.number_as_written
            assert entry.citation.region
