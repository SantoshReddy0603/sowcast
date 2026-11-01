from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from sowcast.api.app import ChatRequest, PlanRequest, create_app

PLOT = {"latitude": 13.14, "longitude": 78.13, "crop": "maize", "sowing_status": "growing"}


def next_year():
    today = datetime.now(UTC).date()
    try:
        return today.replace(year=today.year + 1)
    except ValueError:
        return today.replace(year=today.year + 1, day=28)


@pytest.mark.parametrize("field", ["sowing_date", "planting_date"])
@pytest.mark.parametrize("value", [date(2020, 1, 1), next_year()])
def test_sowing_date_boundaries(field, value):
    body = dict(PLOT)
    if field == "sowing_date":
        body[field] = value.isoformat()
    else:
        body["agronomy_context"] = {field: value.isoformat()}
    assert PlanRequest.model_validate(body)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/v1/plans", "/v1/chat"])
@pytest.mark.parametrize("field", ["sowing_date", "planting_date"])
@pytest.mark.parametrize("value", [date(2019, 12, 31), next_year() + timedelta(days=1)])
async def test_implausible_dates_have_safe_field_errors(path, field, value):
    app = create_app(httpx.MockTransport(lambda request: pytest.fail("No upstream call expected")))
    plot = dict(PLOT)
    if field == "sowing_date":
        plot[field] = value.isoformat()
    else:
        plot["agronomy_context"] = {field: value.isoformat()}
    body = plot if path == "/v1/plans" else {"plot": plot, "question": "Check evidence"}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(path, json=body)
    assert response.status_code == 422
    error = response.json()["error"]
    assert field in error["message"] and "2020" in error["message"]
    assert error["code"] == "validation_error" and error["retryable"] is False
    assert error["request_id"] == response.headers["x-request-id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("question", [" ", "\t\n", "\u3000\u00a0"])
async def test_blank_chat_rejected_before_sources(question):
    app = create_app(httpx.MockTransport(lambda request: pytest.fail("No upstream call expected")))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/v1/chat", json={"plot": PLOT, "question": question})
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "question: enter a nonblank message."


def test_chat_trims_message():
    assert (
        ChatRequest.model_validate({"plot": PLOT, "question": "  Check evidence  "}).question
        == "Check evidence"
    )
