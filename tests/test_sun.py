"""Sun geometry checked against known astronomical facts."""

from datetime import UTC, datetime

import numpy as np
import pytest

from orbit_telemetry.sun import (
    EARTH_RADIUS_KM,
    beta_angle_deg,
    in_eclipse,
    julian_date,
    subsolar_point,
    sun_unit_vector,
)


def test_julian_date_of_j2000_epoch():
    assert julian_date(datetime(2000, 1, 1, 12, tzinfo=UTC)) == pytest.approx(2451545.0)


@pytest.mark.parametrize(
    ("when", "expected_declination"),
    [
        (datetime(2026, 6, 21, 12, tzinfo=UTC), 23.44),  # June solstice
        (datetime(2026, 12, 21, 12, tzinfo=UTC), -23.44),  # December solstice
        (datetime(2026, 3, 20, 15, tzinfo=UTC), 0.0),  # March equinox
    ],
)
def test_subsolar_latitude_matches_seasons(when, expected_declination):
    latitude, _ = subsolar_point(when)
    assert latitude == pytest.approx(expected_declination, abs=0.1)


def test_subsolar_longitude_is_near_greenwich_at_noon_utc():
    # Off by at most the equation of time (about 4 degrees).
    _, longitude = subsolar_point(datetime(2026, 4, 15, 12, tzinfo=UTC))
    assert abs(longitude) < 5


def test_sun_vector_is_unit_length():
    assert np.linalg.norm(sun_unit_vector(datetime(2026, 11, 19, tzinfo=UTC))) == pytest.approx(1)


SUN = np.array([1.0, 0.0, 0.0])
LEO = EARTH_RADIUS_KM + 420


def test_satellite_on_day_side_is_lit():
    assert not in_eclipse(np.array([LEO, 0, 0]), SUN)


def test_satellite_directly_behind_earth_is_in_shadow():
    assert in_eclipse(np.array([-LEO, 0, 0]), SUN)


def test_night_side_but_outside_shadow_cylinder_is_lit():
    assert not in_eclipse(np.array([-1000.0, 0, LEO]), SUN)


def test_beta_angle_extremes():
    position, velocity = np.array([LEO, 0, 0]), np.array([0, 7.66, 0])  # orbit normal is +z
    assert beta_angle_deg(position, velocity, np.array([1.0, 0, 0])) == pytest.approx(0)
    assert beta_angle_deg(position, velocity, np.array([0, 0, 1.0])) == pytest.approx(90)
