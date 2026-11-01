import asyncio
import json
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from sowcast.api.app import create_app
from sowcast.backtest.metrics import (
    assess,
    brier_score,
    rain_score,
    reliability_sentences,
    wilson95,
)
from sowcast.backtest.service import BacktestService
from sowcast.backtest.store import BacktestStore
from sowcast.sources.history import HistoryClient
from sowcast.sources.models import Location, SourceError
from sowcast.sources.transport import SourceTransport

ROOT = Path(__file__).parent / "recorded"
META = json.loads((ROOT / "previous_runs.meta.json").read_text(encoding="utf-8"))
START, END = date.fromisoformat(META["start_date"]), date.fromisoformat(META["end_date"])
NOW = datetime.combine(END + timedelta(days=6), datetime.min.time(), UTC)
LOCATION = Location(latitude=12.97, longitude=77.59)


def payload(name):
    return json.loads((ROOT / f"{name}.json").read_text(encoding="utf-8"))


def respond(request):
    name = "previous_runs" if request.url.host.startswith("previous-runs") else "era5"
    return httpx.Response(200, json=payload(name))


async def evidence():
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = HistoryClient(SourceTransport(http))
        return (
            await client.fetch(LOCATION, START, END, "previous"),
            await client.fetch(LOCATION, START, END, "archive"),
        )


@pytest.mark.asyncio
async def test_real_recorded_alignment_counts_and_formulas():
    forecast, reference = await evidence()
    result = assess(forecast, reference, START, END, NOW)
    assert result.data_status == "partial" and len(result.scores) == 7
    for score in result.scores:
        assert score.temperature_pairs == 1440 and score.rain_pairs == 59
        assert score.temperature_missing_hours == 0 and score.rain_missing_days == 1
        predicted = forecast.hourly.values[f"temperature_2m_previous_day{score.lead_days}"]
        actual = reference.hourly.values["temperature_2m"]
        assert score.temperature_mae_c == pytest.approx(
            sum(abs(a - b) for a, b in zip(predicted[:1440], actual[:1440])) / 1440
        )
        assert 0 <= score.rain_accuracy <= 1 and score.rain_brier is None


@pytest.mark.asyncio
async def test_missing_values_not_zero_and_full_day_requirement():
    forecast, reference = await evidence()
    values = dict(forecast.hourly.values)
    for field in values:
        values[field] = values[field][:1] + (None,) + values[field][2:]
    changed = forecast.model_copy(
        update={"hourly": forecast.hourly.model_copy(update={"values": values})}
    )
    score = assess(changed, reference, START, END, NOW).scores[0]
    assert score.temperature_pairs == 1439 and score.temperature_missing_hours == 1
    assert score.rain_pairs == 58 and score.rain_missing_days == 2
    empty = changed.model_copy(
        update={
            "hourly": changed.hourly.model_copy(
                update={"values": {key: (None,) * len(changed.hourly.time) for key in values}}
            )
        }
    )
    result = assess(empty, reference, START, END, NOW)
    assert result.data_status == "empty"
    assert "0–0 paired rain days" in result.uncertainty_note
    assert "about 59" not in result.uncertainty_note
    assert all(s.temperature_mae_c is None and s.rain_accuracy is None for s in result.scores)


@pytest.mark.asyncio
async def test_alignment_uses_valid_time_instead_of_array_position():
    forecast, reference = await evidence()
    shifted = forecast.model_copy(
        update={
            "hourly": forecast.hourly.model_copy(
                update={
                    "time": forecast.hourly.time[:1] + forecast.hourly.time[2:],
                    "values": {
                        key: values[:1] + values[2:]
                        for key, values in forecast.hourly.values.items()
                    },
                }
            )
        }
    )
    result = assess(shifted, reference, START, END, NOW)
    score = result.scores[0]
    expected = (
        sum(
            abs(a - b)
            for a, b in zip(
                forecast.hourly.values["temperature_2m_previous_day1"][:1]
                + forecast.hourly.values["temperature_2m_previous_day1"][2:1440],
                reference.hourly.values["temperature_2m"][:1]
                + reference.hourly.values["temperature_2m"][2:1440],
            )
        )
        / 1439
    )
    assert score.temperature_pairs == 1439 and score.rain_pairs == 58
    assert score.temperature_mae_c == pytest.approx(expected)
    with pytest.raises(ValueError, match="same requested plot"):
        assess(
            forecast,
            reference.model_copy(update={"location": Location(latitude=13, longitude=77)}),
            START,
            END,
            NOW,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [0, 0.0001, 0.1, 1, 100])
