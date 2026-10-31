import math
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from sowcast.agronomy.catalogue import Citation, Threshold
from sowcast.agronomy.rules import RuleResult, available, insufficient, invalid

District = Literal["Bengaluru Rural", "Kolar", "Tumakuru", "Chikkaballapura", "Ramanagara"]


class AgronomyContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    district: District | None = None
    allow_fao_reference: bool = False
    planting_date: date | None = None
    water_stage: Literal["initial", "mid", "end"] | None = None
    stage_valid_from: date | None = None
    stage_valid_until: date | None = None
    paddy_standing_water: bool | None = None
    tomato_tall_staked: bool | None = None

    @model_validator(mode="after")
    def stage_interval(self) -> "AgronomyContext":
        if self.water_stage is not None:
            if self.stage_valid_from is None or self.stage_valid_until is None:
                raise ValueError("An observed stage requires an explicit validity interval")
            if self.stage_valid_from > self.stage_valid_until:
                raise ValueError("Stage validity interval is reversed")
            if self.water_stage == "end" and self.stage_valid_from != self.stage_valid_until:
                raise ValueError("Kc end describes an endpoint, not a constant late-season stage")
        elif self.stage_valid_from is not None or self.stage_valid_until is not None:
            raise ValueError("Stage dates require an observed stage")
        return self


class CropWaterBalance(BaseModel):
    coefficient: RuleResult
    crop_et_mm: RuleResult
    rainfall_shortfall_mm: RuleResult
    stage: str | None = None
    stage_basis: str | None = None
    citations: tuple[Citation, ...] = ()
    warning: str = (
        "Unadjusted FAO estimate, not locally calibrated crop need or an irrigation dose. "
        "Gross rain is not effective rain; soil storage, runoff and irrigation are excluded."
    )


def coefficient_for_day(
    crop: str,
    parameters: dict[str, Threshold],
    on: date,
    context: AgronomyContext,
) -> tuple[RuleResult, str | None, str | None, tuple[Citation, ...]]:
    missing = insufficient(
        "dimensionless", "Known stage, district and FAO reference consent required."
    )
    if not context.allow_fao_reference or context.district is None:
        return missing, None, None, ()
    used: list[str] = []

    def number(key: str) -> float | None:
        entry = parameters[key]
        if entry.enabled and isinstance(entry.value, float):
            used.append(key)
            return entry.value
        return None

    stage: str | None = context.water_stage
    basis = "Caller-supplied stage interval; not independently verified"
    value: float | None = None
    if stage is not None:
        assert context.stage_valid_from is not None and context.stage_valid_until is not None
        if not context.stage_valid_from <= on <= context.stage_valid_until:
            return (
                insufficient("dimensionless", "Date is outside supplied stage interval."),
                None,
                basis,
                (),
            )
        value = number(f"kc_{stage}")
    elif crop == "maize" and context.planting_date is not None:
        basis = "FAO Table 11 India dry/cool October example; projected, not observed stage"
        if context.planting_date.month != 10:
            return (
                insufficient("dimensionless", "Selected duration profile is for October maize."),
                None,
                basis,
                (),
            )
        lengths = [number(f"days_{name}") for name in ("initial", "development", "mid", "late")]
        if any(length is None or length <= 0 for length in lengths):
            return missing, None, basis, ()
        initial, development, mid, late = (float(v) for v in lengths if v is not None)
        day = (on - context.planting_date).days + 1
        if day < 1 or day > initial + development + mid + late:
            return (
                insufficient("dimensionless", "Date outside reference growth profile."),
                None,
                basis,
                (),
            )
        if day <= initial:
            stage, value = "initial", number("kc_initial")
        elif day <= initial + development:
            stage = "development"
            start, end = number("kc_initial"), number("kc_mid")
            if start is not None and end is not None:
                value = start + (day - initial) / development * (end - start)
        elif day <= initial + development + mid:
            stage, value = "mid", number("kc_mid")
        else:
            stage = "late"
            start, end = number("kc_mid"), number("kc_end")
            if start is not None and end is not None:
                value = start + (day - initial - development - mid) / late * (end - start)
    if crop == "paddy" and stage == "initial" and context.paddy_standing_water is not True:
        value = None
    if crop == "tomato" and stage == "mid" and context.tomato_tall_staked is not False:
        value = None
    citations = tuple(
        parameters[key].citation
        for key in dict.fromkeys(used)
        if parameters[key].citation is not None
    )
    references = tuple(citation for citation in citations if citation is not None)
    if value is None:
        return (
            insufficient(
                "dimensionless",
                "Crop/stage coefficient or its management conditions are unresolved.",
            ),
            stage,
            basis,
            references,
        )
    return (
        available(value, "dimensionless", "Unadjusted FAO-56 reference coefficient."),
        stage,
        basis,
        references,
    )


def crop_water_balance(
    rainfall_mm: float | None,
    et0_mm: float | None,
    coefficient: RuleResult,
) -> tuple[RuleResult, RuleResult]:
    if (
        rainfall_mm is None
        or et0_mm is None
        or coefficient.value is None
        or coefficient.status != "available"
    ):
        result = insufficient("mm", "Rainfall, ET0 or applicable stage coefficient missing.")
        return result, result
    if any(not math.isfinite(v) or v < 0 for v in (rainfall_mm, et0_mm, coefficient.value)):
        return invalid("mm"), invalid("mm")
    crop_et = available(coefficient.value * et0_mm, "mm", "Reference ETc = Kc × ET0.")
    if crop_et.value is None:
        return crop_et, invalid("mm")
    shortfall = available(
        max(0, crop_et.value - rainfall_mm),
        "mm",
        "Gross rainfall shortfall against reference ETc; not irrigation requirement.",
    )
    return crop_et, shortfall
