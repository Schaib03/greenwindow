from __future__ import annotations

from datetime import datetime, timedelta

from greenwindow.durations import parse_duration
from greenwindow.forecast import Forecast, Point


class StaticProvider:
    """A fixed forecast, for tests and demos: "step=10m;520,480,200,200,510".

    Values start at the anchor time (rounded down to the step), so the same
    string always describes "now, in 10 minutes, in 20 minutes...".
    """

    name = "static"

    def __init__(self, values: list[float], step: timedelta, anchor: datetime):
        self.values = values
        self.step = step
        seconds = int(step.total_seconds())
        epoch = int(anchor.timestamp())
        self.anchor = anchor - timedelta(seconds=epoch % seconds, microseconds=anchor.microsecond)

    @classmethod
    def parse(cls, spec: str, anchor: datetime) -> StaticProvider:
        step = timedelta(hours=1)
        values_part = spec
        if ";" in spec:
            header, values_part = spec.split(";", 1)
            key, _, value = header.partition("=")
            if key.strip() != "step":
                raise ValueError(f"expected step=..., got {header!r}")
            step = parse_duration(value)
        values = [float(v) for v in values_part.split(",") if v.strip()]
        if not values:
            raise ValueError("static forecast needs at least one value")
        return cls(values, step, anchor)

    def forecast(self, zone: str) -> Forecast:
        points = [Point(self.anchor + i * self.step, v) for i, v in enumerate(self.values)]
        return Forecast(points, self.step, zone, self.name)
