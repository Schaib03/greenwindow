from datetime import UTC, datetime

import pytest

from greenwindow.grid_model import (
    EMISSION_FACTORS,
    GridParams,
    dispatch,
    solar_capacity_factor,
    wind_capacity_factor,
)

NOON_UTC = datetime(2026, 6, 15, 11, tzinfo=UTC)
NIGHT_UTC = datetime(2026, 6, 15, 2, tzinfo=UTC)


@pytest.mark.parametrize(
    ("speed", "expected"), [(0, 0), (2.9, 0), (12, 1), (20, 1), (25, 0), (7.5, 0.125)]
)
def test_wind_power_curve(speed, expected):
    assert wind_capacity_factor(speed) == pytest.approx(expected)


def test_solar_is_capped():
    assert solar_capacity_factor(1200) == pytest.approx(0.85)
    assert solar_capacity_factor(-5) == 0


def test_sun_and_wind_lower_the_intensity():
    params = GridParams()
    calm_night = dispatch(NIGHT_UTC, 0, [2, 2, 2], params).intensity
    sunny_windy = dispatch(NOON_UTC, 950, [13, 12, 14], params).intensity
    assert sunny_windy < calm_night - 100


def test_intensity_stays_between_cleanest_and_dirtiest_source():
    params = GridParams()
    for moment, irradiance, wind in [(NIGHT_UTC, 0, [0]), (NOON_UTC, 1000, [15, 15, 15])]:
        mix = dispatch(moment, irradiance, wind, params)
        assert EMISSION_FACTORS["wind"] <= mix.intensity <= EMISSION_FACTORS["coal"]


def test_supply_matches_demand_when_renewables_overshoot():
    params = GridParams(wind_mw=9000, solar_mw=5000)
    mix = dispatch(NOON_UTC, 1000, [14, 14, 14], params)
    supply = mix.coal + mix.gas + mix.solar + mix.wind + mix.hydro
    assert supply == pytest.approx(mix.demand)
    assert mix.coal == pytest.approx(params.coal_mw * params.coal_must_run)
    assert mix.gas == 0


def test_evening_peak_needs_gas():
    params = GridParams()
    evening = datetime(2026, 1, 10, 19, tzinfo=UTC)  # 20h local
    mix = dispatch(evening, 0, [3, 3, 3], params)
    assert mix.gas > 0
