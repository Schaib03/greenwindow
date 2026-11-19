from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from greenwindow.forecast import Forecast, Point
from greenwindow.providers import ProviderError

API_URL = "https://api.electricitymap.org/v3/carbon-intensity/forecast"


class ElectricityMapsProvider:
    """Official forecasts for zones covered by an Electricity Maps plan (needs a token)."""

    name = "electricitymaps"

    def __init__(self, token: str, client: httpx.Client | None = None):
        self.token = token
        self.client = client or httpx.Client(timeout=10.0)

    def forecast(self, zone: str) -> Forecast:
        try:
            response = self.client.get(
                API_URL, params={"zone": zone}, headers={"auth-token": self.token}
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Electricity Maps request failed: {exc}") from exc

        entries = response.json().get("forecast", [])
        if not entries:
            raise ProviderError(f"no forecast returned for zone {zone!r}")
        points = [
            Point(
                datetime.fromisoformat(entry["datetime"].replace("Z", "+00:00")),
                float(entry["carbonIntensity"]),
            )
            for entry in entries
        ]
        step = points[1].start - points[0].start if len(points) > 1 else timedelta(hours=1)
        return Forecast(points, step, zone, self.name)
