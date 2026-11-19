from __future__ import annotations

import os
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Protocol

from greenwindow.forecast import Forecast


class Provider(Protocol):
    name: str

    def forecast(self, zone: str) -> Forecast: ...


class ProviderError(RuntimeError):
    pass


class CachedProvider:
    """Forecasts change a few times a day; no need to call the API on every reconcile."""

    def __init__(self, inner: Provider, ttl: timedelta = timedelta(minutes=30)):
        self.inner = inner
        self.name = inner.name
        self.ttl = ttl.total_seconds()
        self._cache: dict[str, tuple[float, Forecast]] = {}
        self._lock = threading.Lock()

    def forecast(self, zone: str) -> Forecast:
        with self._lock:
            cached = self._cache.get(zone)
            if cached and time.monotonic() - cached[0] < self.ttl:
                return cached[1]
        result = self.inner.forecast(zone)
        with self._lock:
            self._cache[zone] = (time.monotonic(), result)
        return result


def from_env(env: dict[str, str] | None = None) -> Provider:
    env = dict(os.environ if env is None else env)
    kind = env.get("GREENWINDOW_PROVIDER", "openmeteo")

    if kind == "openmeteo":
        from greenwindow.providers.openmeteo import OpenMeteoMoroccoProvider

        provider: Provider = OpenMeteoMoroccoProvider()
    elif kind == "electricitymaps":
        from greenwindow.providers.electricitymaps import ElectricityMapsProvider

        token = env.get("ELECTRICITYMAPS_TOKEN")
        if not token:
            raise ProviderError("the electricitymaps provider needs ELECTRICITYMAPS_TOKEN")
        provider = ElectricityMapsProvider(token)
    elif kind == "static":
        from greenwindow.providers.static import StaticProvider

        provider = StaticProvider.parse(
            env.get("GREENWINDOW_STATIC_FORECAST", "step=1h;500"), anchor=datetime.now(UTC)
        )
        return provider
    else:
        raise ProviderError(f"unknown provider {kind!r}")

    ttl = int(env.get("GREENWINDOW_FORECAST_TTL_MINUTES", "30"))
    return CachedProvider(provider, timedelta(minutes=ttl))
