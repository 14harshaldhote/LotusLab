"""Pond geometry and catchment runoff.

The basin is a paraboloid of revolution: a natural bowl that is shallow at the edges
and deepest in the middle. With brim area ``A`` and spill depth ``H``::

    area(h)   = A * h / H
    volume(h) = A * h^2 / (2 H)
    depth(V)  = sqrt(2 V H / A)

All three are closed form, so converting between volume, depth and wetted area costs
a multiply and a square root per step.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .params import PondParams


@dataclass(frozen=True, slots=True)
class Bathymetry:
    area_full_m2: float
    depth_full_m: float

    @classmethod
    def from_params(cls, p: PondParams) -> "Bathymetry":
        return cls(p.surface_area_m2, p.max_depth_m)

    @property
    def volume_full_m3(self) -> float:
        return self.area_full_m2 * self.depth_full_m / 2.0

    def area(self, depth_m: float) -> float:
        return self.area_full_m2 * max(depth_m, 0.0) / self.depth_full_m

    def volume(self, depth_m: float) -> float:
        h = max(depth_m, 0.0)
        return self.area_full_m2 * h * h / (2.0 * self.depth_full_m)

    def depth(self, volume_m3: float) -> float:
        return math.sqrt(2.0 * max(volume_m3, 0.0) * self.depth_full_m / self.area_full_m2)


def runoff_mm(rain_mm: float, soil_mm: float, p: PondParams) -> tuple[float, float]:
    """Split one hour of rain on the catchment into runoff and soil storage.

    A single-bucket soil store: the wetter the soil, the larger the share that runs
    off (variable source area idea), and anything beyond capacity runs off entirely.
    Returns ``(runoff_mm, new_soil_mm)``.
    """
    if rain_mm <= 0.0:
        return 0.0, soil_mm
    cap = p.soil_capacity_mm
    wetness = soil_mm / cap if cap > 0 else 1.0
    coeff = p.runoff_coeff_dry + (p.runoff_coeff_wet - p.runoff_coeff_dry) * wetness
    quick = rain_mm * coeff
    soil = soil_mm + rain_mm - quick
    excess = max(soil - cap, 0.0)
    return quick + excess, soil - excess
