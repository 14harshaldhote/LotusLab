import math

import numpy as np
import pytest

from conftest import PUNE, T0, make_weather
from lotuslab.core import synthetic
from lotuslab.core.engine import simulate
from lotuslab.core.hydrology import Bathymetry, runoff_mm
from lotuslab.core.lotus import depth_factor, logistic_step, temperature_factor
from lotuslab.core.params import LotusParams, PondParams


def test_bathymetry_round_trip():
    b = Bathymetry(200.0, 1.5)
    for h in (0.0, 0.1, 0.75, 1.5):
        assert b.depth(b.volume(h)) == pytest.approx(h)
    assert b.volume(1.5) == pytest.approx(b.volume_full_m3) == pytest.approx(150.0)
    assert b.area(0.75) == pytest.approx(100.0)


def test_mass_balance_closes_exactly_over_a_year():
    w = synthetic.generate(T0, 24 * 365, *PUNE, seed=3)
    tl = simulate(w, *PUNE)
    assert abs(tl.summary["mass_balance_error_m3"]) < 1e-6
    assert tl.summary["hours"] == 24 * 365


def test_overflow_caps_volume_at_spill_level():
    w = make_weather(hours=72, rain=25.0)  # absurd storm
    tl = simulate(w, *PUNE, pond=PondParams(initial_depth_m=1.4))
    v_full = tl.summary["volume_full_m3"]
    assert tl.columns["volume_m3"].max() <= v_full + 1e-9
    assert tl.summary["totals_m3"]["overflow_m3"] > 0
    assert tl.summary["milestones"]["first_overflow"] is not None


def test_dry_weather_drains_and_never_goes_negative():
    w = make_weather(hours=24 * 120, rain=0.0, et0=0.6)
    tl = simulate(w, *PUNE, pond=PondParams(initial_depth_m=0.5))
    d = tl.columns["depth_m"]
    assert d.min() >= 0.0
    assert np.all(np.diff(d) <= 1e-12)  # no inputs -> monotone decline
    assert tl.summary["milestones"]["first_stranded"] is not None


def test_cover_bounded_by_current_water_surface():
    w = synthetic.generate(T0, 24 * 90, *PUNE, seed=11, rain_events_per_week=0.2)
    tl = simulate(w, *PUNE)
    k = LotusParams().max_cover_fraction
    assert np.all(tl.columns["cover_m2"] <= k * tl.columns["surface_area_m2"] + 1e-9)
    assert np.all(tl.columns["cover_m2"] >= 0.0)


def test_cover_grows_in_good_conditions():
    w = make_weather(hours=24 * 30, temp=30.0, rain=0.05, et0=0.1)
    tl = simulate(w, *PUNE)
    cf = tl.columns["cover_fraction"]
    assert cf[-1] > 5 * cf[0]
    assert tl.summary["milestones"]["cover_50"] is not None


def test_no_growth_when_too_cold():
    w = make_weather(hours=24 * 10, temp=5.0)
    tl = simulate(w, *PUNE)
    assert tl.columns["cover_fraction"][-1] < tl.columns["cover_fraction"][0]


def test_seek_matches_rows_and_interpolates():
    w = synthetic.generate(T0, 48, *PUNE)
    tl = simulate(w, *PUNE)
    s = tl.seek(tl.time[10])
    assert s["depth_m"] == pytest.approx(tl.columns["depth_m"][10])
    mid = tl.seek(tl.time[10] + 1800)
    expected = 0.5 * (tl.columns["cover_m2"][10] + tl.columns["cover_m2"][11])
    assert mid["cover_m2"] == pytest.approx(expected)
    # clamped outside the range
    assert tl.seek(tl.t0 - 1e6)["depth_m"] == pytest.approx(tl.columns["depth_m"][0])
    assert tl.seek(tl.t_end + 1e6)["depth_m"] == pytest.approx(tl.columns["depth_m"][-1])


def test_between_uses_prefix_sums():
    w = synthetic.generate(T0, 24 * 10, *PUNE, rain_events_per_week=6)
    tl = simulate(w, *PUNE)
    a, b = tl.time[5], tl.time[100]
    assert tl.between("rain_m3", a, b) == pytest.approx(tl.columns["rain_m3"][6:101].sum())
    assert tl.between("rain_m3", b, a) == pytest.approx(tl.between("rain_m3", a, b))


def test_azimuth_is_unwrapped():
    w = synthetic.generate(T0, 24 * 3, *PUNE)
    tl = simulate(w, *PUNE)
    assert np.abs(np.diff(tl.columns["sun_azimuth_deg"])).max() < 180


def test_deterministic():
    w = synthetic.generate(T0, 24 * 20, *PUNE, seed=5)
    a = simulate(w, *PUNE)
    b = simulate(w, *PUNE)
    for name in a.columns:
        assert np.array_equal(a.columns[name], b.columns[name])


@pytest.mark.parametrize("seed", range(8))
def test_invariants_under_random_weather(seed):
    rng = np.random.default_rng(seed)
    w = synthetic.generate(T0 + seed * 86400 * 37, 24 * int(rng.integers(5, 60)), *PUNE, seed=seed,
                           rain_events_per_week=float(rng.uniform(0, 8)), mean_temp_c=float(rng.uniform(5, 40)))
    pond = PondParams(initial_depth_m=float(rng.uniform(0, 1.5)), catchment_area_m2=float(rng.uniform(0, 5000)))
    tl = simulate(w, *PUNE, pond=pond)
    c = tl.columns
    assert abs(tl.summary["mass_balance_error_m3"]) < 1e-6
    assert np.all(c["volume_m3"] >= 0) and np.all(c["volume_m3"] <= tl.summary["volume_full_m3"] + 1e-9)
    assert np.all((c["cover_fraction"] >= 0) & (c["cover_fraction"] <= 1))
    assert np.all(np.isfinite(np.column_stack(list(c.values()))))


def test_runoff_bucket_wet_soil_runs_off_more():
    p = PondParams()
    dry, _ = runoff_mm(10.0, 0.0, p)
    wet, _ = runoff_mm(10.0, p.soil_capacity_mm, p)
    assert dry < wet <= 10.0
    total, soil = runoff_mm(10.0, 5.0, p)
    assert total + (soil - 5.0) == pytest.approx(10.0)  # rain is conserved


def test_response_functions():
    p = LotusParams()
    f = temperature_factor(np.array([p.t_min_c, p.t_opt_c, p.t_max_c, 50.0]), p)
    assert f.tolist() == pytest.approx([0.0, 1.0, 0.0, 0.0])
    assert depth_factor(0.0, p) == 0.0 and depth_factor(1.0, p) == 1.0
    # exact logistic: large K behaves exponentially, never exceeds K
    assert logistic_step(1.0, math.log(2), 1e12, 1.0) == pytest.approx(2.0)
    assert logistic_step(50.0, 10.0, 100.0, 10.0) <= 100.0


def test_invalid_params_rejected():
    w = make_weather()
    with pytest.raises(ValueError):
        simulate(w, *PUNE, pond=PondParams(initial_depth_m=3.0))
    with pytest.raises(ValueError):
        simulate(w, *PUNE, lotus=LotusParams(t_min_c=35.0))
    with pytest.raises(ValueError):
        simulate(w, *PUNE, pond=PondParams(surface_area_m2=float("nan")))
