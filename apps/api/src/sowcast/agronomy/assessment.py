from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from sowcast.agronomy.catalogue import Catalogue, Citation, CropName, Threshold
from sowcast.agronomy.rules import (
    RuleResult,
    frost_risk,
    growing_degree_days,
    heat_stress_days,
    insufficient,
    rainfall_deficit_against_et0,
    sowing_window_suitability,
    waterlogging_risk,
)
from sowcast.agronomy.water_balance import (
    AgronomyContext,
    CropWaterBalance,
    coefficient_for_day,
    crop_water_balance,
)
from sowcast.sources.models import Forecast, Location


class EvidenceReference(BaseModel):
    source: str
    request_url: str
    fetched_at: datetime
    is_stale: bool
    field: str
    valid_at: datetime
    value: float | None
    unit: str


class Action(BaseModel):
    date: date
    kind: Literal["inspect_heat_exposure", "review_water_balance", "review_evidence"]
    reason: str
    explanation: str | None = None
    explanation_status: Literal["unavailable", "verified"] = "unavailable"
    explanation_sources: tuple[str, ...] = ()
    rule_version: str
    metrics: dict[str, RuleResult]
    inputs: tuple[EvidenceReference, ...]
    citations: tuple[Citation, ...]
    water_balance: CropWaterBalance


class DisabledRule(BaseModel):
    parameter: str
    reason: str


class Plan(BaseModel):
    api_version: Literal["1.0"] = "1.0"
    crop: CropName
    location: Location
    rule_version: str
    date_basis: Literal["UTC forecast days"] = "UTC forecast days"
    sowing_status: Literal["not_sown", "growing"]
    growth_stage: Literal["flowering", "other"] | None
    actions: tuple[Action, ...]
    disabled_parameters: tuple[DisabledRule, ...]
    evidence: Forecast
    limitation: str
    agronomy_context: AgronomyContext
    regional_sowing_window: Threshold | None = None
    sowing_date: date | None = None
    water_balance_availability: str
    agent_note: str = "Explanations unavailable."
    forecast_reliability: tuple[str, ...] = ()
    trace_id: str | None = None
    trace_access_token: str | None = None
    optional_evidence_notes: tuple[str, ...] = (
        "SoilGrids is optional; missing soil values never block the weather-based plan.",
        "NASA POWER is retrospective observation cross-check evidence, not a forecast input.",
    )


def numeric(threshold: Threshold) -> float | None:
    return threshold.value if threshold.enabled and isinstance(threshold.value, float) else None


