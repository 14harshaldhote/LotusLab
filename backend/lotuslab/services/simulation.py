"""Orchestration: weather cache -> scenario -> engine -> serialised timeline.

Two cache layers keep repeated work at zero:

1. weather cache (TTL + single-flight + stale-if-error), keyed by rounded location and
   date range, so scrubbing, scenario changes and comparisons reuse one provider call;
2. result cache (LRU) holding *serialised JSON bytes*, keyed by the weather snapshot and
   every model input, so an identical request is answered without simulating or
   re-encoding anything.
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from .. import MODEL_VERSION
from ..api.schemas import CompareRequest, Location, SensitivityRequest, SimulationRequest
from ..config import Settings
from ..core import synthetic
from ..core.engine import Timeline, simulate
from ..core.params import LotusParams, PondParams, params_key
from ..core.scenarios import Scenario, apply
from ..core.weather import HourlyWeather
from .cache import Entry, LRUCache, TTLCache
from .open_meteo import ATTRIBUTION, OpenMeteoClient, WeatherResult

# Columns are rounded before encoding: 5 significant decimals is far below any model
# or measurement precision and cuts the JSON size roughly in half.
DECIMALS = 5


@dataclass(frozen=True)
class WeatherSnapshot:
    key: tuple
    entry: Entry[WeatherResult]
    status: str  # hit | miss | stale

    @property
    def weather(self) -> HourlyWeather:
        return self.entry.value.weather

    def provenance(self, lat: float, lon: float) -> dict[str, Any]:
        result = self.entry.value
        synthetic_source = result.endpoint == "synthetic"
        return {
            "source": "synthetic" if synthetic_source else f"open-meteo-{result.endpoint}",
            "fetched_at": self.entry.stored_at,
            "stale": self.status == "stale",
            "cache": self.status,
            "timezone": result.timezone,
            "utc_offset_s": result.weather.utc_offset_s,
            "latitude": lat,
            "longitude": lon,
            "gaps_filled": result.weather.gaps_filled,
            "attribution": None if synthetic_source else ATTRIBUTION,
        }


class LotusService:
    def __init__(self, settings: Settings, client: OpenMeteoClient) -> None:
        self.settings = settings
        self.client = client
        self.weather_cache: TTLCache[WeatherResult] = TTLCache(settings.weather_cache_size, settings.stale_grace_s)
        self.result_cache: LRUCache[Encoded] = LRUCache(settings.result_cache_size)

    # ---- weather -----------------------------------------------------------------
    async def weather(self, loc: Location) -> WeatherSnapshot:
        lat, lon = round(loc.latitude, 2), round(loc.longitude, 2)  # ~1 km: share nearby requests
        end = loc.start_date + dt.timedelta(days=loc.days - 1)
        if loc.source == "synthetic":
            key: tuple = ("synthetic", lat, lon, loc.start_date, loc.days, loc.seed)

            async def load() -> WeatherResult:
                offset = int(round(lon / 15.0)) * 3600  # nominal solar time zone
                start = dt.datetime.combine(loc.start_date, dt.time(), dt.timezone.utc).timestamp() - offset
                w = synthetic.generate(start, loc.days * 24, lat, lon, seed=loc.seed)
                w = w.with_columns(utc_offset_s=offset)
                return WeatherResult(w, "synthetic", f"UTC{offset // 3600:+d} (nominal)")

            ttl = float("inf")
        else:
            key = ("open-meteo", lat, lon, loc.start_date, end)

            async def load() -> WeatherResult:
                return await self.client.hourly(lat, lon, loc.start_date, end)

            today = dt.datetime.now(dt.timezone.utc).date()
            ttl = self.settings.archive_ttl_s if end < today - dt.timedelta(days=5) else self.settings.forecast_ttl_s
        entry, status = await self.weather_cache.get_or_load(key, load, ttl)
        return WeatherSnapshot(key, entry, status)

    # ---- simulation ----------------------------------------------------------------
    async def simulate(self, req: SimulationRequest) -> tuple["Encoded", dict[str, str]]:
        snap = await self.weather(req)
        scenario = req.scenario.to_scenario()
        pond, lotus = req.pond.to_params(), req.lotus.to_params()
        key = ("sim", snap.key, snap.entry.stored_at, snap.status == "stale", scenario, params_key(pond, lotus))
        cached = self.result_cache.get(key)
        if cached is not None:
            return cached, {"X-Result-Cache": "hit", "X-Weather-Cache": snap.status}

        t = time.perf_counter()
        tl = self._run(snap.weather, req, scenario, pond, lotus)
        compute_ms = (time.perf_counter() - t) * 1000.0
        body = {
            "model_version": MODEL_VERSION,
            "provenance": snap.provenance(round(req.latitude, 2), round(req.longitude, 2)),
            **run_payload(tl, scenario),
        }
        body["summary"]["compute_ms"] = round(compute_ms, 3)
        data = Encoded.of(encode(body))
        self.result_cache.put(key, data)
        return data, {
            "X-Result-Cache": "miss",
            "X-Weather-Cache": snap.status,
            "Server-Timing": f"simulate;dur={compute_ms:.2f}",
        }

    async def compare(self, req: CompareRequest) -> bytes:
        snap = await self.weather(req)
        pond, lotus = req.pond.to_params(), req.lotus.to_params()
        a_s, b_s = req.baseline.to_scenario(), req.variant.to_scenario()
        a = self._run(snap.weather, req, a_s, pond, lotus)
        b = self._run(snap.weather, req, b_s, pond, lotus)
        body = {
            "model_version": MODEL_VERSION,
            "provenance": snap.provenance(round(req.latitude, 2), round(req.longitude, 2)),
            "baseline": run_payload(a, a_s),
            "variant": run_payload(b, b_s),
            "divergence": divergence(a, b),
        }
        return encode(body)

    async def sensitivity(self, req: SensitivityRequest) -> bytes:
        snap = await self.weather(req)
        pond, lotus = req.pond.to_params(), req.lotus.to_params()
        t = time.perf_counter()
        sat, depth, over = [], [], []
        for dt_c in req.temperature_offsets_c:
            row_s, row_d, row_o = [], [], []
            for pm in req.precipitation_multipliers:
                s = Scenario(temperature_offset_c=dt_c, precipitation_multiplier=pm)
                summary = self._run(snap.weather, req, s, pond, lotus).summary
                row_s.append(round(summary["final_saturation"], 4))
                row_d.append(round(summary["final_depth_m"], 4))
                row_o.append(round(summary["totals_m3"]["overflow_m3"], 3))
            sat.append(row_s)
            depth.append(row_d)
            over.append(row_o)
        body = {
            "model_version": MODEL_VERSION,
            "provenance": snap.provenance(round(req.latitude, 2), round(req.longitude, 2)),
            "temperature_offsets_c": req.temperature_offsets_c,
            "precipitation_multipliers": req.precipitation_multipliers,
            "final_saturation": sat,
            "final_depth_m": depth,
            "overflow_m3": over,
            "compute_ms": round((time.perf_counter() - t) * 1000.0, 3),
        }
        return encode(body)

    @staticmethod
    def _run(w: HourlyWeather, loc: Location, s: Scenario, pond: PondParams, lotus: LotusParams) -> Timeline:
        return simulate(apply(w, s), loc.latitude, loc.longitude, pond, lotus)

    def stats(self) -> dict[str, Any]:
        return {
            "weather_cache": self.weather_cache.stats(),
            "result_cache": self.result_cache.stats(),
            "provider_requests": self.client.requests_made,
        }


def run_payload(tl: Timeline, scenario: Scenario) -> dict[str, Any]:
    cols = {name: np.round(arr, DECIMALS).tolist() for name, arr in tl.columns.items()}
    return {
        "scenario": scenario.as_dict(),
        "timeline": {"t0": tl.t0, "dt": tl.dt, "n": len(tl), "columns": cols, "phase": tl.phase.tolist()},
        "summary": tl.summary,
    }


def divergence(a: Timeline, b: Timeline, threshold: float = 0.05) -> dict[str, Any]:
    """Where and how far two runs on the same weather drift apart."""
    d_sat = b.columns["saturation"] - a.columns["saturation"]
    d_depth = b.columns["depth_m"] - a.columns["depth_m"]
    over = np.flatnonzero(np.abs(d_sat) >= threshold)
    i_max = int(np.abs(d_sat).argmax())
    return {
        "threshold": threshold,
        "first_divergence_time": float(a.time[over[0]]) if over.size else None,
        "max_saturation_gap": float(d_sat[i_max]),
        "max_saturation_gap_time": float(a.time[i_max]),
        "max_depth_gap_m": float(d_depth[int(np.abs(d_depth).argmax())]),
        "final_saturation_delta": float(d_sat[-1]),
        "final_depth_delta_m": float(d_depth[-1]),
        "overflow_delta_m3": b.summary["totals_m3"]["overflow_m3"] - a.summary["totals_m3"]["overflow_m3"],
    }


@dataclass(frozen=True, slots=True)
class Encoded:
    """A response body kept both raw and gzip-compressed, so a cache hit costs no CPU."""

    raw: bytes
    gz: bytes

    @classmethod
    def of(cls, raw: bytes) -> "Encoded":
        return cls(raw, gzip.compress(raw, compresslevel=6, mtime=0))


def encode(body: dict[str, Any]) -> bytes:
    return json.dumps(body, separators=(",", ":"), allow_nan=False).encode()
