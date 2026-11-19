from datetime import timedelta

import pytest

from greenwindow.scheduler import energy_kwh, plan

from .conftest import T0, hourly

H = timedelta(hours=1)


def test_picks_the_lowest_average_window():
    forecast = hourly([700, 690, 650, 400, 380, 600, 700, 700])
    result = plan(forecast, T0, 2 * H, T0 + 8 * H)
    assert result.start == T0 + 3 * H
    assert result.intensity == pytest.approx(390)
    assert result.intensity_now == pytest.approx(695)
    assert result.delayed


def test_job_must_finish_before_the_deadline():
    forecast = hourly([700, 700, 700, 650, 200, 200])
    result = plan(forecast, T0, 2 * H, T0 + 5 * H)
    # Starting at 4h would end at 6h, after the deadline.
    assert result.start == T0 + 3 * H
    assert result.start + 2 * H <= T0 + 5 * H


def test_window_does_not_need_to_start_on_the_hour():
    forecast = hourly([600, 600, 300, 600])
    now = T0 + timedelta(minutes=10)
    result = plan(forecast, now, timedelta(minutes=30), T0 + 4 * H)
    assert result.start == T0 + 2 * H
    assert result.intensity == 300


def test_small_gains_are_not_worth_waiting_for():
    forecast = hourly([500, 495, 490, 500])
    result = plan(forecast, T0, H, T0 + 4 * H)
    assert result.start == T0
    assert result.reason == "already-green"


def test_threshold_runs_immediately():
    forecast = hourly([350, 100, 100])
    result = plan(forecast, T0, H, T0 + 3 * H, max_intensity=400)
    assert result.start == T0
    assert result.reason == "below-threshold"


def test_no_slack_runs_now():
    forecast = hourly([700, 100, 100])
    result = plan(forecast, T0, 2 * H, T0 + 2 * H)
    assert result.start == T0
    assert result.reason == "no-slack"


def test_forecast_shorter_than_job_runs_now():
    forecast = hourly([700, 100])
    result = plan(forecast, T0, 5 * H, T0 + 10 * H)
    assert result.start == T0
    assert result.reason == "forecast-too-short"


def test_deadline_beyond_forecast_is_clipped():
    forecast = hourly([700, 700, 300])
    result = plan(forecast, T0, H, T0 + 48 * H)
    assert result.start == T0 + 2 * H


def test_avoided_emissions():
    forecast = hourly([700, 300])
    result = plan(forecast, T0, H, T0 + 2 * H)
    kwh = energy_kwh(500, H)
    assert kwh == pytest.approx(0.5)
    assert result.avoided_grams(kwh) == pytest.approx(200)