async def test_rain_event_boundary(amount):
    forecast, reference = await evidence()
    fv = {
        key: (amount,) * len(forecast.hourly.time) if key.startswith("precipitation") else values
        for key, values in forecast.hourly.values.items()
    }
    rv = dict(reference.hourly.values) | {"precipitation": (0.0,) * len(reference.hourly.time)}
    result = assess(
        forecast.model_copy(update={"hourly": forecast.hourly.model_copy(update={"values": fv})}),
        reference.model_copy(update={"hourly": reference.hourly.model_copy(update={"values": rv})}),
        START,
        END,
        NOW,
    )
    assert all(
        s.rain_pairs == 60 and s.rain_correct_days == (60 if amount == 0 else 0)
        for s in result.scores
    )


@pytest.mark.asyncio
async def test_midnight_precipitation_belongs_to_preceding_day():
    forecast, reference = await evidence()
    fv = {
        key: (0.0,) * len(forecast.hourly.time) if key.startswith("precipitation") else values
        for key, values in forecast.hourly.values.items()
    }
    rv = dict(reference.hourly.values) | {"precipitation": (0.0,) * len(reference.hourly.time)}
    for key in fv:
        if key.startswith("precipitation"):
            values = list(fv[key])
            values[0] = 5.0
            values[24] = 1.0
            fv[key] = tuple(values)
    result = assess(
        forecast.model_copy(update={"hourly": forecast.hourly.model_copy(update={"values": fv})}),
        reference.model_copy(update={"hourly": reference.hourly.model_copy(update={"values": rv})}),
        START,
        END,
        NOW,
    )
    assert all(s.rain_pairs == 60 and s.rain_correct_days == 59 for s in result.scores)


@pytest.mark.asyncio
async def test_expired_lease_can_be_reclaimed_without_old_owner_overwrite(tmp_path, monkeypatch):
    import sowcast.backtest.store as module

    store = BacktestStore(str(tmp_path / "jobs.sqlite3"))
    now = [1000.0]
    monkeypatch.setattr(module.time, "time", lambda: now[0])
    assert await store.claim("plot", "old") is True
    now[0] += 301
    assert await store.claim("plot", "new") is True
    forecast, reference = await evidence()
    result = assess(forecast, reference, START, END, NOW)
    await store.finish("plot", "old", result)
    assert await store.claim("plot", "third") is False
    await store.finish("plot", "new", result)
    assert await store.claim("plot", "third") == result
    now[0] += 86401
    assert await store.claim("plot", "third") is True


def test_brier_requires_probabilities_and_aligned_outcomes():
    assert brier_score((), ()) is None
    assert brier_score((0, 1), (False, True)) == 0
    assert brier_score((1, 0), (False, True)) == 1
    assert brier_score((0.5, 0.5), (False, True)) == 0.25
    for probabilities in ((-0.1,), (1.1,), (float("nan"),), (float("inf"),)):
        with pytest.raises(ValueError):
            brier_score(probabilities, (True,))
    with pytest.raises(ValueError):
        brier_score((0.5,), ())


def test_rain_definitions_share_the_same_sample_and_majority_baseline():
    totals = ((0.1, 0.1), (0, 0.9), (1, 1), (0, 0))
    gt0, ge1 = rain_score(totals, "gt0"), rain_score(totals, "ge1")
    assert gt0.paired_days == ge1.paired_days == 4
    assert gt0.era5_rain_days == 3 and gt0.era5_rain_share == 0.75
    assert gt0.majority_class == "rain" and gt0.majority_accuracy == 0.75
    assert gt0.correct_days == 3 and gt0.accuracy == 0.75
    assert ge1.era5_rain_days == 1 and ge1.era5_rain_share == 0.25
    assert ge1.majority_class == "no_rain" and ge1.majority_accuracy == 0.75
    assert ge1.correct_days == 4 and ge1.accuracy == 1
    assert rain_score(((0, 0), (1, 1)), "ge1").majority_class == "tie"


@pytest.mark.parametrize("value,rain", [(0, False), (0.999999, False), (1, True), (1.000001, True)])
def test_one_mm_definition_is_inclusive(value, rain):
    score = rain_score(((value, value),), "ge1")
    assert score.era5_rain_days == int(rain) and score.accuracy == 1


