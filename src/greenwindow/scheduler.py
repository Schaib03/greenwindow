from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from greenwindow.forecast import Forecast

# not worth waiting hours for a 1% gain
DEFAULT_MIN_IMPROVEMENT = 0.05


@dataclass(frozen=True)
class Plan:
    start: datetime
    intensity: float
    intensity_now: float
    reason: str

    @property
    def delayed(self) -> bool:
        return self.reason == "greener-window"

    def avoided_grams(self, energy_kwh: float) -> float:
        return max(self.intensity_now - self.intensity, 0.0) * energy_kwh


def energy_kwh(power_watts: float, duration: timedelta) -> float:
    return power_watts * duration.total_seconds() / 3600 / 1000


def _candidates(forecast: Forecast, now: datetime, latest_start: datetime):
    yield now
    step = min(forecast.step, timedelta(minutes=15))
    cursor = forecast.start
    while cursor <= now:
        cursor += step
    while cursor <= latest_start:
        yield cursor
        cursor += step


def plan(
    forecast: Forecast,
    now: datetime,
    duration: timedelta,
    deadline: datetime,
    max_intensity: float | None = None,
    min_improvement: float = DEFAULT_MIN_IMPROVEMENT,
) -> Plan:
    run_now_end = now + duration
    if not forecast.covers(now, run_now_end):
        intensity = forecast.intensity_at(now) if forecast.start <= now < forecast.end else 0.0
        return Plan(now, intensity, intensity, "forecast-too-short")

    now_avg = forecast.average(now, run_now_end)
    if max_intensity is not None and now_avg <= max_intensity:
        return Plan(now, now_avg, now_avg, "below-threshold")

    latest_start = min(deadline, forecast.end) - duration
    if latest_start <= now:
        return Plan(now, now_avg, now_avg, "no-slack")

    best_start, best_avg = now, now_avg
    for start in _candidates(forecast, now, latest_start):
        avg = forecast.average(start, start + duration)
        if avg < best_avg:
            best_start, best_avg = start, avg

    if best_start == now or (now_avg - best_avg) / now_avg < min_improvement:
        return Plan(now, now_avg, now_avg, "already-green")
    return Plan(best_start, best_avg, now_avg, "greener-window")
