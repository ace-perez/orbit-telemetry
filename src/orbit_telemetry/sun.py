"""Sun geometry: where the Sun is, and whether a satellite is in Earth's shadow.

Uses the low-precision solar position from the Astronomical Almanac (accurate to about
0.01 degrees between 1950 and 2050). That is far better than this app needs and avoids
downloading a 17 MB JPL ephemeris file at runtime or in tests.
"""

import math
from datetime import UTC, datetime

import numpy as np

EARTH_RADIUS_KM = 6371.0
_J2000_JD = 2451545.0
_UNIX_EPOCH_JD = 2440587.5


def julian_date(when: datetime) -> float:
    """Julian Date (days since noon, 1 Jan 4713 BC) for a timezone-aware datetime."""
    return when.astimezone(UTC).timestamp() / 86400.0 + _UNIX_EPOCH_JD


def _ecliptic_longitude_and_obliquity(when: datetime) -> tuple[float, float]:
    """Sun's ecliptic longitude and Earth's axial tilt, both in radians."""
    n = julian_date(when) - _J2000_JD  # days since J2000.0
    mean_longitude = math.radians((280.460 + 0.9856474 * n) % 360)
    mean_anomaly = math.radians((357.528 + 0.9856003 * n) % 360)
    ecliptic_longitude = (
        mean_longitude
        + math.radians(1.915) * math.sin(mean_anomaly)
        + math.radians(0.020) * math.sin(2 * mean_anomaly)
    )
    obliquity = math.radians(23.439 - 0.0000004 * n)
    return ecliptic_longitude, obliquity


def sun_unit_vector(when: datetime) -> np.ndarray:
    """Unit vector from Earth's centre towards the Sun, in equatorial (inertial) axes."""
    lam, eps = _ecliptic_longitude_and_obliquity(when)
    return np.array([math.cos(lam), math.cos(eps) * math.sin(lam), math.sin(eps) * math.sin(lam)])


def greenwich_sidereal_angle_deg(when: datetime) -> float:
    """Greenwich Mean Sidereal Time as an angle: how far Earth has rotated, in degrees."""
    n = julian_date(when) - _J2000_JD
    return (280.46061837 + 360.98564736629 * n) % 360


def subsolar_point(when: datetime) -> tuple[float, float]:
    """Latitude and longitude (degrees) where the Sun is directly overhead.

    The solar terminator (day/night line) is the circle 90 degrees from this point.
    """
    x, y, z = sun_unit_vector(when)
    declination = math.degrees(math.asin(z))
    right_ascension = math.degrees(math.atan2(y, x))
    longitude = (right_ascension - greenwich_sidereal_angle_deg(when) + 540) % 360 - 180
    return declination, longitude


def in_eclipse(position_km: np.ndarray, sun_direction: np.ndarray) -> bool:
    """True if the satellite is inside Earth's shadow (cylindrical shadow model).

    The satellite is in shadow when it is on the night side (behind Earth relative to the
    Sun) AND closer to the Earth-Sun line than Earth's radius. Ignoring the penumbra is
    accurate to a few seconds of eclipse entry/exit time in low Earth orbit.
    """
    along_sun_axis = float(np.dot(position_km, sun_direction))
    if along_sun_axis >= 0:
        return False  # on the day side
    distance_from_axis = float(np.linalg.norm(position_km - along_sun_axis * sun_direction))
    return distance_from_axis < EARTH_RADIUS_KM


def beta_angle_deg(
    position_km: np.ndarray, velocity_km_s: np.ndarray, sun_direction: np.ndarray
) -> float:
    """Angle between the orbital plane and the Sun direction, in degrees.

    Near 0: the orbit passes through Earth's shadow every revolution (longest eclipses).
    Near +/-90: the orbit faces the Sun edge-on and can stay in sunlight continuously.
    """
    orbit_normal = np.cross(position_km, velocity_km_s)
    orbit_normal = orbit_normal / np.linalg.norm(orbit_normal)
    return math.degrees(math.asin(float(np.clip(np.dot(orbit_normal, sun_direction), -1, 1))))