def run_risk_assessment(
    evidence: Forecast,
    crop: CropName,
    catalogue: Catalogue,
    sowing_status: Literal["not_sown", "growing"],
    growth_stage: Literal["flowering", "other"] | None = None,
    context: AgronomyContext | None = None,
) -> Plan:
    context = context or AgronomyContext()
    parameters = catalogue.crops[crop]
    actions: list[Action] = []
    fields = {
        "temperature_2m_min": "°C",
        "temperature_2m_max": "°C",
        "precipitation_sum": "mm",
        "et0_fao_evapotranspiration": "mm",
    }
    for index, valid_at in enumerate(evidence.daily.time):

        def measurement(field: str) -> float | None:
            if evidence.daily.units.get(field) != fields[field]:
                return None
            values = evidence.daily.values.get(field)
            return values[index] if values is not None else None

        low = measurement("temperature_2m_min")
        high = measurement("temperature_2m_max")
        rain = measurement("precipitation_sum")
        et0 = measurement("et0_fao_evapotranspiration")
        coefficient, water_stage, stage_basis, water_citations = coefficient_for_day(
            crop,
            parameters,
            valid_at.date(),
            context,
        )
        if crop in ("ragi", "tur"):
            coefficient = insufficient(
                "dimensionless", f"No verified crop-water profile is enabled for {crop}."
            )
        elif sowing_status != "growing":
            coefficient = insufficient("dimensionless", "A growing crop is required for crop ET.")
        crop_et, shortfall = crop_water_balance(rain, et0, coefficient)
        water = CropWaterBalance(
            coefficient=coefficient,
            crop_et_mm=crop_et,
            rainfall_shortfall_mm=shortfall,
            stage=water_stage,
            stage_basis=stage_basis,
            citations=water_citations,
        )
        heat_parameter = parameters["heat_above_c"]
        heat = heat_stress_days((high,), numeric(heat_parameter))
        if heat_parameter.stage and (
            sowing_status != "growing" or growth_stage != heat_parameter.stage
        ):
            heat = insufficient("day", "Heat rule requires a growing crop at the cited stage.")
        if evidence.is_stale:
            heat = insufficient("day", "Stale forecast cannot trigger a protective action.")
        metrics = {
            "growing_degree_days": growing_degree_days(
                low, high, numeric(parameters["gdd_base_c"])
            ),
            "heat_stress_days": heat,
            "frost_risk": frost_risk(low, numeric(parameters["frost_below_c"])),
            "rainfall_deficit_against_et0": rainfall_deficit_against_et0((rain,), (et0,)),
            "rainfall_shortfall_against_crop_et": shortfall,
            "waterlogging_risk": waterlogging_risk(
                rain,
                None,
                None,
                None,
                numeric(parameters["waterlogging_excess_mm"]),
            ),
            "sowing_window_suitability": sowing_window_suitability(
                valid_at.date(),
                None,
                None,
                numeric(parameters["sowing_min_c"]),
                numeric(parameters["sowing_max_c"]),
                None,
            ),
        }
        kind: Literal["inspect_heat_exposure", "review_water_balance", "review_evidence"]
        if heat.status == "available" and heat.value is not None and heat.value > 0:
            kind = "inspect_heat_exposure"
            reason = (
                f"{valid_at.date().isoformat()} UTC forecast maximum {high:.2f} °C exceeds "
                f"the {numeric(heat_parameter):.2f} °C reference flowering heat screen "
                "(national/international source, not calibrated for Karnataka districts). "
                "Inspect the crop and seek local advice; duration and injury are not established."
            )
        elif (
            metrics["rainfall_deficit_against_et0"].status == "available" and not evidence.is_stale
        ):
            if crop_et.value is not None and shortfall.value is not None:
                kind = "review_water_balance"
                reason = (
                    f"{valid_at.date().isoformat()} UTC forecast: rainfall {rain:.2f} mm against "
                    f"reference {crop} {water_stage} ETc {crop_et.value:.2f} mm "
                    f"(Kc {coefficient.value:.3f} × ET0 {et0:.2f} mm); "
                    f"gross-rainfall shortfall {shortfall.value:.2f} mm. "
                    "Review soil moisture and irrigation records; this is not an irrigation dose. "
                    "FAO reference values are not locally calibrated."
                )
            else:
                kind = "review_evidence"
                if sowing_status == "not_sown":
                    next_step = (
                        "The crop is not yet sown. Review rainfall, soil readiness and local "
                        "sowing advice before deciding; this is not a safe-to-sow recommendation."
                    )
                elif crop in ("ragi", "tur"):
                    next_step = (
                        f"No verified crop-water rule is enabled for {crop}; crop water need "
                        "cannot be assessed. Review the forecast with local extension advice."
                    )
                else:
                    next_step = (
                        "An applicable crop stage or reference profile is missing. "
                        "Confirm growth stage and field conditions; "
                        "no crop-water estimate is shown."
                    )
                reason = (
                    f"{valid_at.date().isoformat()} UTC forecast: rainfall {rain:.2f} mm and "
                    f"reference ET0 {et0:.2f} mm. {next_step}"
                )
        else:
            kind = "review_evidence"
            reason = "Refresh or complete the evidence before deciding field operations."
        inputs = tuple(
            EvidenceReference(
                source=evidence.source,
                request_url=evidence.request_url,
                fetched_at=evidence.fetched_at,
                is_stale=evidence.is_stale,
                field=f"daily.values.{field}[{index}]",
                valid_at=valid_at,
                value=measurement(field),
                unit=unit,
            )
            for field, unit in fields.items()
        )
        citations = tuple(
            parameter.citation
            for parameter in parameters.values()
            if parameter.enabled and parameter.citation is not None and not parameter.reference_only
        )
        actions.append(
            Action(
                date=valid_at.date(),
                kind=kind,
                reason=reason,
                rule_version=catalogue.version,
                metrics=metrics,
                inputs=inputs,
                citations=citations,
                water_balance=water,
            )
        )
    return Plan(
        crop=crop,
        location=evidence.location,
        rule_version=catalogue.version,
        sowing_status=sowing_status,
        growth_stage=growth_stage,
        actions=tuple(actions),
        disabled_parameters=tuple(
            DisabledRule(parameter=name, reason=parameter.reason)
            for name, parameter in parameters.items()
            if not parameter.enabled
        ),
        evidence=evidence,
        sowing_date=context.planting_date,
        water_balance_availability=(
            f"No water-balance rule exists for {crop}. Weather evidence is shown; "
            "crop-water need is not estimated."
            if crop in ("ragi", "tur")
            else "Reference water balance needs applicable stage inputs and field conditions."
        ),
        agronomy_context=context,
        regional_sowing_window=(
            parameters["sowing_window"]
            if parameters["sowing_window"].enabled
            and context.district in parameters["sowing_window"].districts
            else None
        ),
        limitation=(
            "Decision support, not a replacement for local extension officers. "
            "Actions are inspection/review tasks, not prescriptions. "
            "AI explanations are optional; evidence checks can withhold unsupported responses. "
            "UTC daily extrema screen exposure; they do not establish duration or injury."
            " District boundaries do not verify field conditions or plot ownership. "
            "FAO coefficients and "
            "duration examples are reference estimates, not Karnataka calibration. "
            "Historical sowing windows do not establish rainfall onset or soil readiness."
        ),
    )
