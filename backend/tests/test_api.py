import asyncio
import datetime as dt
import json

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from lotuslab.config import Settings
from lotuslab.main import create_app
from lotuslab.services.open_meteo import HOURLY_VARIABLES, ProviderError, choose_endpoint

TODAY = dt.datetime.now(dt.timezone.utc).date()
START = TODAY - dt.timedelta(days=3)


def fake_payload(start: dt.date, end: dt.date, offset=19800):
    days = (end - start).days + 1
    t0 = dt.datetime.combine(start, dt.time(), dt.timezone.utc).timestamp() - offset
    n = days * 24
    hours = np.arange(n)
    sw = np.clip(850 * np.sin(np.pi * ((hours % 24) - 6) / 12), 0, None)
    hourly = {
        "time": (t0 + 3600 * hours).astype(int).tolist(),
        "temperature_2m": (28 + 5 * np.sin(np.pi * ((hours % 24) - 9) / 12)).tolist(),
        "precipitation": [2.0 if h % 50 == 0 else 0.0 for h in hours],
        "cloud_cover": [40] * n,
        "wind_speed_10m": [3.0] * n,
        "relative_humidity_2m": [60] * n,
        "shortwave_radiation": sw.tolist(),
        "et0_fao_evapotranspiration": (sw / 1600).tolist(),
    }
    hourly["temperature_2m"][5] = None  # provider gaps happen
    return {"utc_offset_seconds": offset, "timezone": "Asia/Kolkata", "hourly": hourly}


class Provider:
    """Programmable fake Open-Meteo."""

    def __init__(self):
        self.calls = 0
        self.mode = "ok"
        self.last_params = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        self.last_params = dict(request.url.params)
        if self.mode == "down":
            return httpx.Response(502)
        if self.mode == "bad":
            return httpx.Response(400, json={"error": True, "reason": "Latitude must be in range"})
        if self.mode == "timeout":
            raise httpx.ConnectTimeout("boom", request=request)
        p = self.last_params
        start = dt.date.fromisoformat(p["start_date"])
        end = dt.date.fromisoformat(p["end_date"])
        return httpx.Response(200, json=fake_payload(start, end))


@pytest.fixture
def provider():
    return Provider()


@pytest.fixture
def client(provider):
    settings = Settings(http_retries=1, http_backoff_s=0.0, forecast_ttl_s=60)
    app = create_app(settings, transport=httpx.MockTransport(provider))
    with TestClient(app) as c:
        yield c


def body(**kw):
    b = {"latitude": 18.5204, "longitude": 73.8567, "start_date": START.isoformat(), "days": 3}
    b.update(kw)
    return b


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_simulation_end_to_end(client, provider):
    r = client.post("/api/v1/simulations", json=body())
    assert r.status_code == 200, r.text
    data = r.json()
    tl = data["timeline"]
    assert tl["n"] == 72 and len(tl["columns"]["depth_m"]) == 72 and len(tl["phase"]) == 72
    assert data["provenance"]["source"] == "open-meteo-forecast"
    assert data["provenance"]["gaps_filled"]["temperature_c"] == 1
    assert data["provenance"]["attribution"].startswith("Weather data by Open-Meteo")
    assert data["provenance"]["utc_offset_s"] == 19800
    assert abs(data["summary"]["mass_balance_error_m3"]) < 1e-6
    # request is rounded to ~1 km so nearby requests share the cache
    assert provider.last_params["latitude"] == "18.5200"
    assert provider.last_params["wind_speed_unit"] == "ms"


def test_caching_layers(client, provider):
    client.post("/api/v1/simulations", json=body())
    r2 = client.post("/api/v1/simulations", json=body(latitude=18.5199))  # rounds to the same cell
    assert provider.calls == 1
    assert r2.headers["x-result-cache"] == "hit"
    r3 = client.post("/api/v1/simulations", json=body(scenario={"preset": "heatwave"}))
    assert provider.calls == 1  # same weather, different scenario
    assert r3.headers["x-result-cache"] == "miss" and r3.headers["x-weather-cache"] == "hit"


def test_stale_if_error(provider):
    t = [1000.0]
    settings = Settings(http_retries=0, http_backoff_s=0.0, forecast_ttl_s=10, stale_grace_s=100)
    app = create_app(settings, transport=httpx.MockTransport(provider))
    with TestClient(app) as c:
        c.app.state.service.weather_cache.clock = lambda: t[0]
        assert c.post("/api/v1/simulations", json=body()).status_code == 200
        t[0] += 50  # expired, but inside the stale grace window
        provider.mode = "down"
        r = c.post("/api/v1/simulations", json=body())
        assert r.status_code == 200
        assert r.json()["provenance"]["stale"] is True
        assert r.headers["x-weather-cache"] == "stale"
        t[0] += 1000  # beyond grace -> honest failure
        assert c.post("/api/v1/simulations", json=body()).status_code == 503


