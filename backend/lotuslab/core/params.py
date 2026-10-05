"""Model parameters. Defaults describe a small natural garden-scale pond."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class PondParams:
    surface_area_m2: float = 200.0  # water surface when brim-full (at spill level)
    max_depth_m: float = 1.5  # depth at the spill point; deeper water overflows
    initial_depth_m: float = 1.0
    catchment_area_m2: float = 1500.0  # surrounding land that drains into the pond
    runoff_coeff_dry: float = 0.05  # fraction of rain that runs off a dry catchment
    runoff_coeff_wet: float = 0.6  # ... and a saturated one
    soil_capacity_mm: float = 40.0  # catchment soil storage that must fill first
    initial_soil_fraction: float = 0.3
    soil_drain_mm_per_day: float = 4.0  # drying of the catchment soil store
    evaporation_coeff: float = 1.05  # open-water evaporation / FAO-56 ET0
    seepage_mm_per_day: float = 2.0  # loss through the bed, over the wetted area

    def validate(self) -> None:
        _positive(self, "surface_area_m2", "max_depth_m")
        _non_negative(
            self,
            "initial_depth_m",
            "catchment_area_m2",
            "soil_capacity_mm",
            "soil_drain_mm_per_day",
            "evaporation_coeff",
            "seepage_mm_per_day",
        )
        _fraction(self, "runoff_coeff_dry", "runoff_coeff_wet", "initial_soil_fraction")
        if self.initial_depth_m > self.max_depth_m:
            raise ValueError("initial_depth_m cannot exceed max_depth_m")
        if self.runoff_coeff_dry > self.runoff_coeff_wet:
            raise ValueError("runoff_coeff_dry must not exceed runoff_coeff_wet")


@dataclass(frozen=True, slots=True)
class LotusParams:
    initial_cover_fraction: float = 0.04  # of the brim-full surface
    max_growth_per_day: float = 0.6  # intrinsic rate at optimum temperature and full light
    max_cover_fraction: float = 0.92  # leaves cannot pave every square metre
    t_min_c: float = 12.0  # cardinal temperatures for growth
    t_opt_c: float = 30.0
    t_max_c: float = 42.0
    light_half_sat_wm2: float = 220.0
    depth_min_m: float = 0.15  # below this the rhizomes are exposed
    depth_opt_low_m: float = 0.4
    depth_opt_high_m: float = 1.6
    depth_max_m: float = 2.5
    base_mortality_per_day: float = 0.01
    dry_mortality_per_day: float = 0.2
    heat_mortality_per_day: float = 0.08

    def validate(self) -> None:
        _fraction(self, "initial_cover_fraction", "max_cover_fraction")
        _positive(self, "max_growth_per_day", "light_half_sat_wm2")
        _non_negative(self, "base_mortality_per_day", "dry_mortality_per_day", "heat_mortality_per_day")
        if not self.t_min_c < self.t_opt_c < self.t_max_c:
            raise ValueError("require t_min_c < t_opt_c < t_max_c")
        if not 0 <= self.depth_min_m < self.depth_opt_low_m <= self.depth_opt_high_m < self.depth_max_m:
            raise ValueError("require depth_min < depth_opt_low <= depth_opt_high < depth_max")
        if self.initial_cover_fraction > self.max_cover_fraction:
            raise ValueError("initial cover exceeds max cover")


def params_key(*objs: object) -> tuple:
    """Hashable, order-stable key for caching simulations."""
    return tuple(tuple(sorted(asdict(o).items())) for o in objs)  # type: ignore[arg-type]


def _positive(obj: object, *names: str) -> None:
    for n in names:
        if not getattr(obj, n) > 0:
            raise ValueError(f"{n} must be > 0")


def _non_negative(obj: object, *names: str) -> None:
    for n in names:
        if not getattr(obj, n) >= 0:
            raise ValueError(f"{n} must be >= 0")


def _fraction(obj: object, *names: str) -> None:
    for n in names:
        if not 0 <= getattr(obj, n) <= 1:
            raise ValueError(f"{n} must be within [0, 1]")
