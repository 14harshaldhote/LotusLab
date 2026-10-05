import datetime as dt

import numpy as np

from lotuslab.core.solar import PHASE_DAY, PHASE_GOLDEN, PHASE_NIGHT, PHASE_TWILIGHT, day_phase, solar_position


def unix(*args):
    return dt.datetime(*args, tzinfo=dt.timezone.utc).timestamp()


def test_equinox_noon_at_equator_is_near_zenith():
    # solar noon at lon 0 on the March equinox is ~12:07 UTC
    pos = solar_position(np.array([unix(2025, 3, 20, 12, 7)]), 0.0, 0.0)
    assert pos.elevation_deg[0] > 88.0


def test_pune_june_noon_elevation_matches_geometry():
    # Pune (18.52N, 73.86E) solar noon ~ 06:58 UTC on 21 June; max elev = 90 - |lat - decl|
    t = unix(2025, 6, 21, 6, 0) + np.arange(0, 7200, 60)
    elev = solar_position(t, 18.52, 73.86).elevation_deg
    assert abs(elev.max() - (90 - abs(18.52 - 23.44))) < 0.5


def test_midnight_is_dark_and_azimuth_east_in_morning():
    pos = solar_position(np.array([unix(2025, 6, 21, 18, 30), unix(2025, 6, 21, 2, 0)]), 18.52, 73.86)
    assert pos.elevation_deg[0] < -30  # local midnight
    assert 45 < pos.azimuth_deg[1] < 110  # 07:30 local: sun in the east


def test_sunrise_against_reference():
    # NOAA calculator: Pune sunrise 21 June 2025 ~ 06:00 IST = 00:30 UTC
    t = unix(2025, 6, 21, 0, 0) + np.arange(0, 3600, 60)
    elev = solar_position(t, 18.52, 73.86).elevation_deg
    crossing = t[np.argmax(elev > -0.833)]
    expected = unix(2025, 6, 21, 0, 30)
    assert abs(crossing - expected) < 5 * 60


def test_day_phase_codes():
    phases = day_phase(np.array([-20.0, -3.0, 3.0, 40.0]))
    assert phases.tolist() == [PHASE_NIGHT, PHASE_TWILIGHT, PHASE_GOLDEN, PHASE_DAY]
