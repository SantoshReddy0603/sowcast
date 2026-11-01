import httpx
import pytest
from test_plans import recorded

from sowcast.api.app import create_app


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/v1/plans", "/v1/chat"])
@pytest.mark.parametrize("point", [(0, -30), (28.61, 77.21)])
async def test_forged_district_outside_pilot_never_calls_sources(path, point):
    def reject(request):
        pytest.fail("Unsupported plots must be rejected before upstream work")

    app = create_app(httpx.MockTransport(reject))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            plot = {
                "latitude": point[0],
                "longitude": point[1],
                "crop": "maize",
                "sowing_status": "not_sown",
                "agronomy_context": {"district": "Kolar"},
            }
            body = (
                plot if path == "/v1/plans" else {"question": "What should I check?", "plot": plot}
            )
            response = await client.post(path, json=body)
            assert response.status_code == 422
            error = response.json()["error"]
            assert error["code"] == "http_error" and error["retryable"] is False
            assert "coordinates" in error["message"]
            assert error["request_id"] == response.headers["x-request-id"]
            assert "actions" not in response.json()
            assert all(h.request_count == 0 for h in app.state.sources.health().values())


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/v1/plans", "/v1/chat"])
async def test_pilot_district_is_resolved_instead_of_trusting_caller(path):
    app = create_app(httpx.MockTransport(lambda request: httpx.Response(200, json=recorded())))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            plot = {
                "latitude": 13.34,
                "longitude": 77.1,
                "crop": "maize",
                "sowing_status": "not_sown",
                "agronomy_context": {"district": "Kolar"},
            }
            body = (
                plot if path == "/v1/plans" else {"question": "What should I check?", "plot": plot}
            )
            response = await client.post(path, json=body)
            assert response.status_code == 200
            plan = response.json() if path == "/v1/plans" else response.json()["plan"]
            assert plan["agronomy_context"]["district"] == "Tumakuru"
            assert plan["regional_sowing_window"] is None
            assert len(plan["actions"]) == 14


@pytest.mark.asyncio
async def test_unavailable_boundary_data_fails_closed(monkeypatch):
    def unavailable(location):
        raise OSError("private filesystem detail")

    monkeypatch.setattr("sowcast.api.app.identify_district", unavailable)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
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
            assert response.json()["error"]["code"] == "geography_unavailable"
            assert "private" not in response.text
