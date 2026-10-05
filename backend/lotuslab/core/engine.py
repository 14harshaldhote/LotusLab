"""Simulation engine: hourly weather in, a precomputed pond timeline out.

Algorithm
---------
1. Vectorised pre-pass over the whole series (numpy): solar position, day phase and
   the weather-only growth factors f_T and f_L. These do not depend on pond state.
2. One sequential pass over the hours (the only part that must be sequential because
   each hour depends on the last): soil bucket, water balance, overflow, lotus cover.
   It works on plain Python floats with pre-bound locals, which is the fastest way to
   run a scalar recurrence in CPython without extra compilers.
3. Prefix sums over every flux so the volume of rain, evaporation or overflow between
   any two instants is an O(1) difference.

The result is a ``Timeline``: column arrays on a regular hourly grid. ``seek(t)`` is
O(1): one index computation and a linear interpolation between neighbouring rows.

Convention: row 0 is the initial condition at ``time[0]``. Row k (k >= 1) is the state
at ``time[k]`` after applying the weather of the hour ending at ``time[k]``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from . import lotus as lotus_model
from .hydrology import Bathymetry, runoff_mm
from .params import LotusParams, PondParams
from .solar import day_phase, solar_position
from .weather import HOUR_S, VARIABLES, HourlyWeather

STATE_COLUMNS = (
    "depth_m",
    "volume_m3",
    "surface_area_m2",
    "fill_fraction",
    "soil_mm",
    "cover_m2",
    "cover_fraction",
    "cover_of_water",
    "saturation",
    "growth_rate_per_day",
    "f_temperature",
    "f_light",
    "f_depth",
)
FLUX_COLUMNS = ("rain_m3", "runoff_m3", "evaporation_m3", "seepage_m3", "overflow_m3")
SOLAR_COLUMNS = ("sun_elevation_deg", "sun_azimuth_deg")
CUMULATIVE_COLUMNS = tuple(f"cum_{c}" for c in FLUX_COLUMNS)
ALL_COLUMNS = (*VARIABLES, *SOLAR_COLUMNS, *STATE_COLUMNS, *FLUX_COLUMNS, *CUMULATIVE_COLUMNS)


@dataclass(frozen=True)
class Timeline:
    t0: float
    dt: float
    time: np.ndarray
    columns: dict[str, np.ndarray]
    phase: np.ndarray  # int8 day-phase codes per row
    summary: dict[str, Any]

    def __len__(self) -> int:
        return int(self.time.shape[0])

    @property
    def t_end(self) -> float:
        return float(self.time[-1])

    def __post_init__(self) -> None:
        # One contiguous (rows x columns) matrix makes seek a single fancy-index.
        names = tuple(self.columns)
        object.__setattr__(self, "_names", names)
        object.__setattr__(self, "_matrix", np.column_stack([self.columns[n] for n in names]))

    def index_of(self, t: float) -> tuple[int, float]:
        """Row index and fractional position for time ``t`` (clamped to range)."""
        x = (t - self.t0) / self.dt
        n = len(self)
        if x <= 0.0:
            return 0, 0.0
        if x >= n - 1:
            return n - 1, 0.0
        i = int(x)
        return i, x - i

    def seek(self, t: float) -> dict[str, float]:
        """Interpolated model state at any instant. O(number of columns)."""
        i, frac = self.index_of(t)
        m: np.ndarray = self._matrix  # type: ignore[attr-defined]
        row = m[i] if frac == 0.0 else m[i] + (m[i + 1] - m[i]) * frac
        out = dict(zip(self._names, row.tolist()))  # type: ignore[attr-defined]
        out["time"] = float(t)
        e = out["sun_elevation_deg"]
        out["phase"] = 0 if e < -6.0 else 1 if e < 0.0 else 2 if e < 6.0 else 3  # see solar.day_phase
        return out

    def between(self, column: str, t_a: float, t_b: float) -> float:
        """Total of a flux between two instants via prefix sums. O(1)."""
        cum = self.columns[f"cum_{column}"]
        a, fa = self.index_of(min(t_a, t_b))
        b, fb = self.index_of(max(t_a, t_b))
        val_a = cum[a] + (cum[min(a + 1, len(cum) - 1)] - cum[a]) * fa
        val_b = cum[b] + (cum[min(b + 1, len(cum) - 1)] - cum[b]) * fb
        return float(val_b - val_a)


def simulate(
    weather: HourlyWeather,
    lat: float,
    lon: float,
    pond: PondParams | None = None,
    lotus: LotusParams | None = None,
) -> Timeline:
    pond = pond or PondParams()
    lotus = lotus or LotusParams()
    pond.validate()
    lotus.validate()
    n = len(weather)
    if n < 2:
        raise ValueError("need at least two hourly rows")

    # ---- 1. vectorised pre-pass -------------------------------------------------
    sun = solar_position(weather.time, lat, lon)
    f_t = lotus_model.temperature_factor(weather.temperature_c, lotus)
    f_l = lotus_model.light_factor(weather.shortwave_wm2, lotus)
    heat = weather.temperature_c >= lotus.t_max_c

    # ---- 2. sequential state recurrence -----------------------------------------
    bath = Bathymetry.from_params(pond)
    a_full = bath.area_full_m2
    h_full = bath.depth_full_m
    v_full = bath.volume_full_m3
    dt_days = HOUR_S / 86400.0
    soil_drain = pond.soil_drain_mm_per_day * dt_days
    seep_m = pond.seepage_mm_per_day * dt_days / 1000.0
    kw = pond.evaporation_coeff
    catchment = pond.catchment_area_m2
    r_max = lotus.max_growth_per_day
    k_frac = lotus.max_cover_fraction
    m_base = lotus.base_mortality_per_day
    m_dry = lotus.dry_mortality_per_day
    m_heat = lotus.heat_mortality_per_day
    depth_min = lotus.depth_min_m
    depth_factor = lotus_model.depth_factor
    logistic_step = lotus_model.logistic_step
    exp = math.exp
    sqrt = math.sqrt

    rain_l = weather.precipitation_mm.tolist()
    et0_l = weather.et0_mm.tolist()
    ft_l = f_t.tolist()
    fl_l = f_l.tolist()
    heat_l = heat.tolist()

    depth = pond.initial_depth_m
    volume = bath.volume(depth)
    soil = pond.initial_soil_fraction * pond.soil_capacity_mm
    cover = min(lotus.initial_cover_fraction * a_full, k_frac * bath.area(depth))

    cols = {name: [0.0] * n for name in (*STATE_COLUMNS, *FLUX_COLUMNS)}
    c_depth, c_vol, c_area, c_fill = cols["depth_m"], cols["volume_m3"], cols["surface_area_m2"], cols["fill_fraction"]
    c_soil, c_cover, c_cf, c_cw = cols["soil_mm"], cols["cover_m2"], cols["cover_fraction"], cols["cover_of_water"]
    c_sat = cols["saturation"]
    c_rate, c_ft, c_fl, c_fd = cols["growth_rate_per_day"], cols["f_temperature"], cols["f_light"], cols["f_depth"]
    c_rain, c_run, c_evap, c_seep, c_over = (cols[c] for c in FLUX_COLUMNS)

    def record(k: int, rate: float, fd: float) -> None:
        area = a_full * depth / h_full
        c_depth[k] = depth
        c_vol[k] = volume
        c_area[k] = area
        c_fill[k] = volume / v_full
        c_soil[k] = soil
        c_cover[k] = cover
        c_cf[k] = cover / a_full
        c_cw[k] = cover / area if area > 0 else 0.0
        c_sat[k] = cover / (k_frac * area) if area > 0 else 0.0
        c_rate[k] = rate
        c_ft[k] = ft_l[k]
        c_fl[k] = fl_l[k]
        c_fd[k] = fd

    record(0, 0.0, depth_factor(depth, lotus))

    for k in range(1, n):
        # catchment soil bucket and runoff
        soil = soil - soil_drain if soil > soil_drain else 0.0
        rain_mm = rain_l[k]
        run_mm, soil = runoff_mm(rain_mm, soil, pond)

        # water balance on the current wetted area
        area = a_full * depth / h_full
        rain_in = rain_mm * 0.001 * a_full  # rain on the whole basin footprint
        run_in = run_mm * 0.001 * catchment
        evap = kw * et0_l[k] * 0.001 * area
        seep = seep_m * area
        available = volume + rain_in + run_in
        losses = evap + seep
        if losses > available:  # cannot lose water that is not there
            scale = available / losses if losses > 0 else 0.0
            evap *= scale
            seep *= scale
            losses = available
        volume = available - losses
        overflow = volume - v_full if volume > v_full else 0.0
        volume -= overflow
        depth = sqrt(2.0 * volume * h_full / a_full)

        # lotus: growth limited by temperature, light, depth; capacity = water surface
        fd = depth_factor(depth, lotus)
        r = r_max * ft_l[k] * fl_l[k] * fd
        capacity = k_frac * a_full * depth / h_full
        cover = logistic_step(cover, r, capacity, dt_days) if cover > 0.0 else 0.0
        m = m_base + (m_dry if depth < depth_min else 0.0) + (m_heat if heat_l[k] else 0.0)
        cover *= exp(-m * dt_days)
        if cover > capacity:  # leaves stranded on a shrinking shoreline
            cover = capacity

        c_rain[k] = rain_in
        c_run[k] = run_in
        c_evap[k] = evap
        c_seep[k] = seep
        c_over[k] = overflow
        record(k, r - m, fd)

    # ---- 3. assemble columns, prefix sums --------------------------------------
    columns: dict[str, np.ndarray] = {name: weather.column(name).astype(np.float64) for name in VARIABLES}
    columns["sun_elevation_deg"] = sun.elevation_deg
    columns["sun_azimuth_deg"] = _unwrap_azimuth(sun.azimuth_deg)
    for name, values in cols.items():
        columns[name] = np.asarray(values, dtype=np.float64)
    for name in FLUX_COLUMNS:
        columns[f"cum_{name}"] = np.cumsum(columns[name])

    phase = day_phase(sun.elevation_deg)
    summary = _summarise(weather.time, columns, phase, pond, lotus, bath)
    return Timeline(
        t0=float(weather.time[0]),
        dt=float(HOUR_S),
        time=weather.time.astype(np.float64),
        columns=columns,
        phase=phase,
        summary=summary,
    )


def _unwrap_azimuth(az: np.ndarray) -> np.ndarray:
    """Remove 360 deg jumps so linear interpolation never sweeps the wrong way."""
    return np.degrees(np.unwrap(np.radians(az)))


def _first_time(time: np.ndarray, mask: np.ndarray) -> float | None:
    idx = np.flatnonzero(mask)
    return float(time[idx[0]]) if idx.size else None


def _summarise(
    time: np.ndarray,
    c: dict[str, np.ndarray],
    phase: np.ndarray,
    pond: PondParams,
    lotus: LotusParams,
    bath: Bathymetry,
) -> dict[str, Any]:
    cover_frac = c["cover_fraction"]
    sat = c["saturation"]  # cover relative to what the current water surface can hold
    totals = {name: float(c[f"cum_{name}"][-1]) for name in FLUX_COLUMNS}
    v0, v1 = float(c["volume_m3"][0]), float(c["volume_m3"][-1])
    balance_error = (v1 - v0) - (
        totals["rain_m3"] + totals["runoff_m3"] - totals["evaporation_m3"] - totals["seepage_m3"] - totals["overflow_m3"]
    )
    rate = c["growth_rate_per_day"][1:]
    positive = rate[rate > 0]
    daylight_hours = float(np.count_nonzero(phase >= 2))
    return {
        "hours": int(time.size),
        "start": float(time[0]),
        "end": float(time[-1]),
        "initial_depth_m": float(c["depth_m"][0]),
        "final_depth_m": float(c["depth_m"][-1]),
        "min_depth_m": float(c["depth_m"].min()),
        "max_depth_m": float(c["depth_m"].max()),
        "initial_cover_fraction": float(cover_frac[0]),
        "final_cover_fraction": float(cover_frac[-1]),
        "peak_cover_fraction": float(cover_frac.max()),
        "peak_cover_time": float(time[int(cover_frac.argmax())]),
        "final_saturation": float(sat[-1]),
        "peak_saturation": float(sat.max()),
        "totals_m3": totals,
        "mass_balance_error_m3": float(balance_error),
        "overflow_hours": int(np.count_nonzero(c["overflow_m3"] > 0)),
        "daylight_hours": daylight_hours,
        "volume_full_m3": bath.volume_full_m3,
        "milestones": {
            "cover_25": _first_time(time, sat >= 0.25),
            "cover_50": _first_time(time, sat >= 0.5),
            "cover_full": _first_time(time, sat >= 0.98),
            "first_overflow": _first_time(time, c["overflow_m3"] > 0),
            "first_stranded": _first_time(time, c["depth_m"] < lotus.depth_min_m),
        },
        "mean_positive_growth_per_day": float(positive.mean()) if positive.size else 0.0,
    }
