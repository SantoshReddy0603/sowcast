import asyncio
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sowcast.agronomy.assessment import Plan, run_risk_assessment
from sowcast.agronomy.catalogue import Catalogue, CropName
from sowcast.agronomy.water_balance import AgronomyContext
from sowcast.sources.models import Location, SourceError
from sowcast.sources.services import SourceServices

ToolName = Literal[
    "get_forecast",
    "get_soil",
    "get_mandi_prices",
    "run_risk_assessment",
    "get_backtest",
    "get_flood_signal",
]


class PlotContext(Location):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    crop: CropName
    sowing_status: Literal["growing", "not_sown"]
    sowing_date: str | None = None
    growth_stage: Literal["flowering", "other"] | None = None
    agronomy_context: AgronomyContext | None = None


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: ToolName
    arguments: dict[str, str] = Field(default_factory=dict)


class MarketArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    district: str = Field(min_length=1, max_length=100)
    commodity: str = Field(min_length=1, max_length=100)


class ToolRunner:
    def __init__(self, sources: SourceServices, catalogue: Catalogue, context: PlotContext) -> None:
        self.sources, self.catalogue, self.context = sources, catalogue, context
        self.events: list[dict[str, Any]] = []
        self.plan: Plan | None = None

    async def execute(self, call: ToolCall) -> dict[str, Any]:
        started = time.monotonic()
        result: dict[str, Any]
        try:
            async with asyncio.timeout(18):
                result = await self._run(call)
        except TimeoutError:
            result = {"status": "error", "code": "tool_timeout", "retryable": True}
        except SourceError as exc:
            result = {
                "status": "error",
                "code": exc.code,
                "source": exc.source,
                "retryable": exc.retryable,
            }
        except (ValueError, ValidationError):
            result = {"status": "error", "code": "invalid_tool_arguments", "retryable": False}
        self.events.append(
            {
                "name": call.name,
                "arguments": call.arguments,
                "latitude": self.context.latitude,
                "longitude": self.context.longitude,
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
                "status": result.get("status"),
                "code": result.get("code"),
            }
        )
        return result

    async def _run(self, call: ToolCall) -> dict[str, Any]:
        location = Location(latitude=self.context.latitude, longitude=self.context.longitude)
        key = (location.latitude, location.longitude)
        if call.name == "get_mandi_prices":
            args = MarketArguments.model_validate(call.arguments)
            evidence = await self.sources.mandi.get((args.district, args.commodity))
            return {"status": evidence.data_status, "evidence": evidence.model_dump(mode="json")}
        if call.arguments:
            raise ValueError("This tool uses only the validated request plot context")
        if call.name == "get_backtest":
            result = await self.sources.backtest.get(location)
            return {"status": result.data_status, "backtest": result.model_dump(mode="json")}
        if call.name == "get_forecast":
            forecast = await self.sources.weather.get(location)
            return {"status": forecast.data_status, "evidence": forecast.model_dump(mode="json")}
        if call.name == "get_soil":
            soil = await self.sources.soil.get(key)
            return {"status": soil.data_status, "evidence": soil.model_dump(mode="json")}
        if call.name == "get_flood_signal":
            flood = await self.sources.flood.get(key)
            return {"status": flood.data_status, "evidence": flood.model_dump(mode="json")}
        forecast = await self.sources.weather.get(location)
        self.plan = run_risk_assessment(
            forecast,
            self.context.crop,
            self.catalogue,
            self.context.sowing_status,
            self.context.growth_stage,
            self.context.agronomy_context,
        )
        return {"status": "complete", "plan": self.plan.model_dump(mode="json")}
