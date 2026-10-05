import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lotuslab.core.weather import normalise  # noqa: E402

PUNE = (18.52, 73.86)
T0 = 1751328000.0  # 2025-07-01T00:00:00Z


def make_weather(hours=48, rain=0.0, temp=28.0, sw=None, et0=0.0, cloud=30.0, start=T0):
    t = start + 3600.0 * np.arange(hours)
    def full(v):
        return np.broadcast_to(np.asarray(v, dtype=float), (hours,)).copy()
    if sw is None:
        sw = np.clip(800 * np.sin(np.pi * ((np.arange(hours) % 24) - 6) / 12), 0, None)
    return normalise(
        t,
        {
            "temperature_c": full(temp),
            "precipitation_mm": full(rain),
            "cloud_cover_pct": full(cloud),
            "wind_speed_ms": full(2.0),
            "relative_humidity_pct": full(60.0),
            "shortwave_wm2": full(sw),
            "et0_mm": full(et0),
        },
    )


@pytest.fixture
def weather_factory():
    return make_weather
