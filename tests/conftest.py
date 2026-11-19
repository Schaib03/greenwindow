from datetime import UTC, datetime, timedelta

import pytest

from greenwindow.forecast import Forecast, Point

T0 = datetime(2026, 3, 2, 0, 0, tzinfo=UTC)


def hourly(values, start=T0, zone="MA"):
    points = [Point(start + timedelta(hours=i), float(v)) for i, v in enumerate(values)]
    return Forecast(points, timedelta(hours=1), zone, "test")


@pytest.fixture
def t0():
    return T0