def test_empty_baselines_and_invalid_amounts():
    for definition in ("gt0", "ge1"):
        score = rain_score((), definition)
        assert score.era5_rain_share is score.majority_accuracy is score.accuracy_ci95 is None
        assert score.majority_class is None and score.paired_days == 0
    for value in (-1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            rain_score(((value, 0),), "ge1")


def test_wilson_reference_values_and_properties():
    assert wilson95(50, 100) == pytest.approx((0.4038315304, 0.5961684696))
    assert wilson95(0, 1) == pytest.approx((0, 0.7934506856))
    assert wilson95(0, 0) is None
    for total in range(1, 61):
        for correct in range(total + 1):
            low, high = wilson95(correct, total)
            assert 0 <= low <= correct / total + 1e-12
            assert correct / total - 1e-12 <= high <= 1
            other_low, other_high = wilson95(total - correct, total)
            assert low == pytest.approx(1 - other_high)
            assert high == pytest.approx(1 - other_low)
    for args in ((-1, 10), (11, 10), (0, -1)):
        with pytest.raises(ValueError):
            wilson95(*args)


@pytest.mark.asyncio
async def test_baseline_denominator_changes_with_lead_coverage():
    forecast, reference = await evidence()
    values = dict(forecast.hourly.values)
    values["precipitation_previous_day1"] = (
        values["precipitation_previous_day1"][:1]
        + (None,)
        + values["precipitation_previous_day1"][2:]
    )
    changed = forecast.model_copy(
        update={"hourly": forecast.hourly.model_copy(update={"values": values})}
    )
    result = assess(changed, reference, START, END, NOW)
    for definition in range(2):
        first, second = (
            result.scores[0].rain_definitions[definition],
            result.scores[1].rain_definitions[definition],
        )
        assert first.paired_days == 58 and second.paired_days == 59
        assert first.era5_rain_share == first.era5_rain_days / 58
        assert first.majority_accuracy == max(first.era5_rain_days, 58 - first.era5_rain_days) / 58
        assert first.accuracy_ci95 == wilson95(first.correct_days, 58)


@pytest.mark.asyncio
async def test_service_coalescing_and_persistence_across_instances(tmp_path):
    calls = []

    async def delayed(request):
        calls.append(request.url.host)
        await asyncio.sleep(0.01)
        return respond(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(delayed)) as http:
        client = HistoryClient(SourceTransport(http))
        store = BacktestStore(str(tmp_path / "jobs.sqlite3"))
        service = BacktestService(client, client, store, lambda: NOW)
        results = await asyncio.gather(*(service.get(LOCATION) for _ in range(10)))
        assert len(calls) == 2 and all(r == results[0] for r in results)
        other = BacktestService(client, client, store, lambda: NOW)
        assert await other.get(LOCATION) == results[0]
        assert len(calls) == 2
        assert results[0].sources[0].grid_location != results[0].sources[1].grid_location


@pytest.mark.asyncio
async def test_atomic_job_lease_and_owner(tmp_path):
    path = str(tmp_path / "jobs.sqlite3")
    a, b = BacktestStore(path), BacktestStore(path)
    results = await asyncio.gather(a.claim("plot", "a"), b.claim("plot", "b"))
    assert sorted(results) == [False, True]
    owner = "a" if results[0] else "b"
    await a.release("plot", "wrong-owner")
    assert await b.claim("plot", "c") is False
    await a.release("plot", owner)
    assert await b.claim("plot", "c") is True


@pytest.mark.asyncio
async def test_api_recorded_and_typed_source_failure():
    app = create_app(httpx.MockTransport(respond))
    async with app.router.lifespan_context(app):
        app.state.sources.backtest.clock = lambda: NOW
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            response = await http.get("/v1/backtests?latitude=12.97&longitude=77.59")
            assert response.status_code == 200
            assert response.json()["scores"][0]["rain_pairs"] == 59
            assert response.headers["x-request-id"]
            assert (await http.get("/v1/backtests?latitude=nan&longitude=77")).status_code == 422

    def failure(request):
        raise httpx.ConnectError("private details", request=request)

    app = create_app(httpx.MockTransport(failure))
    async with app.router.lifespan_context(app):
        app.state.sources.backtest.clock = lambda: NOW
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            response = await http.get("/v1/backtests?latitude=13&longitude=78")
            assert response.status_code == 503
            assert response.json()["error"]["retryable"] is True
            assert "private" not in response.text and "scores" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["unit", "negative", "duplicate", "offset"])
