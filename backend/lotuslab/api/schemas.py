"""Request / response contracts. Validation happens here, at the boundary."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..core.params import LotusParams, PondParams
from ..core.scenarios import PRESETS, Scenario

PresetName = Literal["live", "monsoon_surge", "heatwave", "overcast", "drought"]
assert set(PresetName.__args__) == set(PRESETS)  # type: ignore[attr-defined]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ScenarioIn(Strict):
    """A preset, optionally fine-tuned. Explicit fields override the preset's values."""

    preset: PresetName = "live"
    temperature_offset_c: float | None = Field(None, ge=-15, le=15)
    precipitation_multiplier: float | None = Field(None, ge=0, le=10)
    cloud_cover_offset_pct: float | None = Field(None, ge=-100, le=100)
    wind_multiplier: float | None = Field(None, ge=0, le=5)

    def to_scenario(self) -> Scenario:
        base = PRESETS[self.preset][1].as_dict()
        overrides = {k: v for k, v in self.model_dump(exclude={"preset"}).items() if v is not None}
        return Scenario(**{**base, **overrides})


class PondIn(Strict):
    surface_area_m2: float = Field(200.0, gt=0, le=1_000_000)
    max_depth_m: float = Field(1.5, gt=0, le=20)
    initial_depth_m: float = Field(1.0, ge=0, le=20)
    catchment_area_m2: float = Field(1500.0, ge=0, le=100_000_000)
    runoff_coeff_dry: float = Field(0.05, ge=0, le=1)
    runoff_coeff_wet: float = Field(0.6, ge=0, le=1)
    soil_capacity_mm: float = Field(40.0, ge=0, le=500)
    initial_soil_fraction: float = Field(0.3, ge=0, le=1)
    soil_drain_mm_per_day: float = Field(4.0, ge=0, le=100)
    evaporation_coeff: float = Field(1.05, ge=0, le=3)
    seepage_mm_per_day: float = Field(2.0, ge=0, le=200)

    @model_validator(mode="after")
    def _consistent(self) -> "PondIn":
        try:
            self.to_params().validate()
        except ValueError as exc:
            raise ValueError(str(exc)) from None
        return self

    def to_params(self) -> PondParams:
        return PondParams(**self.model_dump())


class LotusIn(Strict):
    initial_cover_fraction: float = Field(0.04, ge=0, le=1)
    max_growth_per_day: float = Field(0.6, gt=0, le=5)
    max_cover_fraction: float = Field(0.92, gt=0, le=1)
    t_min_c: float = Field(12.0, ge=-10, le=40)
    t_opt_c: float = Field(30.0, ge=0, le=50)
    t_max_c: float = Field(42.0, ge=5, le=60)
    light_half_sat_wm2: float = Field(220.0, gt=0, le=2000)
    depth_min_m: float = Field(0.15, ge=0, le=10)
    depth_opt_low_m: float = Field(0.4, ge=0, le=10)
    depth_opt_high_m: float = Field(1.6, ge=0, le=20)
    depth_max_m: float = Field(2.5, gt=0, le=30)
    base_mortality_per_day: float = Field(0.01, ge=0, le=2)
    dry_mortality_per_day: float = Field(0.2, ge=0, le=5)
    heat_mortality_per_day: float = Field(0.08, ge=0, le=5)

    @model_validator(mode="after")
    def _consistent(self) -> "LotusIn":
        try:
            self.to_params().validate()
        except ValueError as exc:
            raise ValueError(str(exc)) from None
        return self

    def to_params(self) -> LotusParams:
        return LotusParams(**self.model_dump())


class Location(Strict):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    start_date: dt.date
    days: int = Field(14, ge=1, le=366)
    source: Literal["auto", "synthetic"] = Field(
        "auto", description="auto = Open-Meteo; synthetic = labelled offline demo weather"
    )
    seed: int = Field(7, ge=0, le=2**31 - 1, description="only used by synthetic weather")


class SimulationRequest(Location):
    scenario: ScenarioIn = ScenarioIn()
    pond: PondIn = PondIn()
    lotus: LotusIn = LotusIn()


class CompareRequest(Location):
    baseline: ScenarioIn = ScenarioIn()
    variant: ScenarioIn = ScenarioIn(preset="heatwave")
    pond: PondIn = PondIn()
    lotus: LotusIn = LotusIn()


class SensitivityRequest(Location):
    temperature_offsets_c: list[float] = Field(default=[-4, -2, 0, 2, 4, 6], min_length=1, max_length=15)
    precipitation_multipliers: list[float] = Field(default=[0, 0.5, 1, 2, 3], min_length=1, max_length=15)
    pond: PondIn = PondIn()
    lotus: LotusIn = LotusIn()

    @model_validator(mode="after")
    def _ranges(self) -> "SensitivityRequest":
        if any(not -15 <= v <= 15 for v in self.temperature_offsets_c):
            raise ValueError("temperature offsets must be within [-15, 15]")
        if any(not 0 <= v <= 10 for v in self.precipitation_multipliers):
            raise ValueError("precipitation multipliers must be within [0, 10]")
        return self


# ---- responses (documented shapes; bodies are pre-serialised for speed) ---------


class Provenance(BaseModel):
    source: Literal["open-meteo-forecast", "open-meteo-archive", "synthetic"]
    fetched_at: float
    stale: bool
    cache: Literal["hit", "miss", "stale"]
    timezone: str
    utc_offset_s: int
    latitude: float
    longitude: float
    gaps_filled: dict[str, int]
    attribution: str | None


class TimelineOut(BaseModel):
    t0: float
    dt: float
    n: int
    columns: dict[str, list[float]]
    phase: list[int]


class RunOut(BaseModel):
    scenario: dict[str, float]
    timeline: TimelineOut
    summary: dict[str, Any]


class SimulationResponse(RunOut):
    model_version: str
    provenance: Provenance


class CompareResponse(BaseModel):
    model_version: str
    provenance: Provenance
    baseline: RunOut
    variant: RunOut
    divergence: dict[str, Any]


class SensitivityResponse(BaseModel):
    model_version: str
    provenance: Provenance
    temperature_offsets_c: list[float]
    precipitation_multipliers: list[float]
    final_cover_fraction: list[list[float]]
    final_saturation: list[list[float]]
    final_depth_m: list[list[float]]
    overflow_m3: list[list[float]]
    compute_ms: float


class PuzzleResponse(BaseModel):
    initial: float
    multiplier: float
    capacity: float
    days_to_fill: int
    half_full_day: float
    series: list[float]
