import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import structlog
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.responses import Response

from sowcast.agent.provider import GeminiProvider
from sowcast.agent.service import AgentService, Answer
from sowcast.agent.tools import PlotContext
from sowcast.agronomy.assessment import Plan, run_risk_assessment
from sowcast.agronomy.catalogue import CropName, load_catalogue
from sowcast.agronomy.water_balance import AgronomyContext
from sowcast.api.limits import RateLimiter, RateLimitMiddleware
from sowcast.backtest.metrics import BacktestResult, reliability_sentences
from sowcast.geography.districts import DistrictResult, identify_district
from sowcast.i18n.render import Language
from sowcast.logging import configure_logging
from sowcast.sources.climate import ClimateNormals
from sowcast.sources.flood import FloodEvidence
from sowcast.sources.geocoding import GeocodingEvidence
from sowcast.sources.mandi import MandiEvidence
from sowcast.sources.models import ErrorDetail, ErrorEnvelope, Forecast, Location, SourceError
from sowcast.sources.power import PowerEvidence
from sowcast.sources.services import SourceServices
from sowcast.sources.soil import SoilEvidence
from sowcast.storage.database import Database
from sowcast.storage.errors import StorageUnavailable
from sowcast.storage.traces import TraceStore


class PlanRequest(Location):
    model_config = {"frozen": True, "allow_inf_nan": False, "extra": "forbid"}
    api_version: Literal["1.0"] = "1.0"
    sowing_date: date | None = None
    crop: CropName
    sowing_status: Literal["not_sown", "growing"]
    growth_stage: Literal["flowering", "other"] | None = None
    agronomy_context: AgronomyContext | None = None
    language: Language = "en"

    @model_validator(mode="after")
    def plausible_dates(self) -> "PlanRequest":
        today = datetime.now(UTC).date()
        try:
            latest = today.replace(year=today.year + 1)
        except ValueError:
            latest = today.replace(year=today.year + 1, day=28)
        dates = {"sowing_date": self.sowing_date}
        if self.agronomy_context:
            dates["agronomy_context.planting_date"] = self.agronomy_context.planting_date
        for field, value in dates.items():
            if value is not None and not date(2020, 1, 1) <= value <= latest:
                raise PydanticCustomError(
                    "implausible_sowing_date",
                    "{field}: use a date from 2020 through one year ahead.",
                    {"field": field},
                )
        return self

    @model_validator(mode="after")
    def consistent_stage(self) -> "PlanRequest":
        nested_date = self.agronomy_context.planting_date if self.agronomy_context else None
        if (
            self.sowing_date is not None
            and nested_date is not None
            and self.sowing_date != nested_date
        ):
            raise ValueError("Sowing date conflicts with the reference profile planting date")
        if self.sowing_status == "not_sown" and self.sowing_date is not None:
            raise ValueError("Unsown crops cannot have an existing sowing date")
        if self.sowing_status == "not_sown" and self.growth_stage is not None:
            raise ValueError("An unsown crop cannot have a growth stage")
        if self.sowing_status == "not_sown" and self.agronomy_context is not None:
            if self.agronomy_context.water_stage or self.agronomy_context.planting_date:
                raise ValueError(
                    "Unsown crops cannot supply an existing crop stage or planting date"
                )
        return self


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    plot: PlanRequest
    language: Language = "en"

    @field_validator("question")
    @classmethod
    def nonblank_question(cls, value: str) -> str:
        if not value.strip():
            raise PydanticCustomError("blank_question", "question: enter a nonblank message.")
        return value.strip()


def regional_context(body: PlanRequest) -> AgronomyContext:
    try:
        resolved = identify_district(Location(latitude=body.latitude, longitude=body.longitude))
    except (OSError, ValueError) as exc:
        raise SourceError(
            "geography_unavailable",
            "District evidence is unavailable; local crop advice cannot be verified",
            True,
            "Sowcast district lookup",
        ) from exc
    if resolved.status != "matched" or resolved.supported_district is None:
        raise HTTPException(
            422,
            "Local crop advice requires a confirmed plot inside Bengaluru Rural, Kolar, "
            "Tumakuru, Chikkaballapura or Ramanagara. Check the plot coordinates; "
            "ocean, outside-area and uncertain boundary points are not supported.",
        )
    context = body.agronomy_context or AgronomyContext()
    return context.model_copy(update={"district": resolved.supported_district})


