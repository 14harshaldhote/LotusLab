"""What-if transforms applied to a real weather series.

A scenario never invents a new weather series; it perturbs the observed or forecast
one in physically coupled ways, so the what-if pond stays comparable to the live pond.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .weather import BOUNDS, HourlyWeather


@dataclass(frozen=True, slots=True)
class Scenario:
    temperature_offset_c: float = 0.0
    precipitation_multiplier: float = 1.0
    cloud_cover_offset_pct: float = 0.0
    wind_multiplier: float = 1.0

    def is_identity(self) -> bool:
        return self == Scenario()

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


PRESETS: dict[str, tuple[str, Scenario]] = {
    "live": ("Weather exactly as observed or forecast", Scenario()),
    "monsoon_surge": (
        "Three times the rain under heavier cloud",
        Scenario(precipitation_multiplier=3.0, cloud_cover_offset_pct=30.0, temperature_offset_c=-1.5),
    ),
    "heatwave": (
        "Five degrees hotter, clearer skies, a third of the rain",
        Scenario(temperature_offset_c=5.0, cloud_cover_offset_pct=-25.0, precipitation_multiplier=0.3),
    ),
    "overcast": ("Persistent thick cloud, less sunlight", Scenario(cloud_cover_offset_pct=50.0, temperature_offset_c=-1.0)),
    "drought": (
        "No rain at all, two degrees warmer, windier",
        Scenario(precipitation_multiplier=0.0, temperature_offset_c=2.0, wind_multiplier=1.4),
    ),
}

# FAO-56 sensitivity of reference ET to air temperature is roughly 2-4 % per degree
# in warm climates; 3 % is used here. Wind enters ET0 roughly linearly for light winds.
ET0_PER_DEGREE = 0.03
ET0_WIND_WEIGHT = 0.35


def kasten_czeplak(cloud_pct: np.ndarray) -> np.ndarray:
    """Fraction of clear-sky radiation reaching the ground under cloud (0..1)."""
    return 1.0 - 0.75 * (np.clip(cloud_pct, 0.0, 100.0) / 100.0) ** 3.4


def apply(weather: HourlyWeather, s: Scenario) -> HourlyWeather:
    if s.is_identity():
        return weather
    if s.precipitation_multiplier < 0 or s.wind_multiplier < 0:
        raise ValueError("multipliers must be >= 0")

    temp = weather.temperature_c + s.temperature_offset_c
    rain = weather.precipitation_mm * s.precipitation_multiplier
    cloud_old = weather.cloud_cover_pct
    cloud_new = np.clip(cloud_old + s.cloud_cover_offset_pct, 0.0, 100.0)
    radiation = weather.shortwave_wm2 * kasten_czeplak(cloud_new) / kasten_czeplak(cloud_old)
    wind = weather.wind_speed_ms * s.wind_multiplier

    et0 = weather.et0_mm * (1.0 + ET0_PER_DEGREE * s.temperature_offset_c)
    et0 = et0 * (1.0 + ET0_WIND_WEIGHT * (s.wind_multiplier - 1.0))
    # radiation-driven share of ET0 follows the sunlight change
    with np.errstate(divide="ignore", invalid="ignore"):
        rad_ratio = np.where(weather.shortwave_wm2 > 1.0, radiation / weather.shortwave_wm2, 1.0)
    et0 = et0 * (0.3 + 0.7 * rad_ratio)

    return weather.with_columns(
        temperature_c=np.clip(temp, *BOUNDS["temperature_c"]),
        precipitation_mm=np.clip(rain, *BOUNDS["precipitation_mm"]),
        cloud_cover_pct=cloud_new,
        shortwave_wm2=np.clip(radiation, *BOUNDS["shortwave_wm2"]),
        wind_speed_ms=np.clip(wind, *BOUNDS["wind_speed_ms"]),
        et0_mm=np.clip(et0, *BOUNDS["et0_mm"]),
    )