async def test_source_rejects_bad_units_values_or_times(change):
    data = payload("era5")
    if change == "unit":
        data["hourly_units"]["precipitation"] = "inch"
    if change == "negative":
        data["hourly"]["precipitation"][0] = -1
    if change == "duplicate":
        data["hourly"]["time"][1] = data["hourly"]["time"][0]
    if change == "offset":
        data["utc_offset_seconds"] = 3600
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data))
    ) as http:
        client = HistoryClient(SourceTransport(http))
        with pytest.raises(SourceError, match="schema or units"):
            await client.fetch(LOCATION, START, END, "archive")


@pytest.mark.parametrize("latitude", ["nan", "91", "inf"])
def test_cli_invalid_coordinates_are_readable_without_traceback(latitude):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sowcast",
            "backtest",
            "--latitude",
            latitude,
            "--longitude",
            "77.59",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "Coordinates must be finite" in result.stderr and "Traceback" not in result.stderr


@pytest.mark.asyncio
async def test_backtest_tool_has_citable_windowed_metrics():
    from sowcast.agent.service import tool_facts
    from sowcast.agent.tools import PlotContext, ToolCall, ToolRunner
    from sowcast.guardrails.claims import Claim, verify_quantities

    app = create_app(httpx.MockTransport(respond))
    async with app.router.lifespan_context(app):
        app.state.sources.backtest.clock = lambda: NOW
        runner = ToolRunner(
            app.state.sources,
            app.state.catalogue,
            PlotContext(latitude=12.97, longitude=77.59, crop="maize", sowing_status="not_sown"),
        )
        result = await runner.execute(ToolCall(name="get_backtest"))
        assert result["status"] == "partial"
        facts = tool_facts("get_backtest", result)
        fact = facts["backtest:lead1:rain_pairs"]
        assert fact.window_start == str(START) and fact.window_end == str(END)
        assert fact.supporting_urls and fact.value == 59
        secondary = facts["backtest:lead1:ge1:majority_accuracy"]
        assert secondary.value == pytest.approx(41 / 59)
        assert "GFS model 24h" in secondary.label and "n=59" in secondary.label
        assert facts["backtest:lead1:gt0:era5_rain_share"].value == pytest.approx(36 / 59)
        claim = Claim(
            text="59 days",
            evidence_id=fact.id,
            date=fact.date,
            latitude=fact.latitude,
            longitude=fact.longitude,
        )
        assert verify_quantities((claim,), facts).passed
        assert not verify_quantities((claim.model_copy(update={"date": str(START)}),), facts).passed


@pytest.mark.asyncio
async def test_cached_lookup_is_read_only_and_never_requests_sources(tmp_path):
    calls = []

    def counting(request):
        calls.append(request.url.host)
        return respond(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(counting)) as http:
        client = HistoryClient(SourceTransport(http))
        store = BacktestStore(str(tmp_path / "jobs.sqlite3"))
        service = BacktestService(client, client, store, lambda: NOW)
        assert await service.cached(LOCATION) is None
        assert calls == []
        result = await service.get(LOCATION)
        assert len(calls) == 2
        assert await service.cached(LOCATION) == result
        assert await service.cached(Location(latitude=13, longitude=78)) is None
        assert len(calls) == 2


@pytest.mark.asyncio
async def test_reliability_sentences_use_only_score_fields():
    forecast, reference = await evidence()
    result = assess(forecast, reference, START, END, NOW)
    gt0 = result.scores[2].rain_definitions[0]
    days = ((3, date(2026, 11, 4)), (9, date(2026, 11, 10)))
    sentences = reliability_sentences(result, days)
    assert len(sentences) == 1
    assert sentences[0].startswith("2026-11-04: GFS model 72h rain/no-rain (>0 mm)")
    assert f"on {gt0.correct_days} of {gt0.paired_days} paired days" in sentences[0]
    assert f"baseline {gt0.majority_correct_days} of {gt0.paired_days}" in sentences[0]
    assert f"{START} to {END}" in sentences[0]
    assert "different model from the plan forecast" in sentences[0]
    assert reliability_sentences(result.model_copy(update={"is_stale": True}), days) == ()
    assert reliability_sentences(result.model_copy(update={"data_status": "empty"}), days) == ()
