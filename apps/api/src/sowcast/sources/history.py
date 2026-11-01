from datetime import date, timedelta
from typing import Any, Literal

from sowcast.sources.base import SourceClientBase, metadata
from sowcast.sources.models import Location, Series, SourceEvidence
from sowcast.sources.parsing import parse_series
from sowcast.sources.transport import QueryValue

LEADS = (1, 2, 3, 4, 5, 6, 7)
PREVIOUS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


class HistorySource(SourceEvidence):
    location: Location
    grid_location: Location
    model: str


class HistoryEvidence(HistorySource):
    hourly: Series


class HistoryClient(SourceClientBase):
    async def fetch(
        self, location: Location, start: date, end: date, kind: Literal["previous", "archive"]
    ) -> HistoryEvidence:
        if end < start or (end - start).days != 59:
            raise ValueError("History comparison requires exactly 60 days")
        previous = kind == "previous"
        fields = {
            f"{field}_previous_day{lead}" if previous else field: unit
            for lead in (LEADS if previous else (0,))
            for field, unit in (("temperature_2m", "°C"), ("precipitation", "mm"))
        }
        url = PREVIOUS_URL if previous else ARCHIVE_URL
        model = "gfs_global" if previous else "era5"
        params: dict[str, QueryValue] = {
            **location.model_dump(),
            "start_date": str(start),
            "end_date": str(end + timedelta(days=1)),
            "hourly": ",".join(fields),
            "models": model,
            "timezone": "UTC",
            "timeformat": "unixtime",
            "temperature_unit": "celsius",
            "precipitation_unit": "mm",
        }

        def parse(payload: dict[str, Any]) -> HistoryEvidence:
            hourly = parse_series(payload, "hourly", fields)
            if payload.get("utc_offset_seconds") != 0:
                raise ValueError("History must use UTC")
            if any(t.minute or t.second or t.microsecond for t in hourly.time):
                raise ValueError("History timestamps must be exact UTC hours")
            if any(t.date() < start or t.date() > end + timedelta(days=1) for t in hourly.time):
                raise ValueError("History timestamps exceed requested interval")
            if any(
                v is not None and v < 0
                for f, vs in hourly.values.items()
                if f.startswith("precipitation")
                for v in vs
            ):
                raise ValueError("Negative precipitation")
            present = sum(v is not None for vs in hourly.values.values() for v in vs)
            total = 1464 * len(fields)
            return HistoryEvidence(
                **metadata(
                    "open_meteo_previous_runs" if previous else "open_meteo_archive",
                    url,
                    params,
                    "Weather data by Open-Meteo.com; GFS/NOAA"
                    if previous
                    else "Weather data by Open-Meteo.com; ERA5/Copernicus C3S",
                    "https://open-meteo.com/",
                    "https://creativecommons.org/licenses/by/4.0/",
                    "Selected hourly fields; UTC timestamps. No missing values filled.",
                ),
                location=location,
                grid_location=Location(
                    latitude=payload["latitude"], longitude=payload["longitude"]
                ),
                model=model,
                hourly=hourly,
                data_status="complete" if present == total else "partial" if present else "empty",
                missing_reasons=()
                if present == total
                else ("History has missing hours or values.",),
            )

        return await self.request(url, params, parse)
