from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Point:
    start: datetime
    intensity: float  # gCO2eq/kWh


class Forecast:
    """Piecewise-constant carbon intensity: each point holds until the next one."""

    def __init__(self, points: list[Point], step: timedelta, zone: str, source: str):
        if not points:
            raise ValueError("empty forecast")
        self.points = sorted(points, key=lambda p: p.start)
        self.step = step
        self.zone = zone
        self.source = source
        self._starts = [p.start for p in self.points]

    @property
    def start(self) -> datetime:
        return self.points[0].start

    @property
    def end(self) -> datetime:
        return self.points[-1].start + self.step

    def covers(self, start: datetime, end: datetime) -> bool:
        return self.start <= start and end <= self.end

    def intensity_at(self, moment: datetime) -> float:
        if not self.start <= moment < self.end:
            raise ValueError(f"{moment.isoformat()} is outside the forecast")
        return self.points[bisect_right(self._starts, moment) - 1].intensity

    def average(self, start: datetime, end: datetime) -> float:
        if not self.covers(start, end) or end <= start:
            raise ValueError("window is outside the forecast")
        total = 0.0
        index = bisect_right(self._starts, start) - 1
        cursor = start
        while cursor < end:
            point = self.points[index]
            next_start = self.points[index + 1].start if index + 1 < len(self.points) else self.end
            segment_end = min(next_start, end)
            total += point.intensity * (segment_end - cursor).total_seconds()
            cursor = segment_end
            index += 1
        return total / (end - start).total_seconds()

    def window(self, start: datetime, end: datetime) -> list[Point]:
        return [p for p in self.points if start <= p.start < end]
