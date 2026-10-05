"""Normalised hourly weather series.

Every provider (Open-Meteo, the synthetic generator, a test fixture) is converted into
one ``HourlyWeather`` with SI-ish units, a regular hourly grid and no gaps. The rest of
the model never has to think about provider quirks.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

HOUR_S = 3600

# variable name -> (min, max) physically plausible bounds used for clipping
BOUNDS: dict[str, tuple[float, float]] = {
    "temperature_c": (-60.0, 60.0),
    "precipitation_mm": (0.0, 300.0),
    "cloud_cover_pct": (0.0, 100.0),
    "wind_speed_ms": (0.0, 80.0),
    "relative_humidity_pct": (0.0, 100.0),
    "shortwave_wm2": (0.0, 1400.0),
    "et0_mm": (0.0, 3.0),
}
VARIABLES = tuple(BOUNDS)


class WeatherError(ValueError):
    """Raised when a weather series cannot be normalised into a usable grid."""


@dataclass(frozen=True)
class HourlyWeather:
    time: np.ndarray  # unix seconds, UTC, strictly hourly
    temperature_c: np.ndarray
    precipitation_mm: np.ndarray  # sum over the hour ending at time[k]
    cloud_cover_pct: np.ndarray
    wind_speed_ms: np.ndarray
    relative_humidity_pct: np.ndarray
    shortwave_wm2: np.ndarray  # mean over the hour ending at time[k]
    et0_mm: np.ndarray  # FAO-56 reference evapotranspiration over the hour
    utc_offset_s: int = 0
    gaps_filled: dict[str, int] = field(default_factory=dict)

    def __len__(self) -> int:
        return int(self.time.shape[0])

    def column(self, name: str) -> np.ndarray:
        return getattr(self, name)

    def with_columns(self, **cols: np.ndarray) -> "HourlyWeather":
        return replace(self, **cols)

    def slice(self, start: int, stop: int) -> "HourlyWeather":
        cols = {name: self.column(name)[start:stop] for name in ("time", *VARIABLES)}
        return replace(self, **cols)


def normalise(
    time: np.ndarray | list[float],
    columns: dict[str, np.ndarray | list[float | None]],
    utc_offset_s: int = 0,
) -> HourlyWeather:
    """Validate a raw series and return a gap-free, clipped ``HourlyWeather``.

    * ``time`` must be strictly increasing hourly unix seconds.
    * Missing values (None / NaN / inf) are linearly interpolated; a column that is
      entirely missing is derived (ET0, radiation) or set to a neutral default.
    """
    t = np.asarray(time, dtype=np.float64)
    if t.ndim != 1 or t.size < 2:
        raise WeatherError("need at least two hourly time steps")
    if not np.all(np.isfinite(t)):
        raise WeatherError("time axis contains non-finite values")
    steps = np.diff(t)
    if not np.all(steps == HOUR_S):
        raise WeatherError("time axis must be a regular hourly grid")

    out: dict[str, np.ndarray] = {}
    filled: dict[str, int] = {}
    missing_entirely: list[str] = []
    for name in VARIABLES:
        raw = columns.get(name)
        if raw is None:
            missing_entirely.append(name)
            continue
        arr = np.array([np.nan if v is None else v for v in raw], dtype=np.float64)
        if arr.shape != t.shape:
            raise WeatherError(f"{name} has {arr.size} values for {t.size} time steps")
        arr[~np.isfinite(arr)] = np.nan
        n_missing = int(np.isnan(arr).sum())
        if n_missing == arr.size:
            missing_entirely.append(name)
            continue
        if n_missing:
            arr = _interp_gaps(arr)
            filled[name] = n_missing
        lo, hi = BOUNDS[name]
        out[name] = np.clip(arr, lo, hi)

    for name in missing_entirely:
        out[name] = _derive(name, out, t.size)
        filled[name] = t.size

    return HourlyWeather(time=t, utc_offset_s=int(utc_offset_s), gaps_filled=filled, **out)


def _interp_gaps(arr: np.ndarray) -> np.ndarray:
    idx = np.arange(arr.size)
    ok = ~np.isnan(arr)
    return np.interp(idx, idx[ok], arr[ok])


def _derive(name: str, have: dict[str, np.ndarray], n: int) -> np.ndarray:
    if name == "precipitation_mm":
        return np.zeros(n)
    if name == "cloud_cover_pct":
        return np.full(n, 50.0)
    if name == "wind_speed_ms":
        return np.full(n, 2.0)
    if name == "relative_humidity_pct":
        return np.full(n, 60.0)
    if name == "temperature_c":
        raise WeatherError("temperature is required")
    if name == "shortwave_wm2":
        raise WeatherError("shortwave radiation is required")
    if name == "et0_mm":
        return priestley_taylor_et0(have["temperature_c"], have["shortwave_wm2"])
    raise WeatherError(f"cannot derive {name}")  # pragma: no cover


def priestley_taylor_et0(temperature_c: np.ndarray, shortwave_wm2: np.ndarray) -> np.ndarray:
    """Hourly evaporation estimate (mm) when the provider gives no ET0.

    Priestley-Taylor with alpha=1.26, net radiation ~= 0.77 * (1 - albedo 0.08) * Rs.
    """
    t = temperature_c
    es = 0.6108 * np.exp(17.27 * t / (t + 237.3))
    delta = 4098.0 * es / (t + 237.3) ** 2  # kPa/K
    gamma = 0.066  # kPa/K near sea level
    rn_mj = 0.77 * 0.92 * shortwave_wm2 * 0.0036  # W/m2 over an hour -> MJ/m2
    et = 1.26 * delta / (delta + gamma) * rn_mj / 2.45
    return np.clip(et, 0.0, BOUNDS["et0_mm"][1])
