from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from greenwindow.forecast import Forecast, Point
from greenwindow.grid_model import GridParams, dispatch
from greenwindow.providers import ProviderError

API_URL = "https://api.open-meteo.com/v1/forecast"

SOLAR_SITE = ("Noor Ouarzazate", 30.99, -6.86)
WIND_SITES = [
    ("Tarfaya", 27.94, -12.93),
    ("Khalladi (Tangier)", 35.70, -5.80),
    ("Essaouira", 31.51, -9.77),
]


class OpenMeteoMoroccoProvider:
    """Estimates Morocco's grid intensity from the Open-Meteo weather forecast (no API key)."""

    name = "openmeteo-model"

    def __init__(
        self,
        params: GridParams | None = None,
        client: httpx.Client | None = None,
        forecast_days: int = 2,
    ):
        self.params = params or GridParams()
        self.client = client or httpx.Client(timeout=10.0)
        self.forecast_days = forecast_days

    def forecast(self, zone: str) -> Forecast:
        if zone.upper() != "MA":
            raise ProviderError(f"the weather model only covers Morocco (MA), not {zone!r}")

        sites = [SOLAR_SITE, *WIND_SITES]
        try:
            response = self.client.get(
                API_URL,
                params={
                    "latitude": ",".join(str(s[1]) for s in sites),
                    "longitude": ",".join(str(s[2]) for s in sites),
                    "hourly": "shortwave_radiation,wind_speed_100m",
                    "wind_speed_unit": "ms",
                    "timezone": "UTC",
                    "forecast_days": self.forecast_days,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Open-Meteo request failed: {exc}") from exc

        solar_site, *wind_sites = response.json()
        times = solar_site["hourly"]["time"]
        irradiance = solar_site["hourly"]["shortwave_radiation"]
        winds = [site["hourly"]["wind_speed_100m"] for site in wind_sites]

        points = []
        for i, stamp in enumerate(times):
            moment = datetime.fromisoformat(stamp).replace(tzinfo=UTC)
            speeds = [w[i] for w in winds if w[i] is not None]
            mix = dispatch(moment, irradiance[i] or 0.0, speeds, self.params)
            points.append(Point(moment, round(mix.intensity, 1)))
        return Forecast(points, timedelta(hours=1), "MA", self.name)
