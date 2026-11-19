"""Orbit propagation sanity checks with fixture elements (no network)."""

from datetime import timedelta

import pytest

from orbit_telemetry.orbit import Propagator, coverage_half_angle_deg, orbit_class, parse_omm
from tests.conftest import EPOCH, ISS


@pytest.fixture
def iss(omm_records):
    return parse_omm(omm_records[ISS])


def test_parse_omm_reads_identity_and_elements(iss):
    assert iss.norad_id == ISS
    assert iss.name == "ISS (ZARYA)"
    assert iss.intl_designator == "1998-067A"
    assert iss.epoch == EPOCH
    assert iss.inclination_deg == pytest.approx(51.64)


def test_parse_omm_rejects_incomplete_record():
    with pytest.raises(KeyError):
        parse_omm({"OBJECT_NAME": "broken"})


def test_iss_period_is_about_93_minutes(iss):
    assert iss.period_minutes == pytest.approx(92.9, abs=0.2)


def test_iss_state_is_physically_plausible(iss):
    state = Propagator().state(iss, EPOCH + timedelta(minutes=10))
    assert 380 < state.altitude_km < 460
    assert state.speed_km_s == pytest.approx(7.66, abs=0.05)
    assert abs(state.latitude_deg) <= iss.inclination_deg + 0.5  # cannot exceed inclination
    assert -180 <= state.longitude_deg <= 180


def test_ground_track_covers_requested_orbits(iss):
    track = Propagator().ground_track(iss, EPOCH, orbits=2, step_seconds=60)
    expected_points = int(iss.period_minutes * 2) + 1
    assert abs(len(track) - expected_points) <= 1
    assert track[0].time == EPOCH
    assert max(abs(p.latitude_deg) for p in track) == pytest.approx(51.64, abs=1.0)


def test_coverage_half_angle_at_iss_altitude():
    assert coverage_half_angle_deg(418) == pytest.approx(20.2, abs=0.1)


@pytest.mark.parametrize(
    ("inclination", "altitude", "expected"),
    [(51.6, 420, "LEO"), (98.6, 786, "SSO"), (85.0, 800, "PO"), (98.6, 20000, "PO")],
)
def test_orbit_class(inclination, altitude, expected):
    assert orbit_class(inclination, altitude) == expected
