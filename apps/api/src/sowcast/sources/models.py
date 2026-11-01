from datetime import datetime
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Location(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class Series(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)
    time: tuple[datetime, ...]
    values: dict[str, tuple[float | None, ...]]
    units: dict[str, str]

    @model_validator(mode="after")
    def aligned(self) -> "Series":
        if not self.time or any(len(v) != len(self.time) for v in self.values.values()):
            raise ValueError("Empty or misaligned weather series")
        if set(self.values) != set(self.units):
            raise ValueError("Each variable requires a unit")
        if any(a >= b for a, b in zip(self.time, self.time[1:])):
            raise ValueError("Weather times must increase")
        return self


class SourceEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    api_version: Literal["1.0"] = "1.0"
    source: str
    attribution_url: str
    attribution_text: str
    licence_url: str | None
    modifications: str
    request_url: str
    fetched_at: datetime
    is_stale: bool = False
    data_status: Literal["complete", "partial", "empty"] = "complete"
    missing_reasons: tuple[str, ...] = ()


class Forecast(SourceEvidence):
    source: Literal["open_meteo_forecast"] = "open_meteo_forecast"
    attribution_url: str = "https://open-meteo.com/"
    attribution_text: str = "Weather data by Open-Meteo.com"
    licence_url: str = "https://creativecommons.org/licenses/by/4.0/"
    modifications: str = "Fields selected and reorganized; timestamps converted to UTC ISO 8601."
    request_url: str
    fetched_at: datetime
    is_stale: bool = False
    location: Location
    grid_location: Location
    timezone: str
    hourly: Series
    daily: Series


class ErrorDetail(BaseModel):
    code: str
    message: str
    source: str | None
    retryable: bool
    request_id: str


class ErrorEnvelope(BaseModel):
    api_version: Literal["1.0"] = "1.0"
    error: ErrorDetail


class SourceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        retryable: bool = False,
        source: str = "Open-Meteo forecast",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.source = source

    def envelope(self, request_id: str) -> ErrorEnvelope:
        reason = "network error" if self.code == "network_error" else str(self)
        suffix = " (retryable)" if self.retryable else ""
        return ErrorEnvelope(
            error=ErrorDetail(
                code=self.code,
                message=f"{self.source}: {reason}{suffix}",
                source=self.source,
                retryable=self.retryable,
                request_id=request_id,
            )
        )


class SourceHealth(BaseModel):
    status: Literal["unknown", "available", "degraded", "unavailable", "unconfigured"] = "unknown"
    checked_at: datetime | None = None
    error_code: str | None = None
    request_count: int = 0
    latency_ms: float | None = None


Result = TypeVar("Result", covariant=True)


class SourceClient(Protocol[Result]):
    async def fetch(self, location: Location) -> Result: ...
