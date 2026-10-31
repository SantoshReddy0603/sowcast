import math
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict


class RuleResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: Literal["available", "insufficient_data", "invalid_input"]
    value: float | None = None
    unit: str
    reason: str


def insufficient(unit: str, reason: str) -> RuleResult:
    return RuleResult(status="insufficient_data", unit=unit, reason=reason)


def invalid(unit: str) -> RuleResult:
    return RuleResult(status="invalid_input", unit=unit, reason="Invalid or non-finite input.")


def available(value: float, unit: str, reason: str) -> RuleResult:
    if not math.isfinite(value):
        return invalid(unit)
    return RuleResult(status="available", value=value, unit=unit, reason=reason)


def growing_degree_days(
    minimum_c: float | None,
    maximum_c: float | None,
    base_c: float | None,
) -> RuleResult:
    if minimum_c is None or maximum_c is None or base_c is None:
        return insufficient("degC_day", "Daily extrema or verified crop base temperature missing.")
    if not all(map(math.isfinite, (minimum_c, maximum_c, base_c))) or minimum_c > maximum_c:
        return invalid("degC_day")
    return available(
        max(0, minimum_c / 2 + maximum_c / 2 - base_c),
        "degC_day",
        "Uncapped daily mean temperature above the supplied base; not a maturity prediction.",
    )


def heat_stress_days(
    daily_maxima_c: tuple[float | None, ...],
    threshold_c: float | None,
) -> RuleResult:
    if not daily_maxima_c or threshold_c is None or any(t is None for t in daily_maxima_c):
        return insufficient("day", "Temperature coverage or verified heat threshold missing.")
    values = tuple(t for t in daily_maxima_c if t is not None)
    if not all(map(math.isfinite, (*values, threshold_c))):
        return invalid("day")
    return available(
        float(sum(t > threshold_c for t in values)),
        "day",
        "Days strictly above the threshold; potential exposure, not proven injury.",
    )


def frost_risk(minimum_c: float | None, threshold_c: float | None) -> RuleResult:
    if minimum_c is None or threshold_c is None:
        return insufficient("flag", "Minimum temperature or verified frost threshold missing.")
    if not all(map(math.isfinite, (minimum_c, threshold_c))):
        return invalid("flag")
    return available(float(minimum_c < threshold_c), "flag", "Below-threshold temperature screen.")


def rainfall_deficit_against_et0(
    rainfall_mm: tuple[float | None, ...],
    et0_mm: tuple[float | None, ...],
) -> RuleResult:
    if not rainfall_mm or not et0_mm or any(v is None for v in (*rainfall_mm, *et0_mm)):
        return insufficient("mm", "Complete paired rainfall and reference ET0 are required.")
    if len(rainfall_mm) != len(et0_mm):
        return invalid("mm")
    rain = tuple(v for v in rainfall_mm if v is not None)
    et0 = tuple(v for v in et0_mm if v is not None)
    if any(not math.isfinite(v) or v < 0 for v in (*rain, *et0)):
        return invalid("mm")
    return available(
        max(0, sum(et0) - sum(rain)),
        "mm",
        "Reference atmospheric water deficit; not crop water stress or irrigation volume.",
    )


def waterlogging_risk(
    rainfall_mm: float | None,
    infiltration_mm: float | None,
    drainage_mm: float | None,
    available_storage_mm: float | None,
    threshold_mm: float | None,
) -> RuleResult:
    inputs = (rainfall_mm, infiltration_mm, drainage_mm, available_storage_mm, threshold_mm)
    if any(v is None for v in inputs):
        return insufficient(
            "flag", "Field storage, drainage, infiltration or verified limit missing."
        )
    values = tuple(v for v in inputs if v is not None)
    if any(not math.isfinite(v) or v < 0 for v in values):
        return invalid("flag")
    rain, infiltration, drainage, storage, threshold = values
    return available(
        float(rain - infiltration - drainage - storage > threshold),
        "flag",
        "Simplified surface-excess screen; infiltration and surface drainage must not overlap.",
    )


def sowing_window_suitability(
    on: date | None,
    months: tuple[int, ...] | None,
    temperature_c: float | None,
    minimum_c: float | None,
    maximum_c: float | None,
    soil_ready: bool | None,
) -> RuleResult:
    if any(v is None for v in (on, months, temperature_c, minimum_c, maximum_c, soil_ready)):
        return insufficient(
            "flag", "Verified local sowing window, temperature or soil readiness missing."
        )
    assert on is not None and months is not None
    assert temperature_c is not None and minimum_c is not None and maximum_c is not None
    if (
        not months
        or any(m < 1 or m > 12 for m in months)
        or not all(map(math.isfinite, (temperature_c, minimum_c, maximum_c)))
        or minimum_c > maximum_c
    ):
        return invalid("flag")
    return available(
        float(
            on.month in months and minimum_c <= temperature_c <= maximum_c and soil_ready is True
        ),
        "flag",
        "Calendar and thermal candidate conditional on verified local scope and soil readiness.",
    )
