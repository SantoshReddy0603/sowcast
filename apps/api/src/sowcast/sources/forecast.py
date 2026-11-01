from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx
from pydantic import ValidationError

from sowcast.sources.models import Forecast, Location, SourceError
from sowcast.sources.parsing import parse_series
from sowcast.sources.transport import QueryValue, SourceTransport

URL = "https://api.open-meteo.com/v1/forecast"
HOURLY = {
    "temperature_2m": "°C",
    "precipitation": "mm",
    "et0_fao_evapotranspiration": "mm",
    "soil_moisture_0_to_1cm": "m³/m³",
    "wind_speed_10m": "km/h",
}
DAILY = {
    "temperature_2m_max": "°C",
    "temperature_2m_min": "°C",
    "precipitation_sum": "mm",
    "et0_fao_evapotranspiration": "mm",
}


class ForecastClient:
    def __init__(self, transport: SourceTransport) -> None:
        self.transport = transport

    async def fetch(self, location: Location) -> Forecast:
        params: dict[str, QueryValue] = {
            **location.model_dump(),
            "hourly": ",".join(HOURLY),
            "daily": ",".join(DAILY),
            "forecast_days": 14,
            "timezone": "UTC",
            "timeformat": "unixtime",
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
        }
        payload = await self.transport.get(URL, params)
        try:
            hourly = parse_series(payload, "hourly", HOURLY)
            daily = parse_series(payload, "daily", DAILY)
            values = [
                value
                for series in (hourly, daily)
                for column in series.values.values()
                for value in column
            ]
            present = sum(value is not None for value in values)
            coverage_complete = (
                len(daily.time) == 14
                and len(hourly.time) == 14 * 24
                and hourly.time[0] == daily.time[0]
                and all(b - a == timedelta(days=1) for a, b in zip(daily.time, daily.time[1:]))
                and all(b - a == timedelta(hours=1) for a, b in zip(hourly.time, hourly.time[1:]))
            )
            status: Literal["complete", "partial", "empty"] = (
                "empty"
                if not present
                else "complete"
                if present == len(values) and coverage_complete
                else "partial"
            )
            result = Forecast(
                request_url=str(httpx.Request("GET", URL, params=params).url),
                fetched_at=datetime.now(UTC),
                location=location,
                grid_location=Location(
                    latitude=payload["latitude"],
                    longitude=payload["longitude"],
                ),
                timezone=payload["timezone"],
                hourly=hourly,
                daily=daily,
                data_status=status,
                missing_reasons=(
                    (() if present == len(values) else ("Forecast measurements are missing.",))
                    + (
                        ()
                        if coverage_complete
                        else ("Requested forecast time coverage is incomplete.",)
                    )
                ),
            )
            if status != "complete":
                self.transport.report("degraded", f"{status}_data")
            return result
        except (KeyError, TypeError, ValueError, OverflowError, ValidationError) as exc:
            self.transport.report("degraded", "invalid_response")
            raise SourceError("invalid_response", "Forecast schema or units are invalid") from exc
