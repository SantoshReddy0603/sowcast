from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from sowcast.api.app import create_app
from sowcast.sources.models import Location
from sowcast.sources.power import PowerClient
from sowcast.sources.transport import SourceTransport


@pytest.mark.asyncio
async def test_power_rejects_future_recent_and_pre_archive_without_network():
    def unexpected(request):
        raise AssertionError("Unsupported dates must not contact NASA")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as http:
        source = PowerClient(SourceTransport(http))
        for on in (
            date(1980, 12, 31),
            datetime.now(UTC).date(),
            datetime.now(UTC).date() + timedelta(days=1),
        ):
            with pytest.raises(ValueError):
                await source.fetch(Location(latitude=13.14, longitude=78.13), on, on)
    app = create_app(httpx.MockTransport(unexpected))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            on = datetime.now(UTC).date().isoformat()
            response = await client.get(
                f"/v1/evidence/power?latitude=13.14&longitude=78.13&start_date={on}&end_date={on}"
            )
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "http_error"
