import math
from datetime import date

import pytest

from sowcast.agronomy.catalogue import load_catalogue
from sowcast.agronomy.rules import (
    frost_risk,
    growing_degree_days,
    heat_stress_days,
    rainfall_deficit_against_et0,
    sowing_window_suitability,
    waterlogging_risk,
)


def test_catalogue_and_every_disabled_threshold():
    catalogue = load_catalogue()
    assert set(catalogue.crops) == {"ragi", "paddy", "maize", "tur", "groundnut", "tomato"}
    for parameters in catalogue.crops.values():
        for parameter in parameters.values():
            if parameter.enabled:
                assert parameter.citation.url.startswith("https://")
                assert parameter.citation.locator
            else:
                assert parameter.value is None
                assert parameter.reason


def test_every_enabled_heat_threshold_boundary():
    for parameters in load_catalogue().crops.values():
        threshold = parameters["heat_above_c"]
        if threshold.enabled:
            value = float(threshold.value)
            assert heat_stress_days((math.nextafter(value, -math.inf),), value).value == 0
            assert heat_stress_days((value,), value).value == 0
            assert heat_stress_days((math.nextafter(value, math.inf),), value).value == 1


@pytest.mark.parametrize("base", [-5, 0, 10, 20])
def test_gdd_boundary_and_monotonicity(base):
    assert growing_degree_days(base, base, base).value == 0
    assert growing_degree_days(base - 2, base - 1, base).value == 0
    previous = 0
    for delta in range(30):
        result = growing_degree_days(base + delta, base + delta, base)
        assert result.value == delta
        assert result.value >= previous
        previous = result.value
    assert growing_degree_days(10, 9, base).status == "invalid_input"


def test_heat_count_additivity_and_threshold_monotonicity():
    samples = tuple(float(t) for t in range(-10, 50))
    previous = len(samples)
    for threshold in range(-10, 50):
        count = heat_stress_days(samples, threshold).value
        left = heat_stress_days(samples[:20], threshold).value
        right = heat_stress_days(samples[20:], threshold).value
        assert count == left + right
        assert count <= previous
        previous = count


@pytest.mark.parametrize("threshold", [-5, 0, 8])
def test_frost_strict_boundary(threshold):
    assert frost_risk(math.nextafter(threshold, -math.inf), threshold).value == 1
    assert frost_risk(threshold, threshold).value == 0
    assert frost_risk(math.nextafter(threshold, math.inf), threshold).value == 0


def test_water_deficit_properties():
    for rain in range(20):
        previous = 0
        for et0 in range(20):
            result = rainfall_deficit_against_et0((rain,), (et0,))
            assert result.value == max(0, et0 - rain)
            assert result.value >= previous
            previous = result.value
    assert rainfall_deficit_against_et0((2, 3), (4, 5)).value == 4
    assert rainfall_deficit_against_et0((-1,), (2,)).status == "invalid_input"
    assert rainfall_deficit_against_et0((1,), (1, 2)).status == "invalid_input"


def test_waterlogging_threshold_and_monotonicity():
    for threshold in range(5):
        boundary = 2 + 3 + 4 + threshold
        assert waterlogging_risk(boundary, 2, 3, 4, threshold).value == 0
        assert waterlogging_risk(boundary + 0.1, 2, 3, 4, threshold).value == 1
        for storage in range(10):
            expected = float(10 - 2 - 3 - storage > threshold)
            assert waterlogging_risk(10, 2, 3, storage, threshold).value == expected


def test_sowing_boundaries():
    on = date(2026, 6, 1)
    for temperature, expected in [(9, 0), (10, 1), (15, 1), (20, 1), (21, 0)]:
        assert sowing_window_suitability(on, (6,), temperature, 10, 20, True).value == expected
    assert sowing_window_suitability(on, (5,), 15, 10, 20, True).value == 0
    assert sowing_window_suitability(on, (6,), 15, 10, 20, False).value == 0
    assert sowing_window_suitability(on, (13,), 15, 10, 20, True).status == "invalid_input"


@pytest.mark.parametrize(
    "function,arguments",
    [
        (growing_degree_days, (10, 20, 5)),
        (frost_risk, (2, 0)),
        (waterlogging_risk, (10, 2, 3, 1, 0)),
        (sowing_window_suitability, (date(2026, 6, 1), (6,), 15, 10, 20, True)),
    ],
)
def test_every_scalar_input_missing(function, arguments):
    for index in range(len(arguments)):
        values = list(arguments)
        values[index] = None
        result = function(*values)
        assert result.status == "insufficient_data"
        assert result.value is None


@pytest.mark.parametrize(
    "result",
    [
        heat_stress_days((), 20),
        heat_stress_days((20, None), 20),
        heat_stress_days((20,), None),
        rainfall_deficit_against_et0((), ()),
        rainfall_deficit_against_et0((None,), (2,)),
        rainfall_deficit_against_et0((2,), (None,)),
    ],
)
def test_missing_series_never_produces_default(result):
    assert result.status == "insufficient_data"
    assert result.value is None


@pytest.mark.parametrize(
    "result",
    [
        growing_degree_days(0, math.inf, 0),
        frost_risk(math.nan, 0),
        heat_stress_days((math.inf,), 1),
        waterlogging_risk(-1, 1, 1, 1, 0),
        rainfall_deficit_against_et0((math.nan,), (1,)),
    ],
)
def test_nonfinite_or_invalid_inputs(result):
    assert result.status == "invalid_input"
    assert result.value is None
