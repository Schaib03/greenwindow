from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from kubernetes.client.exceptions import ApiException

from greenwindow.operator import handlers
from greenwindow.providers.static import StaticProvider

from .test_reconcile import TEMPLATE

BODY = {
    "apiVersion": "greenwindow.io/v1alpha1",
    "kind": "CarbonAwareJob",
    "metadata": {
        "name": "nightly",
        "namespace": "batch",
        "uid": "6f1c2c1e-0000-4000-8000-000000000001",
        "creationTimestamp": "2026-03-02T00:00:00Z",
    },
}
SPEC = {"duration": "1h", "deadline": "6h", "jobTemplate": TEMPLATE}


class Patch(dict):
    def __init__(self):
        super().__init__()
        self.status = {}


class FakeBatch:
    def __init__(self, create_error=None, job_status=None):
        self.created = []
        self.create_error = create_error
        self.job_status = job_status

    def create_namespaced_job(self, namespace, body):
        if self.create_error:
            raise self.create_error
        self.created.append((namespace, body))

    def read_namespaced_job_status(self, name, namespace):
        if isinstance(self.job_status, Exception):
            raise self.job_status
        return SimpleNamespace(to_dict=lambda: {"status": self.job_status})


@pytest.fixture
def events(monkeypatch):
    sent = []
    monkeypatch.setattr(handlers.kopf, "info", lambda body, reason, message: sent.append(reason))
    return sent


@pytest.fixture
def clock(monkeypatch):
    now = {"value": datetime(2026, 3, 2, 0, 0, tzinfo=UTC)}
    monkeypatch.setattr(handlers, "_now", lambda: now["value"])
    return now


def use(batch=None, forecast="step=1h;700,700,300,700,700,700,700,700", clock=None):
    anchor = clock["value"] if clock else datetime(2026, 3, 2, tzinfo=UTC)
    handlers._state["batch"] = batch or FakeBatch()
    handlers._state["provider"] = StaticProvider.parse(forecast, anchor)
    return handlers._state["batch"]


def test_create_plans_and_reports(events, clock):
    use(clock=clock)
    patch = Patch()
    handlers.on_create(spec=SPEC, body=BODY, patch=patch)
    assert patch.status["phase"] == "Scheduled"
    assert patch.status["scheduledFor"] == "2026-03-02T02:00:00Z"
    assert events == ["Scheduled"]


def test_create_with_invalid_spec_fails_permanently(events, clock):
    use(clock=clock)
    patch = Patch()
    with pytest.raises(handlers.kopf.PermanentError):
        handlers.on_create(spec={"jobTemplate": {}}, body=BODY, patch=patch)
    assert patch.status["phase"] == "Failed"


def test_create_survives_a_provider_outage(events, clock):
    use(clock=clock)

    class Broken:
        name = "broken"

        def forecast(self, zone):
            raise RuntimeError("API down")

    handlers._state["provider"] = Broken()
    patch = Patch()
    handlers.on_create(spec=SPEC, body=BODY, patch=patch)
    assert patch.status["reason"] == "forecast-unavailable"
    assert patch.status["scheduledFor"] == "2026-03-02T00:00:00Z"


def scheduled_status(**extra):
    return {
        "phase": "Scheduled",
        "scheduledFor": "2026-03-02T02:00:00Z",
        "deadline": "2026-03-02T06:00:00Z",
        "lastPlanned": "2026-03-02T00:00:00Z",
        "reason": "greener-window",
        "estimatedAvoidedGrams": 40.0,
        **extra,
    }


def test_reconcile_waits_until_due(events, clock):
    batch = use(clock=clock)
    clock["value"] += timedelta(minutes=10)
    patch = Patch()
    handlers.reconcile(SPEC, scheduled_status(), "nightly", "batch", BODY, patch)
    assert batch.created == []
    assert patch.status == {}


def test_reconcile_creates_owned_job_when_due(events, clock):
    batch = use(clock=clock)
    clock["value"] += timedelta(hours=2)
    patch = Patch()
    handlers.reconcile(SPEC, scheduled_status(), "nightly", "batch", BODY, patch)

    namespace, job = batch.created[0]
    assert namespace == "batch"
    assert job["metadata"]["name"] == "nightly-run"
    owner = job["metadata"]["ownerReferences"][0]
    assert owner["kind"] == "CarbonAwareJob" and owner["uid"] == BODY["metadata"]["uid"]
    assert patch.status["phase"] == "Running"
    assert patch.status["jobName"] == "nightly-run"
    assert "Started" in events


def test_reconcile_tolerates_job_already_created(events, clock):
    use(batch=FakeBatch(create_error=ApiException(status=409)), clock=clock)
    clock["value"] += timedelta(hours=3)
    patch = Patch()
    handlers.reconcile(SPEC, scheduled_status(), "nightly", "batch", BODY, patch)
    assert patch.status["phase"] == "Running"


def test_reconcile_replans_with_a_fresh_forecast(events, clock):
    use(clock=clock, forecast="step=1h;700,700,700,700,200,700,700,700")
    clock["value"] += timedelta(minutes=30)
    patch = Patch()
    handlers.reconcile(SPEC, scheduled_status(), "nightly", "batch", BODY, patch)
    assert patch.status["scheduledFor"] == "2026-03-02T04:00:00Z"
    assert "Replanned" in events


@pytest.mark.parametrize(
    ("job_status", "phase"),
    [
        ({"conditions": [{"type": "Complete", "status": "True"}]}, "Succeeded"),
        ({"conditions": [{"type": "Failed", "status": "True"}]}, "Failed"),
        (ApiException(status=404), "Failed"),
    ],
)
def test_running_job_outcome(events, clock, job_status, phase):
    use(batch=FakeBatch(job_status=job_status), clock=clock)
    patch = Patch()
    status = {"phase": "Running", "jobName": "nightly-run"}
    handlers.reconcile(SPEC, status, "nightly", "batch", BODY, patch)
    assert patch.status["phase"] == phase


def test_running_job_still_active(events, clock):
    use(batch=FakeBatch(job_status={"active": 1}), clock=clock)
    patch = Patch()
    handlers.reconcile(
        SPEC, {"phase": "Running", "jobName": "nightly-run"}, "nightly", "batch", BODY, patch
    )
    assert patch.status == {}
