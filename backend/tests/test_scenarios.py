import numpy as np

from conftest import PUNE, T0
from lotuslab.core import synthetic
from lotuslab.core.engine import simulate
from lotuslab.core.scenarios import PRESETS, Scenario, apply


def test_identity_returns_same_object():
    w = synthetic.generate(T0, 48, *PUNE)
    assert apply(w, Scenario()) is w


def test_more_cloud_means_less_sun():
    w = synthetic.generate(T0, 72, *PUNE)
    o = apply(w, Scenario(cloud_cover_offset_pct=60))
    assert o.shortwave_wm2.sum() < w.shortwave_wm2.sum()
    assert np.all(o.cloud_cover_pct <= 100)


def test_presets_move_the_pond_in_expected_directions():
    w = synthetic.generate(T0, 24 * 30, *PUNE, seed=2, rain_events_per_week=3)
    base = simulate(w, *PUNE).summary
    wet = simulate(apply(w, PRESETS["monsoon_surge"][1]), *PUNE).summary
    dry = simulate(apply(w, PRESETS["drought"][1]), *PUNE).summary
    assert wet["final_depth_m"] >= base["final_depth_m"] >= dry["final_depth_m"]
    assert wet["totals_m3"]["overflow_m3"] >= base["totals_m3"]["overflow_m3"]
