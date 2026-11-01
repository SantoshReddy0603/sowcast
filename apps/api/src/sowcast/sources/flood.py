from typing import Any

from sowcast.sources.base import SourceClientBase, metadata
from sowcast.sources.models import Location, Series, SourceEvidence
from sowcast.sources.parsing import parse_series
from sowcast.sources.transport import QueryValue

URL = "https://flood-api.open-meteo.com/v1/flood"


class FloodEvidence(SourceEvidence):
    location: Location
    grid_location: Location
    daily: Series
    original_unit: str
    limitation: str = (
        "Modelled river discharge; not plot inundation or a calibrated flood-risk level."
    )


class FloodClient(SourceClientBase):
    async def fetch(self, location: Location) -> FloodEvidence:
        params: dict[str, QueryValue] = {
            **location.model_dump(),
            "daily": "river_discharge",
            "forecast_days": 14,
            "timezone": "UTC",
            "timeformat": "unixtime",
        }

        def parse(payload: dict[str, Any]) -> FloodEvidence:
            original = payload["daily_units"]["river_discharge"]
            if original != "m³/s":
                raise ValueError("Unexpected river discharge units")
            payload = {
                **payload,
                "daily_units": {**payload["daily_units"], "river_discharge": "m³/s"},
            }
            daily = parse_series(payload, "daily", {"river_discharge": "m³/s"})
            values = daily.values["river_discharge"]
            if any(value is not None and value < 0 for value in values):
                raise ValueError("Negative river discharge")
            count = sum(value is not None for value in values)
            return FloodEvidence(
                **metadata(
                    "open_meteo_flood",
                    URL,
                    params,
                    "River discharge by GloFAS/Copernicus, via Open-Meteo.com",
                    "https://open-meteo.com/",
                    "https://creativecommons.org/licenses/by/4.0/",
                    "Selected discharge fields and UTC timestamp formatting.",
                ),
                location=location,
                grid_location=Location(
                    latitude=payload["latitude"],
                    longitude=payload["longitude"],
                ),
                daily=daily,
                original_unit=original,
                data_status="complete" if count == len(values) else "partial" if count else "empty",
                missing_reasons=()
                if count == len(values)
                else ("Some river discharge values are missing.",),
            )

        return await self.request(URL, params, parse)
