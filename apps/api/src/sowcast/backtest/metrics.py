import math
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sowcast.sources.history import LEADS, HistoryEvidence, HistorySource
from sowcast.sources.models import Location


class RainScore(BaseModel):
    definition: Literal["gt0", "ge1"]
    event: str
    paired_days: int
    missing_days: int
    correct_days: int
    accuracy: float | None
    accuracy_ci95: tuple[float, float] | None
    era5_rain_days: int
    era5_rain_share: float | None
    majority_class: Literal["rain", "no_rain", "tie"] | None
    majority_correct_days: int
    majority_accuracy: float | None


def wilson95(correct: int, total: int) -> tuple[float, float] | None:
    if total < 0 or not 0 <= correct <= total:
        raise ValueError("Invalid binomial counts")
    if not total:
        return None
    z = 1.959963984540054
    p = correct / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def rain_score(
    totals: tuple[tuple[float, float], ...], definition: Literal["gt0", "ge1"]
) -> RainScore:
    if (
        definition not in {"gt0", "ge1"}
        or len(totals) > 60
        or any(not math.isfinite(value) or value < 0 for pair in totals for value in pair)
    ):
        raise ValueError("Invalid daily precipitation comparison")
    predicted = [p > 0 if definition == "gt0" else p >= 1 for p, _ in totals]
    observed = [o > 0 if definition == "gt0" else o >= 1 for _, o in totals]
    days = len(totals)
    correct = sum(p == o for p, o in zip(predicted, observed, strict=True))
    wet = sum(observed)
    majority = max(wet, days - wet)
    majority_class: Literal["rain", "no_rain", "tie"] | None = (
        None if not days else "tie" if wet * 2 == days else "rain" if wet * 2 > days else "no_rain"
    )
    return RainScore(
        definition=definition,
        event="Daily precipitation strictly greater than 0 mm."
        if definition == "gt0"
        else "Daily precipitation at least 1 mm.",
        paired_days=days,
        missing_days=60 - days,
        correct_days=correct,
        accuracy=correct / days if days else None,
        accuracy_ci95=wilson95(correct, days),
        era5_rain_days=wet,
        era5_rain_share=wet / days if days else None,
        majority_class=majority_class,
        majority_correct_days=majority,
        majority_accuracy=majority / days if days else None,
    )


class LeadScore(BaseModel):
    lead_days: int
    lead_hours: int
    temperature_mae_c: float | None
    temperature_pairs: int
    temperature_missing_hours: int
    rain_correct_days: int
    rain_pairs: int
    rain_missing_days: int
    rain_accuracy: float | None
    era5_rain_days: int
    era5_rain_share: float | None
    majority_correct_days: int
    majority_accuracy: float | None
    rain_definitions: tuple[RainScore, ...]
    rain_brier: float | None = None
    brier_reason: str = "No true precipitation probabilities are provided by these requests."


class BacktestResult(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    api_version: Literal["1.0"] = "1.0"
    methodology_version: Literal["1.1.0"] = "1.1.0"
    location: Location
    start_date: date
    end_date: date
    computed_at: datetime
    is_stale: bool = False
    data_status: Literal["complete", "partial", "empty"]
    forecast_model: Literal["gfs_global"] = "gfs_global"
    reference_model: Literal["era5"] = "era5"
    day_basis: Literal["UTC"] = "UTC"
    expected_hours: Literal[1440] = 1440
    expected_days: Literal[60] = 60
    rain_event: str = "Daily precipitation strictly greater than 0 mm."
    uncertainty_note: str
    scores: tuple[LeadScore, ...]
    sources: tuple[HistorySource, ...]
    limitation: str = (
        "GFS fixed-lead forecasts compared with ERA5 gridded reanalysis, not plot observations. "
        "This does not measure the live best-match forecast blend, crop outcomes or alert skill. "
        "The source grids differ. Rain days require all 24 UTC hourly values in both series. "
        "The window ends six days before today to allow ERA5 publication."
    )


def brier_score(probabilities: tuple[float, ...], outcomes: tuple[bool, ...]) -> float | None:
    if len(probabilities) != len(outcomes):
        raise ValueError("Probabilities and outcomes must align")
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities):
        raise ValueError("Probabilities must be finite fractions in [0, 1]")
    return (
        sum((p - float(o)) ** 2 for p, o in zip(probabilities, outcomes, strict=True))
        / len(probabilities)
        if probabilities
        else None
    )