async def cached_reliability(request: Request, evidence: Forecast) -> tuple[str, ...]:
    values = evidence.daily.values.get("precipitation_sum")
    if values is None or evidence.daily.units.get("precipitation_sum") != "mm":
        return ()
    today = request.app.state.sources.backtest.clock().astimezone(UTC).date()
    days: list[tuple[int, date]] = []
    for moment, value in zip(evidence.daily.time, values, strict=False):
        valid_date = moment.date()
        lead = (valid_date - today).days
        if value is not None and 1 <= lead <= 7:
            days.append((lead, valid_date))
    if not days:
        return ()
    try:
        result = await request.app.state.sources.backtest.cached(evidence.location)
    except StorageUnavailable:
        return ()
    return () if result is None else reliability_sentences(result, tuple(days))


def create_app(upstream_transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if os.environ.get("SOWCAST_ENV") == "production" and not os.environ.get(
            "DATABASE_URL", ""
        ).startswith(("postgres://", "postgresql://", "postgresql+asyncpg://")):
            raise ValueError("Production requires a hosted PostgreSQL DATABASE_URL")
        shared_database = (
            Database(os.environ["DATABASE_URL"]) if os.environ.get("DATABASE_URL") else None
        )
        async with httpx.AsyncClient(transport=upstream_transport) as http:
            app.state.sources = SourceServices(
                http,
                os.environ.get("DATA_GOV_IN_API_KEY") or os.environ.get("AGMARKNET_API_KEY"),
                shared_database,
            )
            app.state.weather = app.state.sources.weather
            app.state.catalogue = load_catalogue()
            app.state.traces = TraceStore(
                shared_database or os.environ.get("SOWCAST_TRACE_DB", ".sowcast/traces.sqlite3")
            )
            app.state.agent = AgentService(
                GeminiProvider(
                    http,
                    os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"),
                    os.environ.get("GEMINI_MODEL"),
                ),
                app.state.sources,
                app.state.catalogue,
                app.state.traces,
            )
            await app.state.sources.backtest.store.database.initialize()
            await app.state.traces.database.initialize()
            try:
                yield
            finally:
                await app.state.sources.close()
                await app.state.traces.close()
                if shared_database:
                    await shared_database.close()

    app = FastAPI(title="Sowcast", lifespan=lifespan)

    app.state.limiter = RateLimiter()
    origins = [
        origin.strip() for origin in os.environ.get("CORS_ORIGINS", "").split(",") if origin.strip()
    ]
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("CORS_ORIGINS must contain explicit HTTP origins without paths")
    app.add_middleware(RateLimitMiddleware, limiter=app.state.limiter)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    @app.middleware("http")
    async def request_id(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.state.request_id = str(uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request.state.request_id)
        started = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                response = JSONResponse(
                    ErrorEnvelope(
                        error=ErrorDetail(
                            code="internal_error",
                            message="The request could not be completed; retry later.",
                            source="Sowcast API",
                            retryable=True,
                            request_id=request.state.request_id,
                        )
                    ).model_dump(),
                    status_code=500,
                )
                if request.headers.get("origin") in origins:
                    response.headers["Access-Control-Allow-Origin"] = request.headers["origin"]
                    response.headers["Access-Control-Expose-Headers"] = "X-Request-ID, Retry-After"
                    response.headers["Vary"] = "Origin"
            route = getattr(request.scope.get("route"), "path", "unmatched")
            method = (
                request.method
                if request.method in {"GET", "POST", "DELETE", "OPTIONS", "HEAD", "PUT", "PATCH"}
                else "OTHER"
            )
            structlog.get_logger().info(
                "api_request",
                route=route,
                method=method,
                http_status=response.status_code,
                source="Sowcast API",
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
            )
            response.headers["X-Request-ID"] = request.state.request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()

    @app.exception_handler(SourceError)
    async def source_error(request: Request, exc: SourceError) -> JSONResponse:
        envelope = exc.envelope(request.state.request_id)
        return JSONResponse(status_code=503, content=envelope.model_dump())

    def error_response(request: Request, code: str, message: str, status: int) -> JSONResponse:
        envelope = ErrorEnvelope(
            error=ErrorDetail(
                code=code,
                message=message,
                source=None,
                retryable=False,
                request_id=request.state.request_id,
            )
        )
        return JSONResponse(status_code=status, content=envelope.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        message = "Invalid request; check coordinates, crop, sowing status and growth stage."
        for error in exc.errors():
            if error["type"] == "blank_question":
                message = "question: enter a nonblank message."
                break
            if error["type"] == "implausible_sowing_date":
                field = (error.get("ctx") or {}).get("field")
                if field in {"sowing_date", "agronomy_context.planting_date"}:
                    message = f"{field}: use a date from 2020 through one year ahead."
                    break
            if "sowing_date" in error["loc"] or "planting_date" in error["loc"]:
                message = (
                    "sowing_date or agronomy_context.planting_date: use a valid calendar date."
                )
                break
        return error_response(request, "validation_error", message, 422)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error_response(request, "http_error", str(exc.detail), exc.status_code)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready(request: Request) -> dict[str, str]:
        await request.app.state.traces.database.ready()
        await request.app.state.sources.backtest.store.database.ready()
        return {"status": "ready"}

    @app.exception_handler(SQLAlchemyError)
    @app.exception_handler(StorageUnavailable)
    async def storage_error(request: Request, exc: Exception) -> JSONResponse:
        body = ErrorEnvelope(
            error=ErrorDetail(
                code="storage_unavailable",
                source="Sowcast storage",
                retryable=True,
                request_id=request.state.request_id,
                message="Storage is unavailable; retry later.",
            )
        )
        return JSONResponse(body.model_dump(), status_code=503)

    @app.get("/health/sources")
    async def source_health(request: Request) -> dict[str, object]:
        return {"api_version": "1.0", "sources": request.app.state.sources.health()}

    @app.get("/v1/places", response_model=GeocodingEvidence)
    async def places(
        request: Request,
        name: Annotated[str, Query(min_length=2, max_length=120)],
        language: Literal["en", "hi", "kn", "te", "ta", "mr"] = "en",
    ) -> GeocodingEvidence:
        if len(name.strip()) < 2:
            raise HTTPException(422, "Provide a non-empty place search")
        result: GeocodingEvidence = await request.app.state.sources.geocoding.get(
            (name.strip(), language)
        )
        return result

    @app.get("/v1/places/district", response_model=DistrictResult)
    def district(
        latitude: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
        longitude: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
    ) -> DistrictResult:
        return identify_district(Location(latitude=latitude, longitude=longitude))

    @app.get("/v1/evidence/flood", response_model=FloodEvidence)
    async def flood(
        request: Request,
        latitude: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
        longitude: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
    ) -> FloodEvidence:
        result: FloodEvidence = await request.app.state.sources.flood.get((latitude, longitude))
        return result

    @app.get("/v1/climate-normals", response_model=ClimateNormals)
    async def climate_normals(
        request: Request,
        latitude: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
        longitude: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
    ) -> ClimateNormals:
        result: ClimateNormals = await request.app.state.sources.climate.get((latitude, longitude))
        return result

    @app.get("/v1/evidence/power", response_model=PowerEvidence)
    async def power(
        request: Request,
        latitude: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
        longitude: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
        start_date: date,
        end_date: date,
    ) -> PowerEvidence:
        if start_date > end_date or (end_date - start_date).days > 60:
            raise HTTPException(422, "Use an ordered date range of at most 61 days")
        if start_date < date(1981, 1, 1) or end_date > datetime.now(UTC).date() - timedelta(days=7):
            raise HTTPException(
                422, "POWER cross-checks require dates from 1981 through seven days ago"
            )
        result: PowerEvidence = await request.app.state.sources.power.get(
            (latitude, longitude, start_date, end_date),
        )
        return result

    @app.get(
        "/v1/backtests",
        response_model=BacktestResult,
        responses={503: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
    )
    async def backtest(
        request: Request,
        latitude: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
        longitude: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
    ) -> BacktestResult:
        result: BacktestResult = await request.app.state.sources.backtest.get(
            Location(latitude=latitude, longitude=longitude)
        )
        return result

    @app.get("/v1/evidence/soil", response_model=SoilEvidence)
    async def soil(
        request: Request,
        latitude: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
        longitude: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
    ) -> SoilEvidence:
        result: SoilEvidence = await request.app.state.sources.soil.get((latitude, longitude))
        return result

    @app.get("/v1/evidence/mandi", response_model=MandiEvidence)
    async def mandi(
        request: Request,
        district: Annotated[str, Query(min_length=1, max_length=100)],
        commodity: Annotated[str, Query(min_length=1, max_length=100)],
    ) -> MandiEvidence:
        if not district.strip() or not commodity.strip():
            raise HTTPException(422, "District and commodity are required")
        result: MandiEvidence = await request.app.state.sources.mandi.get(
            (district.strip(), commodity.strip())
        )
        return result

    @app.get(
        "/v1/evidence/weather",
        response_model=Forecast,
        responses={503: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
    )
    async def weather(
        request: Request,
        latitude: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
        longitude: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
    ) -> Forecast:
        result: Forecast = await request.app.state.weather.get(
            Location(latitude=latitude, longitude=longitude),
        )
        return result

    @app.post(
        "/v1/plans",
        response_model=Plan,
        responses={503: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
    )
    async def plan(request: Request, body: PlanRequest) -> Plan:
        started = time.perf_counter()
        context = regional_context(body)
        evidence: Forecast = await request.app.state.weather.get(
            Location(latitude=body.latitude, longitude=body.longitude),
        )
        if body.sowing_date is not None:
            context = context.model_copy(update={"planting_date": body.sowing_date})
        deterministic = run_risk_assessment(
            evidence,
            body.crop,
            request.app.state.catalogue,
            body.sowing_status,
            body.growth_stage,
            context,
        )
        deterministic = deterministic.model_copy(
            update={"forecast_reliability": await cached_reliability(request, evidence)}
        )
        service: AgentService = request.app.state.agent
        enriched, _ = await service.explain_plan(deterministic, body.language, started_at=started)
        return enriched

    @app.post("/v1/chat", response_model=Answer)
    async def chat(request: Request, body: ChatRequest) -> Answer:
        context = regional_context(body.plot)
        if body.plot.sowing_date is not None:
            context = context.model_copy(update={"planting_date": body.plot.sowing_date})
        plot = PlotContext(
            latitude=body.plot.latitude,
            longitude=body.plot.longitude,
            crop=body.plot.crop,
            sowing_status=body.plot.sowing_status,
            sowing_date=body.plot.sowing_date.isoformat() if body.plot.sowing_date else None,
            growth_stage=body.plot.growth_stage,
            agronomy_context=context,
        )
        service: AgentService = request.app.state.agent
        return await service.ask(body.question, plot, body.language)

    @app.get("/v1/traces/{trace_id}")
    async def trace(request: Request, trace_id: str) -> dict[str, object]:
        try:
            from uuid import UUID

            UUID(trace_id)
        except ValueError as exc:
            raise HTTPException(422, "Invalid trace identifier") from exc
        scheme, _, credential = request.headers.get("Authorization", "").partition(" ")
        token = credential if scheme.casefold() == "bearer" else None
        result = await request.app.state.traces.get_authorized(trace_id, token)
        if result is None:
            raise HTTPException(404, "Trace not found")
        return {"api_version": "1.0", "trace_id": trace_id, "trace": result}

    @app.delete("/v1/traces/{trace_id}", status_code=204)
    async def delete_trace(request: Request, trace_id: str) -> Response:
        from uuid import UUID

        try:
            UUID(trace_id)
        except ValueError as exc:
            raise HTTPException(422, "Invalid trace identifier") from exc
        scheme, _, credential = request.headers.get("Authorization", "").partition(" ")
        token = credential if scheme.casefold() == "bearer" else None
        if not await request.app.state.traces.delete_authorized(trace_id, token):
            raise HTTPException(404, "Trace not found")
        return Response(status_code=204)

    return app


app = create_app()
