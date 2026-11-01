import calendar
import math
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict

from sowcast.sources.base import SourceClientBase, metadata
from sowcast.sources.history import ARCHIVE_URL
from sowcast.sources.models import Location, SourceEvidence
from sowcast.sources.parsing import parse_series
from sowcast.sources.transport import QueryValue

START = date(1991, 1, 1)
END = date(2020, 12, 31)
FIELDS = {"temperature_2m_min": "°C", "temperature_2m_max": "°C", "precipitation_sum": "mm"}


class NormalDay(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)
    month_day: str
    values: dict[str, float | None]
    samples: dict[str, int]
    expected_samples: int


class ClimateNormals(SourceEvidence):
    location: Location
    grid_location: Location
    model: str = "era5"
    start_date: date = START
    end_date: date = END
    units: dict[str, str] = FIELDS
    days: tuple[NormalDay, ...]
    limitation: str = (
        "ERA5 gridded historical averages, not plot measurements or an official station normal. "
        "Same-calendar-day means require all expected years per variable; missing means stay null. "
        "February 29 has eight samples. UTC days differ from Indian midnight days. "
        "Average rainfall is not a rain probability or an irrigation requirement."
    )


def aggregate(
    payload: dict[str, Any], location: Location, params: dict[str, QueryValue]
) -> ClimateNormals:
    if any(
        value is not None and type(value) not in {int, float}
        for field in FIELDS
        for value in payload["daily"][field]
    ):
        raise ValueError("Climate values must be numbers or null")
    daily = parse_series(payload, "daily", FIELDS)
    if payload.get("utc_offset_seconds") != 0:
        raise ValueError("Climate baseline requires UTC")
    values: dict[str, dict[str, list[float]]] = {}
    for index, timestamp in enumerate(daily.time):
        if timestamp.hour or timestamp.minute or timestamp.second or timestamp.microsecond:
            raise ValueError("Expected daily UTC boundaries")
        if not START <= timestamp.date() <= END:
            raise ValueError("Baseline date outside reference period")
        low = daily.values["temperature_2m_min"][index]
        high = daily.values["temperature_2m_max"][index]
        if low is not None and high is not None and low > high:
            raise ValueError("Temperature extrema are reversed")
        month_day = timestamp.strftime("%m-%d")
        bucket = values.setdefault(month_day, {field: [] for field in FIELDS})
        for field in FIELDS:
            value = daily.values[field][index]
            if value is not None:
                if not math.isfinite(value) or (field == "precipitation_sum" and value < 0):
                    raise ValueError("Invalid climate measurement")
                bucket[field].append(value)
    days = []
    for offset in range(366):
        month_day = (date(2000, 1, 1) + timedelta(days=offset)).strftime("%m-%d")
        expected = (
            sum(calendar.isleap(year) for year in range(1991, 2021)) if month_day == "02-29" else 30
        )
        bucket = values.get(month_day, {field: [] for field in FIELDS})
        counts = {field: len(samples) for field, samples in bucket.items()}
        days.append(
            NormalDay(
                month_day=month_day,
                samples=counts,
                expected_samples=expected,
                values={
                    field: math.fsum(samples) / expected if len(samples) == expected else None
                    for field, samples in bucket.items()
                },
            )
        )
    available = sum(value is not None for day in days for value in day.values.values())
    complete = available == 366 * len(FIELDS)
    return ClimateNormals(
        **metadata(
            "open_meteo_archive",
            ARCHIVE_URL,
            params,
            "Weather data by Open-Meteo.com; ERA5/Copernicus C3S",
            "https://open-meteo.com/",
            "https://creativecommons.org/licenses/by/4.0/",
            "UTC daily values averaged by calendar month/day over 1991–2020; "
            "no missing values filled.",
        ),
        location=location,
        grid_location=Location(latitude=payload["latitude"], longitude=payload["longitude"]),
        days=tuple(days),
        data_status="complete" if complete else "partial" if available else "empty",
        missing_reasons=()
        if complete
        else ("Some calendar-day means lack complete year coverage.",),
    )


class ClimateClient(SourceClientBase):
    async def fetch(self, location: Location) -> ClimateNormals:
        params: dict[str, QueryValue] = {
            **location.model_dump(),
            "start_date": str(START),
            "end_date": str(END),
            "daily": ",".join(FIELDS),
            "models": "era5",
            "timezone": "UTC",
            "timeformat": "unixtime",
            "temperature_unit": "celsius",
            "precipitation_unit": "mm",
        }
        return await self.request(
            ARCHIVE_URL, params, lambda payload: aggregate(payload, location, params)
        )