def test_provider_down_returns_503_after_retries(client, provider):
    provider.mode = "down"
    r = client.post("/api/v1/simulations", json=body())
    assert r.status_code == 503 and "synthetic" in r.json()["detail"]
    assert provider.calls == 2  # 1 retry


def test_provider_timeout_returns_503(client, provider):
    provider.mode = "timeout"
    assert client.post("/api/v1/simulations", json=body()).status_code == 503


def test_provider_rejection_returns_422(client, provider):
    provider.mode = "bad"
    r = client.post("/api/v1/simulations", json=body())
    assert r.status_code == 422 and "Latitude" in r.json()["detail"]


@pytest.mark.parametrize(
    "bad",
    [
        {"latitude": 91},
        {"days": 0},
        {"days": 400},
        {"pond": {"initial_depth_m": 5, "max_depth_m": 1}},
        {"lotus": {"t_min_c": 35}},
        {"scenario": {"preset": "apocalypse"}},
        {"unknown_field": 1},
    ],
)
def test_validation_errors(client, bad):
    assert client.post("/api/v1/simulations", json=body(**bad)).status_code == 422


def test_nan_rejected(client):
    raw = json.dumps(body()).replace("18.5204", "NaN")
    r = client.post("/api/v1/simulations", content=raw, headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_range_too_far_ahead_rejected(client):
    r = client.post("/api/v1/simulations", json=body(start_date=(TODAY + dt.timedelta(days=10)).isoformat(), days=30))
    assert r.status_code == 422


def test_synthetic_source_is_labelled_and_offline(client, provider):
    r = client.post("/api/v1/simulations", json=body(source="synthetic", start_date="2020-01-01", days=30))
    assert r.status_code == 200
    assert r.json()["provenance"]["source"] == "synthetic"
    assert r.json()["provenance"]["attribution"] is None
    assert provider.calls == 0


def test_compare(client):
    r = client.post(
        "/api/v1/simulations/compare",
        json=body(source="synthetic", days=20, baseline={"preset": "live"}, variant={"preset": "drought"}),
    )
    assert r.status_code == 200
    d = r.json()
    assert d["divergence"]["final_depth_delta_m"] < 0
    assert d["variant"]["scenario"]["precipitation_multiplier"] == 0


def test_scenario_overrides_preset(client):
    r = client.post(
        "/api/v1/simulations",
        json=body(source="synthetic", scenario={"preset": "heatwave", "temperature_offset_c": 1.0}),
    )
    s = r.json()["scenario"]
    assert s["temperature_offset_c"] == 1.0 and s["precipitation_multiplier"] == 0.3


def test_sensitivity_grid(client):
    r = client.post(
        "/api/v1/simulations/sensitivity",
        json=body(source="synthetic", days=10, temperature_offsets_c=[0, 5], precipitation_multipliers=[0, 1, 2]),
    )
    d = r.json()
    assert len(d["final_saturation"]) == 2 and len(d["final_saturation"][0]) == 3
    assert d["final_depth_m"][0][0] <= d["final_depth_m"][0][2]


def test_puzzle(client):
    r = client.get("/api/v1/puzzle")
    d = r.json()
    assert d["days_to_fill"] == 30 and d["half_full_day"] == pytest.approx(29)
    assert client.get("/api/v1/puzzle", params={"multiplier": 1}).status_code == 422


def test_scenarios_listing(client):
    assert set(client.get("/api/v1/scenarios").json()) >= {"live", "heatwave", "drought"}


def test_choose_endpoint():
    today = dt.date(2026, 10, 5)
    assert choose_endpoint(dt.date(2026, 10, 1), dt.date(2026, 10, 10), today) == "forecast"
    assert choose_endpoint(dt.date(2020, 1, 1), dt.date(2020, 3, 1), today) == "archive"
    with pytest.raises(ProviderError):
        choose_endpoint(dt.date(2026, 1, 1), dt.date(2026, 10, 3), today)
    with pytest.raises(ProviderError):
        choose_endpoint(dt.date(2026, 10, 1), dt.date(2026, 11, 30), today)


async def test_single_flight_coalesces_concurrent_loads():
    from lotuslab.services.cache import TTLCache

    cache = TTLCache(8, stale_grace_s=0)
    calls = 0

    async def load():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return "weather"

    results = await asyncio.gather(*(cache.get_or_load("k", load, 60) for _ in range(20)))
    assert calls == 1
    assert all(e.value == "weather" for e, _ in results)
    assert cache.coalesced == 19


def test_lru_eviction():
    from lotuslab.services.cache import LRUCache

    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    c.get("a")
    c.put("c", 3)
    assert c.get("b") is None and c.get("a") == 1 and c.get("c") == 3


def test_all_provider_variables_requested(client, provider):
    client.post("/api/v1/simulations", json=body())
    assert set(provider.last_params["hourly"].split(",")) == set(HOURLY_VARIABLES)
