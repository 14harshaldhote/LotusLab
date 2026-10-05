"""Solar position (NOAA algorithm), vectorised over time.

Accuracy is about 0.01 degrees for years 1800-2100, far finer than anything the
pond model or the sky rendering needs. Every function accepts numpy arrays of unix
seconds (UTC) so a whole timeline is computed in one pass.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Day-phase codes shared with the frontend.
PHASE_NIGHT = 0  # sun below -6 deg (darker than civil twilight)
PHASE_TWILIGHT = 1  # -6 .. 0 deg
PHASE_GOLDEN = 2  # 0 .. 6 deg
PHASE_DAY = 3  # above 6 deg


@dataclass(frozen=True, slots=True)
class SolarPosition:
    elevation_deg: np.ndarray
    azimuth_deg: np.ndarray
    hour_angle_deg: np.ndarray


def solar_position(unix_s: np.ndarray, lat_deg: float, lon_deg: float) -> SolarPosition:
    """Sun elevation (refraction-corrected) and azimuth (clockwise from north)."""
    t = np.asarray(unix_s, dtype=np.float64)
    jd = t / 86400.0 + 2440587.5
    jc = (jd - 2451545.0) / 36525.0

    l0 = np.mod(280.46646 + jc * (36000.76983 + jc * 0.0003032), 360.0)
    m = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    m_r = np.radians(m)
    center = (
        np.sin(m_r) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
        + np.sin(2 * m_r) * (0.019993 - 0.000101 * jc)
        + np.sin(3 * m_r) * 0.000289
    )
    true_long = l0 + center
    omega = np.radians(125.04 - 1934.136 * jc)
    app_long = true_long - 0.00569 - 0.00478 * np.sin(omega)
    mean_obliq = 23.0 + (26.0 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60.0) / 60.0
    obliq = np.radians(mean_obliq + 0.00256 * np.cos(omega))
    decl = np.arcsin(np.sin(obliq) * np.sin(np.radians(app_long)))

    y = np.tan(obliq / 2.0) ** 2
    l0_r = np.radians(l0)
    eq_time = 4.0 * np.degrees(
        y * np.sin(2 * l0_r)
        - 2 * e * np.sin(m_r)
        + 4 * e * y * np.sin(m_r) * np.cos(2 * l0_r)
        - 0.5 * y * y * np.sin(4 * l0_r)
        - 1.25 * e * e * np.sin(2 * m_r)
    )

    minutes_utc = np.mod(t, 86400.0) / 60.0
    true_solar = np.mod(minutes_utc + eq_time + 4.0 * lon_deg, 1440.0)
    hour_angle = true_solar / 4.0 - 180.0  # -180..180, negative = morning

    lat = np.radians(lat_deg)
    ha = np.radians(hour_angle)
    cos_zen = np.clip(np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.cos(ha), -1.0, 1.0)
    zenith = np.arccos(cos_zen)
    elevation = 90.0 - np.degrees(zenith)

    sin_zen = np.sin(zenith)
    denom = np.cos(lat) * sin_zen
    with np.errstate(divide="ignore", invalid="ignore"):
        cos_az = np.where(np.abs(denom) > 1e-9, (np.sin(lat) * cos_zen - np.sin(decl)) / denom, 1.0)
    az = np.degrees(np.arccos(np.clip(cos_az, -1.0, 1.0)))
    azimuth = np.where(hour_angle > 0, np.mod(az + 180.0, 360.0), np.mod(540.0 - az, 360.0))

    return SolarPosition(elevation + _refraction(elevation), azimuth, hour_angle)


def _refraction(elev: np.ndarray) -> np.ndarray:
    """Atmospheric refraction correction in degrees (NOAA piecewise fit)."""
    te = np.tan(np.radians(np.clip(elev, -89.0, 89.0)))
    with np.errstate(divide="ignore", invalid="ignore"):
        high = 58.1 / te - 0.07 / te**3 + 0.000086 / te**5
    mid = 1735.0 + elev * (-518.2 + elev * (103.4 + elev * (-12.79 + elev * 0.711)))
    low = -20.772 / np.where(te == 0, 1e-9, te)
    arcsec = np.where(elev > 85.0, 0.0, np.where(elev > 5.0, high, np.where(elev > -0.575, mid, low)))
    return arcsec / 3600.0


def day_phase(elevation_deg: np.ndarray) -> np.ndarray:
    """Classify each sun elevation into a PHASE_* code."""
    e = np.asarray(elevation_deg)
    return np.select(
        [e < -6.0, e < 0.0, e < 6.0],
        [PHASE_NIGHT, PHASE_TWILIGHT, PHASE_GOLDEN],
        default=PHASE_DAY,
    ).astype(np.int8)


def clear_sky_ghi(elevation_deg: np.ndarray) -> np.ndarray:
    """Haurwitz clear-sky global horizontal irradiance (W/m2)."""
    cz = np.sin(np.radians(np.maximum(elevation_deg, 0.0)))
    with np.errstate(divide="ignore", over="ignore"):
        ghi = np.where(cz > 0.0, 1098.0 * cz * np.exp(-0.057 / np.maximum(cz, 1e-6)), 0.0)
    return ghi
