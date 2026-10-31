from datetime import UTC, date, datetime, timedelta
from typing import Any

from sowcast.sources.base import SourceClientBase, metadata
from sowcast.sources.models import Location, Series, SourceEvidence
from sowcast.sources.transport import QueryValue

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETERS = {"T2M": "C", "PRECTOTCORR": "mm/day", "ALLSKY_SFC_SW_DWN": "MJ/m^2/day"}


class PowerEvidence(SourceEvidence):
    evidence_role: str = "observation_cross_check"
    service_version: str
    data_sources: tuple[str, ...]
    location: Location
    start_date: date
    end_date: date
    daily: Series
    limitation: str = "Gridded retrospective estimates; not a forecast or plot station observation."


class PowerClient(SourceClientBase):
    async def fetch(self, location: Location, start: date, end: date) -> PowerEvidence:
        if start > end or (end - start).days > 60:
            raise ValueError("Provide an ordered date range of at most 61 days")
        if start < date(1981, 1, 1) or end > datetime.now(UTC).date() - timedelta(days=7):
            raise ValueError("POWER cross-checks require dates from 1981 through seven days ago")
        params: dict[str, QueryValue] = {
            **location.model_dump(),
            "community": "AG",
            "parameters": ",".join(PARAMETERS),
            "start": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
            "format": "JSON",
            "time-standard": "UTC",
        }

        def parse(payload: dict[str, Any]) -> PowerEvidence:
            header = payload["header"]
            if header["time_standard"] != "UTC":
                raise ValueError("Unexpected POWER time standard")
            fill = header["fill_value"]
            raw = payload["properties"]["parameter"]
            dates = sorted(raw["T2M"])
            times = tuple(datetime.strptime(day, "%Y%m%d").replace(tzinfo=UTC) for day in dates)
            if any(not start <= day.date() <= end for day in times):
                raise ValueError("POWER dates outside the requested interval")
            values: dict[str, tuple[float | None, ...]] = {}
            for name, unit in PARAMETERS.items():
                if payload["parameters"][name]["units"] != unit or sorted(raw[name]) != dates:
                    raise ValueError("Unexpected POWER units or date alignment")
                values[name] = tuple(
                    None if raw[name][day] == fill else raw[name][day] for day in dates
                )
            missing = tuple(
                f"{name} has missing source values."
                for name, series in values.items()
                if any(value is None for value in series)
            )
            if len(dates) != (end - start).days + 1:
                missing += ("Some requested UTC dates were not returned by NASA POWER.",)
            valid = sum(value is not None for series in values.values() for value in series)
            return PowerEvidence(
                **metadata(
                    "nasa_power",
                    URL,
                    params,
                    "NASA POWER Project, NASA Langley Research Center",
                    "https://power.larc.nasa.gov/",
                    None,
                    "Selected AG parameters; source fill values converted to null; UTC dates.",
                ),
                location=location,
                service_version=header["api"]["version"],
                data_sources=tuple(header["sources"]),
                start_date=start,
                end_date=end,
                daily=Series(time=times, values=values, units=PARAMETERS),
                data_status="empty" if not valid else "partial" if missing else "complete",
                missing_reasons=missing,
            )

        return await self.request(URL, params, parse)
