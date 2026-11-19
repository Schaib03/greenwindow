from datetime import timedelta

import pytest

from greenwindow.durations import format_duration, parse_duration

from .conftest import T0, hourly


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("90m", timedelta(minutes=90)),
        ("1h30m", timedelta(hours=1, minutes=30)),
        ("2d", timedelta(days=2)),
        (" 45S ", timedelta(seconds=45)),
    ],
)
def test_parse_duration(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "10", "1h foo", "0m"])
def test_parse_duration_rejects_garbage(text):
    with pytest.raises(ValueError):
        parse_duration(text)


def test_format_duration():
    assert format_duration(timedelta(minutes=95)) == "1h35m"
    assert format_duration(timedelta(hours=3)) == "3h"
    assert format_duration(timedelta(minutes=20)) == "20m"


def test_intensity_at_and_bounds():
    forecast = hourly([500, 300, 400])
    assert forecast.intensity_at(T0 + timedelta(minutes=59)) == 500
    assert forecast.intensity_at(T0 + timedelta(hours=1)) == 300
    assert forecast.end == T0 + timedelta(hours=3)
    with pytest.raises(ValueError):
        forecast.intensity_at(T0 + timedelta(hours=3))


def test_average_is_time_weighted_across_segments():
    forecast = hourly([600, 300, 300])
    # 30 min at 600 then 60 min at 300
    avg = forecast.average(T0 + timedelta(minutes=30), T0 + timedelta(hours=2))
    assert avg == pytest.approx((600 * 30 + 300 * 60) / 90)


def test_average_outside_forecast_fails():
    forecast = hourly([600, 300])
    with pytest.raises(ValueError):
        forecast.average(T0 + timedelta(hours=1), T0 + timedelta(hours=3))
