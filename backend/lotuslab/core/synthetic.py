"""Deterministic synthetic weather for offline demos and tests.

Responses built from this generator are always labelled ``source: synthetic``. It is
never used silently in place of real data.
"""

from __future__ import annotations

import numpy as np

from .solar import clear_sky_ghi, solar_position
from .scenarios import kasten_czeplak
from .weather import HOUR_S, HourlyWeather, normalise, priestley_taylor_et0


def generate(
    start_unix: float,
    hours: int,
    lat: float,
    lon: float,
    seed: int = 7,
    mean_temp_c: float = 27.0,
    diurnal_range_c: float = 9.0,
    rain_events_per_week: float = 2.0,
) -> HourlyWeather:
    if hours < 2:
        raise ValueError("hours must be >= 2")
    rng = np.random.default_rng(seed)
    t = start_unix - (start_unix % HOUR_S) + HOUR_S * np.arange(hours, dtype=np.float64)

    sun = solar_position(t, lat, lon)
    # temperature peaks ~3 h after solar noon; hour angle 45 deg = 3 h
    temp = mean_temp_c + 0.5 * diurnal_range_c * np.cos(np.radians(sun.hour_angle_deg - 45.0))
    temp += _ar1(rng, hours, sigma=2.0, phi=0.995)  # slow, mean-reverting synoptic drift

    # cloud: mean-reverting noise around 40 %, smoothed
    cloud = np.clip(40.0 + _ar1(rng, hours, sigma=25.0, phi=0.97), 0.0, 100.0)
    cloud = np.convolve(cloud, np.ones(6) / 6.0, mode="same")

    rain = np.zeros(hours)
    n_events = rng.poisson(rain_events_per_week * hours / (24 * 7))
    for start in rng.integers(0, hours, n_events):
        length = int(rng.integers(1, 7))
        total = float(rng.gamma(2.0, 6.0))
        rain[start : start + length] += total / length
        cloud[max(0, start - 2) : start + length + 1] = np.maximum(cloud[max(0, start - 2) : start + length + 1], 85.0)

    radiation = clear_sky_ghi(sun.elevation_deg) * kasten_czeplak(cloud)
    humidity = np.clip(55.0 + 0.4 * cloud - 1.5 * (temp - mean_temp_c), 15.0, 100.0)
    wind = np.abs(2.5 + _ar1(rng, hours, sigma=1.0, phi=0.95))

    return normalise(
        t,
        {
            "temperature_c": temp,
            "precipitation_mm": rain,
            "cloud_cover_pct": cloud,
            "wind_speed_ms": wind,
            "relative_humidity_pct": humidity,
            "shortwave_wm2": radiation,
            "et0_mm": priestley_taylor_et0(temp, radiation),
        },
    )


def _ar1(rng: np.random.Generator, n: int, sigma: float, phi: float) -> np.ndarray:
    """Stationary AR(1) noise with marginal standard deviation ``sigma``."""
    eps = rng.normal(0.0, sigma * np.sqrt(1.0 - phi * phi), n)
    out = np.empty(n)
    acc = rng.normal(0.0, sigma)
    for i in range(n):
        acc = phi * acc + eps[i]
        out[i] = acc
    return out
