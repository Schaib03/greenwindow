from datetime import UTC, datetime, timedelta

import httpx
import pytest

from greenwindow import providers
from greenwindow.providers.electricitymaps import ElectricityMapsProvider
from greenwindow.providers.openmeteo import WIND_SITES, OpenMeteoMoroccoProvider
from greenwindow.providers.static import StaticProvider


def open_meteo_payload(hours=6):
    times = [f"2026-06-15T{h:02d}:00" for h in range(hours)]
    solar = {"hourly": {"time": times, "shortwave_radiation": [0, 0, 300, 800, 900, None]}}
    wind = {"hourly": {"time": times, "wind_speed_100m": [4, 4, 13, 13, 13, None]}}
    return [solar] + [wind] * len(WIND_SITES)


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_open_meteo_builds_an_hourly_forecast():
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=open_meteo_payload())

    forecast = OpenMeteoMoroccoProvider(client=mock_client(handler)).forecast("MA")

    assert seen["params"]["hourly"] == "shortwave_radiation,wind_speed_100m"
    assert len(seen["params"]["latitude"].split(",")) == 1 + len(WIND_SITES)
    assert len(forecast.points) == 6
    assert forecast.step == timedelta(hours=1)
    assert forecast.points[0].start == datetime(2026, 6, 15, tzinfo=UTC)
    # Sun and wind at 03:00-04:00 make those hours cleaner than the calm night.
    assert forecast.points[4].intensity < forecast.points[0].intensity


def test_open_meteo_only_knows_morocco():
    provider = OpenMeteoMoroccoProvider(client=mock_client(lambda r: httpx.Response(500)))
    with pytest.raises(providers.ProviderError):
        provider.forecast("FR")


def test_open_meteo_http_errors_are_provider_errors():
    provider = OpenMeteoMoroccoProvider(client=mock_client(lambda r: httpx.Response(503)))
    with pytest.raises(providers.ProviderError):
        provider.forecast("MA")


def test_electricity_maps_parses_forecast():
    def handler(request):
        assert request.headers["auth-token"] == "secret"
        assert request.url.params["zone"] == "MA"
        return httpx.Response(
            200,
            json={
                "forecast": [
                    {"datetime": "2026-06-15T00:00:00.000Z", "carbonIntensity": 610},
                    {"datetime": "2026-06-15T01:00:00.000Z", "carbonIntensity": 590},
                ]
            },
        )

    forecast = ElectricityMapsProvider("secret", client=mock_client(handler)).forecast("MA")
    assert [p.intensity for p in forecast.points] == [610, 590]
    assert forecast.step == timedelta(hours=1)


def test_static_provider_is_anchored_to_the_step():
    anchor = datetime(2026, 6, 15, 10, 7, 31, 5000, tzinfo=UTC)
    provider = StaticProvider.parse("step=5m;500,200,500", anchor)
    forecast = provider.forecast("MA")
    assert forecast.start == datetime(2026, 6, 15, 10, 5, tzinfo=UTC)
    assert [p.intensity for p in forecast.points] == [500, 200, 500]


def test_static_provider_rejects_bad_spec():
    with pytest.raises(ValueError):
        StaticProvider.parse("every=5m;1,2", datetime.now(UTC))


def test_cached_provider_calls_upstream_once():
    calls = []

    class Upstream:
        name = "upstream"

        def forecast(self, zone):
            calls.append(zone)
            return StaticProvider.parse("100", datetime.now(UTC)).forecast(zone)

    cached = providers.CachedProvider(Upstream(), timedelta(minutes=5))
    cached.forecast("MA")
    cached.forecast("MA")
    cached.forecast("ES")
    assert calls == ["MA", "ES"]


def test_from_env():
    assert providers.from_env({"GREENWINDOW_PROVIDER": "static"}).name == "static"
    assert providers.from_env({}).name == "openmeteo-model"
    with pytest.raises(providers.ProviderError):
        providers.from_env({"GREENWINDOW_PROVIDER": "electricitymaps"})
    with pytest.raises(providers.ProviderError):
        providers.from_env({"GREENWINDOW_PROVIDER": "nope"})
