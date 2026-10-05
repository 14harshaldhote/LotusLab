import numpy as np
import pytest

from lotuslab.core.weather import WeatherError, normalise

T = 1751328000.0 + 3600.0 * np.arange(5)


def test_interpolates_gaps_and_reports_them():
    w = normalise(T, {"temperature_c": [10, None, float("nan"), 16, 18], "shortwave_wm2": [0] * 5})
    assert w.temperature_c.tolist() == [10, 12, 14, 16, 18]
    assert w.gaps_filled["temperature_c"] == 2
    assert w.gaps_filled["et0_mm"] == 5  # derived because missing


def test_clips_to_physical_bounds():
    w = normalise(T, {"temperature_c": [20] * 5, "shortwave_wm2": [0] * 5, "precipitation_mm": [-1, 0, 1, 2, 999]})
    assert w.precipitation_mm.min() == 0 and w.precipitation_mm.max() == 300


def test_rejects_irregular_grid():
    with pytest.raises(WeatherError):
        normalise([0, 3600, 7300], {"temperature_c": [1, 2, 3], "shortwave_wm2": [0, 0, 0]})


def test_requires_temperature():
    with pytest.raises(WeatherError):
        normalise(T, {"shortwave_wm2": [0] * 5})
