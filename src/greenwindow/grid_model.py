"""Weather-driven estimate of the Moroccan grid's carbon intensity.

Good enough to rank hours against each other, not to report emissions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

# Lifecycle emission factors in gCO2eq/kWh (IPCC AR5 medians; solar is a PV/CSP mix).
EMISSION_FACTORS = {"coal": 820.0, "gas": 490.0, "wind": 11.0, "solar": 40.0, "hydro": 24.0}

# relative to the daily average, by local hour (UTC+1)
DEMAND_PROFILE = [
    0.84, 0.81, 0.79, 0.78, 0.78, 0.80, 0.86, 0.93, 0.99, 1.02, 1.04, 1.05,
    1.05, 1.04, 1.03, 1.02, 1.02, 1.04, 1.10, 1.17, 1.20, 1.16, 1.06, 0.94,
]  # fmt: skip


@dataclass(frozen=True)
class GridParams:
    solar_mw: float = 900.0
    wind_mw: float = 2000.0
    hydro_mw: float = 250.0
    coal_mw: float = 4100.0
    coal_must_run: float = 0.55
    coal_max_load: float = 0.9
    demand_avg_mw: float = 4600.0
    utc_offset_hours: int = 1
    demand_profile: list[float] = field(default_factory=lambda: list(DEMAND_PROFILE))


@dataclass(frozen=True)
class Mix:
    demand: float
    solar: float
    wind: float
    hydro: float
    coal: float
    gas: float

    @property
    def intensity(self) -> float:
        emitted = (
            self.coal * EMISSION_FACTORS["coal"]
            + self.gas * EMISSION_FACTORS["gas"]
            + self.solar * EMISSION_FACTORS["solar"]
            + self.wind * EMISSION_FACTORS["wind"]
            + self.hydro * EMISSION_FACTORS["hydro"]
        )
        return emitted / (self.coal + self.gas + self.solar + self.wind + self.hydro)


def wind_capacity_factor(speed_ms: float) -> float:
    cut_in, rated, cut_out = 3.0, 12.0, 25.0
    if speed_ms < cut_in or speed_ms >= cut_out:
        return 0.0
    if speed_ms >= rated:
        return 1.0
    return ((speed_ms - cut_in) / (rated - cut_in)) ** 3


def solar_capacity_factor(irradiance_wm2: float) -> float:
    return max(0.0, min(irradiance_wm2 / 1000.0, 1.0)) * 0.85


def dispatch(
    moment: datetime, irradiance_wm2: float, wind_speeds_ms: list[float], params: GridParams
) -> Mix:
    local_hour = (moment + timedelta(hours=params.utc_offset_hours)).hour
    demand = params.demand_avg_mw * params.demand_profile[local_hour]

    solar = params.solar_mw * solar_capacity_factor(irradiance_wm2)
    wind_cf = sum(wind_capacity_factor(v) for v in wind_speeds_ms) / max(len(wind_speeds_ms), 1)
    wind = params.wind_mw * wind_cf
    hydro = params.hydro_mw

    coal_min = params.coal_mw * params.coal_must_run
    coal_max = params.coal_mw * params.coal_max_load
    residual = demand - solar - wind - hydro
    coal = min(max(residual, coal_min), coal_max)
    gas = max(residual - coal, 0.0)

    # coal stays at must-run, so surplus renewables are curtailed
    surplus = solar + wind + hydro + coal - demand
    if surplus > 0:
        renewables = solar + wind
        scale = max(renewables - surplus, 0.0) / renewables if renewables else 0.0
        solar, wind = solar * scale, wind * scale
    return Mix(demand, solar, wind, hydro, coal, gas)
