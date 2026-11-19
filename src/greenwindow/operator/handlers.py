from __future__ import annotations

import contextlib
import logging
import os
from datetime import UTC, datetime, timedelta

import kopf
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException

from greenwindow import providers
from greenwindow.operator import metrics
from greenwindow.operator.reconcile import (
    GROUP,
    PLURAL,
    VERSION,
    is_due,
    iso,
    job_manifest,
    job_name,
    needs_replan,
    parse_iso,
    parse_request,
    phase_from_job,
    schedule,
)

RECONCILE_SECONDS = float(os.environ.get("GREENWINDOW_RECONCILE_SECONDS", "30"))
REPLAN_INTERVAL = timedelta(minutes=float(os.environ.get("GREENWINDOW_REPLAN_MINUTES", "20")))
METRICS_PORT = int(os.environ.get("GREENWINDOW_METRICS_PORT", "9090"))

log = logging.getLogger("greenwindow")
_state: dict = {}


def _now() -> datetime:
    return datetime.now(UTC)


def _forecast(zone: str):
    try:
        forecast = _state["provider"].forecast(zone)
    except Exception as exc:
        log.warning("forecast for %s unavailable: %s", zone, exc)
        return None
    with contextlib.suppress(ValueError):
        metrics.GRID_INTENSITY.labels(zone, forecast.source).set(forecast.intensity_at(_now()))
    return forecast


@kopf.on.startup()
def startup(settings: kopf.OperatorSettings, **_):
    settings.posting.level = logging.INFO
    settings.watching.server_timeout = 300
    try:
        config.load_incluster_config()
    except ConfigException:
        config.load_kube_config()
    _state["batch"] = client.BatchV1Api()
    _state["provider"] = providers.from_env()
    metrics.serve(METRICS_PORT)
    log.info("using forecast provider %s", _state["provider"].name)


@kopf.on.create(GROUP, VERSION, PLURAL)
def on_create(spec, body, patch, **_):
    try:
        request = parse_request(dict(spec))
    except ValueError as exc:
        patch.status["phase"] = "Failed"
        patch.status["message"] = str(exc)
        raise kopf.PermanentError(str(exc)) from exc

    now = _now()
    status = schedule(request, _forecast(request.zone), now, now + request.deadline)
    patch.status.update(status)
    metrics.JOBS_SCHEDULED.labels(request.zone, status["reason"]).inc()

    if status["reason"] == "greener-window":
        message = (
            f"Holding until {status['scheduledFor']}: "
            f"{status['plannedIntensity']} instead of {status['intensityIfRunNow']} gCO2/kWh"
        )
    else:
        message = f"Starting now ({status['reason']})"
    kopf.info(body, reason="Scheduled", message=message)


@kopf.timer(GROUP, VERSION, PLURAL, interval=RECONCILE_SECONDS)
def reconcile(spec, status, name, namespace, body, patch, **_):
    phase = status.get("phase")
    if phase == "Scheduled":
        _handle_scheduled(spec, status, name, namespace, body, patch)
    elif phase == "Running":
        _handle_running(spec, status, name, namespace, body, patch)


def _handle_scheduled(spec, status, name, namespace, body, patch):
    request = parse_request(dict(spec))
    now = _now()

    if not is_due(status, now):
        if needs_replan(status, now, REPLAN_INTERVAL):
            updated = schedule(request, _forecast(request.zone), now, parse_iso(status["deadline"]))
            if updated["scheduledFor"] != status["scheduledFor"]:
                kopf.info(body, reason="Replanned", message=f"New start {updated['scheduledFor']}")
            patch.status.update(updated)
        return

    manifest = job_manifest(name, request)
    kopf.adopt(manifest, owner=body)
    try:
        _state["batch"].create_namespaced_job(namespace, manifest)
    except ApiException as exc:
        # A previous reconcile may have created it before the status patch landed.
        if exc.status != 409:
            raise

    created = parse_iso(body["metadata"]["creationTimestamp"])
    metrics.JOBS_STARTED.labels(request.zone).inc()
    metrics.START_DELAY.labels(request.zone).observe(max((now - created).total_seconds(), 0))
    metrics.AVOIDED_GRAMS.labels(request.zone).inc(status.get("estimatedAvoidedGrams", 0))
    patch.status.update({"phase": "Running", "jobName": job_name(name), "startedAt": iso(now)})
    kopf.info(body, reason="Started", message=f"Created job {job_name(name)}")


def _handle_running(spec, status, name, namespace, body, patch):
    try:
        job = _state["batch"].read_namespaced_job_status(status["jobName"], namespace)
    except ApiException as exc:
        if exc.status == 404:
            patch.status.update({"phase": "Failed", "message": "job was deleted"})
            return
        raise

    phase = phase_from_job(job.to_dict().get("status"))
    if phase == "Running":
        return
    patch.status.update({"phase": phase, "completedAt": iso(_now())})
    metrics.JOBS_FINISHED.labels(spec.get("zone", "MA"), phase).inc()
    kopf.info(body, reason=phase, message=f"Job {status['jobName']} {phase.lower()}")
