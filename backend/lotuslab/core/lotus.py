"""Lotus growth response functions.

Cover ``C`` (m2 of leaves on the water) follows logistic growth towards a capacity set
by the *current* water surface::

    dC/dt = r(t) * C * (1 - C / K(t)) - m(t) * C
    K(t)  = max_cover_fraction * area(depth(t))
    r(t)  = r_max * f_T(T) * f_L(I) * f_W(h)

The weather-only factors (temperature and light) are vectorised over the whole series
up front; only the depth factor depends on the evolving pond state.
"""

from __future__ import annotations

import math

import numpy as np

from .params import LotusParams


def temperature_factor(temp_c: np.ndarray, p: LotusParams) -> np.ndarray:
    """Yan & Hunt (1999) beta function: 0 at t_min and t_max, 1 at t_opt."""
    t = np.asarray(temp_c, dtype=np.float64)
    inside = (t > p.t_min_c) & (t < p.t_max_c)
    tc = np.clip(t, p.t_min_c, p.t_max_c)
    exponent = (p.t_opt_c - p.t_min_c) / (p.t_max_c - p.t_opt_c)
    f = ((p.t_max_c - tc) / (p.t_max_c - p.t_opt_c)) * ((tc - p.t_min_c) / (p.t_opt_c - p.t_min_c)) ** exponent
    return np.where(inside, f, 0.0)


def light_factor(shortwave_wm2: np.ndarray, p: LotusParams) -> np.ndarray:
    """Saturating (Michaelis-Menten) light response, normalised to 1 at 1000 W/m2."""
    i = np.maximum(np.asarray(shortwave_wm2, dtype=np.float64), 0.0)
    ref = 1000.0 / (1000.0 + p.light_half_sat_wm2)
    return np.minimum((i / (i + p.light_half_sat_wm2)) / ref, 1.0)


def depth_factor(depth_m: float, p: LotusParams) -> float:
    """Trapezoid: 0 when stranded or drowned, 1 across the preferred depth band."""
    h = depth_m
    if h <= p.depth_min_m or h >= p.depth_max_m:
        return 0.0
    if h < p.depth_opt_low_m:
        return (h - p.depth_min_m) / (p.depth_opt_low_m - p.depth_min_m)
    if h <= p.depth_opt_high_m:
        return 1.0
    return (p.depth_max_m - h) / (p.depth_max_m - p.depth_opt_high_m)


def logistic_step(cover: float, rate: float, capacity: float, dt_days: float) -> float:
    """Exact solution of dC/dt = r C (1 - C/K) over dt.

    Unconditionally stable for any dt, keeps 0 <= C <= K when 0 <= C0 <= K, and
    reduces to C0 * exp(r dt) when K is large.
    """
    if cover <= 0.0 or capacity <= 0.0:
        return 0.0
    g = math.exp(rate * dt_days)
    return capacity * cover * g / (capacity + cover * (g - 1.0))
