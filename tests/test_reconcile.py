from datetime import timedelta

import pytest

from greenwindow.operator.reconcile import (
    is_due,
    iso,
    job_manifest,
    job_name,
    needs_replan,
    parse_request,
    phase_from_job,
    schedule,
)

from .conftest import T0, hourly

TEMPLATE = {
    "metadata": {"labels": {"team": "data"}},
    "spec": {
        "backoffLimit": 1,
        "template": {
            "spec": {
                "restartPolicy": "Never",
                "containers": [{"name": "report", "image": "busybox", "command": ["true"]}],
            }
        },
    },
}


def spec(**overrides):
    return {"duration": "1h", "deadline": "8h", "jobTemplate": TEMPLATE, **overrides}


def test_parse_request_defaults():
    request = parse_request({"jobTemplate": TEMPLATE})
    assert request.zone == "MA"
    assert request.duration == timedelta(minutes=30)
    assert request.deadline == timedelta(hours=6)
    assert request.power_watts == 100
    assert request.max_intensity is None


@pytest.mark.parametrize(
    "bad",
    [
        {"jobTemplate": {}},
        {"jobTemplate": TEMPLATE, "duration": "3h", "deadline": "1h"},
        {"jobTemplate": TEMPLATE, "duration": "soon"},
    ],
)
def test_parse_request_rejects_invalid_specs(bad):
    with pytest.raises(ValueError):
        parse_request(bad)


def test_schedule_holds_job_for_a_greener_window():
    request = parse_request(spec(powerWatts=1000))
    forecast = hourly([700, 700, 300, 700, 700, 700, 700, 700, 700])
    status = schedule(request, forecast, T0, T0 + request.deadline)

    assert status["phase"] == "Scheduled"
    assert status["scheduledFor"] == "2026-03-02T02:00:00Z"
    assert status["deadline"] == "2026-03-02T08:00:00Z"
    assert status["reason"] == "greener-window"
    assert status["plannedIntensity"] == 300
    assert status["intensityIfRunNow"] == 700
    assert status["estimatedAvoidedGrams"] == 400  # 1 kWh * 400 g/kWh
    assert status["source"] == "test"


def test_schedule_runs_now_without_a_forecast():
    request = parse_request(spec())
    status = schedule(request, None, T0, T0 + request.deadline)
    assert status["scheduledFor"] == iso(T0)
    assert status["reason"] == "forecast-unavailable"


def test_due_and_replan():
    status = {
        "scheduledFor": "2026-03-02T02:00:00Z",
        "lastPlanned": "2026-03-02T00:00:00Z",
        "reason": "greener-window",
    }
    assert not is_due(status, T0 + timedelta(hours=1, minutes=59))
    assert is_due(status, T0 + timedelta(hours=2))
    assert not needs_replan(status, T0 + timedelta(minutes=10), timedelta(minutes=20))
    assert needs_replan(status, T0 + timedelta(minutes=20), timedelta(minutes=20))
    assert not needs_replan(
        {**status, "reason": "already-green"}, T0 + timedelta(hours=1), timedelta(minutes=20)
    )


def test_job_manifest_keeps_template_and_labels_it():
    manifest = job_manifest("nightly-report", parse_request(spec()))
    assert manifest["kind"] == "Job"
    assert manifest["metadata"]["name"] == "nightly-report-run"
    assert manifest["metadata"]["labels"] == {
        "team": "data",
        "greenwindow.io/carbon-aware-job": "nightly-report",
    }
    assert manifest["spec"] == TEMPLATE["spec"]


def test_job_name_fits_kubernetes_limits():
    assert len(job_name("x" * 80)) <= 63


@pytest.mark.parametrize(
    ("job_status", "phase"),
    [
        (None, "Running"),
        ({"active": 1}, "Running"),
        ({"conditions": [{"type": "Complete", "status": "True"}]}, "Succeeded"),
        ({"conditions": [{"type": "Failed", "status": "True"}]}, "Failed"),
        ({"conditions": [{"type": "Failed", "status": "False"}]}, "Running"),
    ],
)
def test_phase_from_job(job_status, phase):
    assert phase_from_job(job_status) == phase
