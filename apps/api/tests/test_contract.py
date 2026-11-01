import json
from pathlib import Path

import httpx
import pytest
from test_plans import recorded

from sowcast.api.app import create_app


def test_published_api_schema_matches_contract():
    path = Path(__file__).resolve().parents[3] / "docs/api-schema.json"
    assert create_app().openapi() == json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_version_sowing_date_and_no_water_rule_message():
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            body = {
                "api_version": "1.0",
                "latitude": 13.14,
                "longitude": 78.13,
                "crop": "maize",
                "sowing_status": "growing",
                "sowing_date": "2026-10-01",
                "agronomy_context": {"district": "Kolar", "allow_fao_reference": True},
            }
            response = await client.post("/v1/plans", json=body)
            assert response.status_code == 200
            assert response.json()["api_version"] == "1.0"
            assert response.json()["sowing_date"] == body["sowing_date"]
            assert (
                response.json()["actions"][0]["water_balance"]["coefficient"]["value"] is not None
            )
            for crop in ("ragi", "tur"):
                body["crop"] = crop
                plan = (await client.post("/v1/plans", json=body)).json()
                assert (
                    f"No water-balance rule exists for {crop}" in plan["water_balance_availability"]
                )
            body["api_version"] = "2.0"
            rejected = await client.post("/v1/plans", json=body)
            assert rejected.status_code == 422
            assert rejected.json()["api_version"] == "1.0"
            assert rejected.json()["error"]["request_id"] == rejected.headers["X-Request-ID"]
            body["api_version"] = "1.0"
            body["agronomy_context"]["planting_date"] = "2026-10-02"
            assert (await client.post("/v1/plans", json=body)).status_code == 422
