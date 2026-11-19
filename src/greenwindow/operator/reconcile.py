"""Decisions made by the operator, kept free of Kubernetes calls so they can be unit tested."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from greenwindow.durations import parse_duration
from greenwindow.forecast import Forecast
from greenwindow.scheduler import energy_kwh, plan

GROUP = "greenwindow.io"
VERSION = "v1alpha1"
PLURAL = "carbonawarejobs"


@dataclass(frozen=True)
class Request:
    zone: str
    duration: timedelta
    deadline: timedelta
    power_watts: float
    max_intensity: float | None
    job_template: dict[str, Any]

    @property
    def energy_kwh(self) -> float:
        return energy_kwh(self.power_watts, self.duration)


def parse_request(spec: dict[str, Any]) -> Request:
    template = spec.get("jobTemplate") or {}
    if not template.get("spec", {}).get("template"):
        raise ValueError("spec.jobTemplate.spec.template is required")
    duration = parse_duration(spec.get("duration", "30m"))
    deadline = parse_duration(spec.get("deadline", "6h"))
    if deadline < duration:
        raise ValueError("deadline must be at least as long as duration")
    max_intensity = spec.get("maxIntensity")
    return Request(
        zone=spec.get("zone", "MA"),
        duration=duration,
        deadline=deadline,
        power_watts=float(spec.get("powerWatts", 100)),
        max_intensity=float(max_intensity) if max_intensity is not None else None,
        job_template=template,
    )


def iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def schedule(
    request: Request, forecast: Forecast | None, now: datetime, deadline_at: datetime
) -> dict[str, Any]:
    base = {"phase": "Scheduled", "deadline": iso(deadline_at), "lastPlanned": iso(now)}
    if forecast is None:
        # Never hold a job hostage to a forecast outage: run it now.
        return {**base, "scheduledFor": iso(now), "reason": "forecast-unavailable"}

    result = plan(forecast, now, request.duration, deadline_at, request.max_intensity)
    return {
        **base,
        "scheduledFor": iso(result.start),
        "reason": result.reason,
        "source": forecast.source,
        "plannedIntensity": round(result.intensity, 1),
        "intensityIfRunNow": round(result.intensity_now, 1),
        "estimatedAvoidedGrams": round(result.avoided_grams(request.energy_kwh), 1),
    }


def is_due(status: dict[str, Any], now: datetime) -> bool:
    return now >= parse_iso(status["scheduledFor"])


def needs_replan(status: dict[str, Any], now: datetime, interval: timedelta) -> bool:
    if status.get("reason") != "greener-window":
        return False
    return now - parse_iso(status["lastPlanned"]) >= interval


def job_name(name: str) -> str:
    return f"{name[:59]}-run"


def job_manifest(name: str, request: Request) -> dict[str, Any]:
    metadata = dict(request.job_template.get("metadata") or {})
    labels = {**metadata.get("labels", {}), "greenwindow.io/carbon-aware-job": name}
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": job_name(name), "labels": labels},
        "spec": request.job_template["spec"],
    }


def phase_from_job(job_status: dict[str, Any] | None) -> str:
    conditions = (job_status or {}).get("conditions") or []
    for condition in conditions:
        if condition.get("status") != "True":
            continue
        if condition.get("type") == "Complete":
            return "Succeeded"
        if condition.get("type") == "Failed":
            return "Failed"
    return "Running"