def uncertainty_note(scores: tuple[LeadScore, ...]) -> str:
    counts = [score.rain_pairs for score in scores]
    low, high = min(counts), max(counts)
    sample = (
        "With about 59 paired days, differences of a few days between leads are small "
        "relative to sampling uncertainty. "
        if low >= 59
        else "Sparse or absent paired days limit what these comparisons can establish. "
    )
    return (
        f"Each GFS model lead has {low}–{high} paired rain days out of 60. "
        + sample
        + "No lead ranking is established. The 95% Wilson intervals assume independent "
        "days; weather correlation can widen uncertainty. These marginal intervals are "
        "not a paired test between leads."
    )


def assess(
    forecast: HistoryEvidence,
    reference: HistoryEvidence,
    start: date,
    end: date,
    computed_at: datetime,
) -> BacktestResult:
    if forecast.location != reference.location or forecast.is_stale or reference.is_stale:
        raise ValueError("Fresh evidence for the same requested plot is required")
    if forecast.model != "gfs_global" or reference.model != "era5":
        raise ValueError("Unexpected comparison models")
    if (end - start).days != 59:
        raise ValueError("Comparison requires 60 days")
    first = datetime.combine(start, time(), UTC)
    hours = tuple(first + timedelta(hours=n) for n in range(1440))
    indices = [{t: i for i, t in enumerate(s.hourly.time)} for s in (forecast, reference)]
    scores = []
    for lead in LEADS:
        paired: dict[str, dict[datetime, tuple[float, float]]] = {}
        for field, unit in (("temperature_2m", "°C"), ("precipitation", "mm")):
            forecast_field = f"{field}_previous_day{lead}"
            if (
                forecast.hourly.units.get(forecast_field) != unit
                or reference.hourly.units.get(field) != unit
            ):
                raise ValueError("Metric input units do not match")
            values = {}
            valid_hours = (
                tuple(h + timedelta(hours=1) for h in hours) if field == "precipitation" else hours
            )
            for hour in valid_hours:
                a, b = indices[0].get(hour), indices[1].get(hour)
                if a is None or b is None:
                    continue
                predicted = forecast.hourly.values[forecast_field][a]
                observed = reference.hourly.values[field][b]
                if predicted is not None and observed is not None:
                    values[hour] = (predicted, observed)
            paired[field] = values
        temperatures = paired["temperature_2m"]
        rain = paired["precipitation"]
        daily_totals = []
        for day in range(60):
            daily = [rain.get(first + timedelta(days=day, hours=h)) for h in range(1, 25)]
            if any(pair is None for pair in daily):
                continue
            complete = [pair for pair in daily if pair is not None]
            daily_totals.append(
                (math.fsum(pair[0] for pair in complete), math.fsum(pair[1] for pair in complete))
            )
        definitions = tuple(rain_score(tuple(daily_totals), d) for d in ("gt0", "ge1"))
        primary = definitions[0]
        count = len(temperatures)
        scores.append(
            LeadScore(
                lead_days=lead,
                lead_hours=lead * 24,
                temperature_mae_c=sum(abs(a - b) for a, b in temperatures.values()) / count
                if count
                else None,
                temperature_pairs=count,
                temperature_missing_hours=1440 - count,
                rain_correct_days=primary.correct_days,
                rain_pairs=primary.paired_days,
                rain_missing_days=primary.missing_days,
                rain_accuracy=primary.accuracy,
                era5_rain_days=primary.era5_rain_days,
                era5_rain_share=primary.era5_rain_share,
                majority_correct_days=primary.majority_correct_days,
                majority_accuracy=primary.majority_accuracy,
                rain_definitions=definitions,
            )
        )
    status: Literal["complete", "partial", "empty"] = (
        "empty"
        if not any(s.temperature_pairs or s.rain_pairs for s in scores)
        else "partial"
        if any(s.temperature_missing_hours or s.rain_missing_days for s in scores)
        else "complete"
    )
    return BacktestResult(
        location=forecast.location,
        start_date=start,
        end_date=end,
        computed_at=computed_at,
        data_status=status,
        scores=tuple(scores),
        uncertainty_note=uncertainty_note(tuple(scores)),
        sources=tuple(
            HistorySource.model_validate(s.model_dump(exclude={"hourly"}))
            for s in (forecast, reference)
        ),
    )
