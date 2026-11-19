"""Orbital mechanics: turn CelesTrak orbital elements into positions over time.

CelesTrak publishes General Perturbations (GP) elements in the OMM format. The SGP4
propagator (via Skyfield) predicts where the satellite is at any moment from them.
"""

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import numpy as np
from skyfield.api import EarthSatellite, load, wgs84

from orbit_telemetry.sun import EARTH_RADIUS_KM


@dataclass(frozen=True)
class OrbitalElements:
    norad_id: int
    name: str
    intl_designator: str  # COSPAR ID, e.g. 1998-067A
    epoch: datetime  # moment the elements describe; accuracy degrades as it ages
    inclination_deg: float
    mean_motion_rev_per_day: float
    omm: dict = field(repr=False, compare=False)  # raw record, passed to SGP4

    @property
    def period_minutes(self) -> float:
        return 1440.0 / self.mean_motion_rev_per_day


@dataclass(frozen=True)
class SatelliteState:
    latitude_deg: float
    longitude_deg: float
    altitude_km: float
    speed_km_s: float
    position_km: np.ndarray  # inertial frame, for shadow and beta-angle geometry
    velocity_km_s: np.ndarray


@dataclass(frozen=True)
class TrackPoint:
    time: datetime
    latitude_deg: float
    longitude_deg: float


def parse_omm(omm: dict) -> OrbitalElements:
    """Validate and normalise one OMM record from CelesTrak's JSON format."""
    epoch = datetime.fromisoformat(str(omm["EPOCH"]))
    if epoch.tzinfo is None:
        epoch = epoch.replace(tzinfo=UTC)  # OMM epochs are UTC
    return OrbitalElements(
        norad_id=int(omm["NORAD_CAT_ID"]),
        name=str(omm["OBJECT_NAME"]),
        intl_designator=str(omm.get("OBJECT_ID", "")),
        epoch=epoch,
        inclination_deg=float(omm["INCLINATION"]),
        mean_motion_rev_per_day=float(omm["MEAN_MOTION"]),
        omm=omm,
    )


def coverage_half_angle_deg(altitude_km: float) -> float:
    """Earth-centred half-angle of the area that can see the satellite above the horizon."""
    return math.degrees(math.acos(EARTH_RADIUS_KM / (EARTH_RADIUS_KM + altitude_km)))


def orbit_class(inclination_deg: float, altitude_km: float) -> str:
    """Coarse label for the satellite list: SSO, polar (PO) or low Earth orbit (LEO)."""
    if 96.0 <= inclination_deg <= 100.0 and altitude_km < 1500:
        return "SSO"  # sun-synchronous: plane keeps a fixed angle to the Sun
    if 80.0 <= inclination_deg <= 100.0:
        return "PO"
    return "LEO"


class Propagator:
    """Wraps Skyfield's SGP4. Satellites are cached per element set to avoid rebuilding."""

    def __init__(self) -> None:
        # builtin=True uses data shipped with Skyfield: no network access.
        self._ts = load.timescale(builtin=True)
        self._cache: dict[tuple[int, datetime], EarthSatellite] = {}

    def _satellite(self, elements: OrbitalElements) -> EarthSatellite:
        key = (elements.norad_id, elements.epoch)
        if key not in self._cache:
            self._cache[key] = EarthSatellite.from_omm(self._ts, elements.omm)
        return self._cache[key]

    def state(self, elements: OrbitalElements, when: datetime) -> SatelliteState:
        position = self._satellite(elements).at(self._ts.from_datetime(when))
        latitude, longitude = wgs84.latlon_of(position)
        return SatelliteState(
            latitude_deg=float(latitude.degrees),
            longitude_deg=float(longitude.degrees),
            altitude_km=float(wgs84.height_of(position).km),
            speed_km_s=float(np.linalg.norm(position.velocity.km_per_s)),
            position_km=np.asarray(position.position.km, dtype=float),
            velocity_km_s=np.asarray(position.velocity.km_per_s, dtype=float),
        )

    def ground_track(
        self, elements: OrbitalElements, start: datetime, orbits: int, step_seconds: int
    ) -> list[TrackPoint]:
        """Sub-satellite points from `start` for the next `orbits` revolutions."""
        duration = elements.period_minutes * 60 * orbits
        offsets = np.arange(0, duration + step_seconds, step_seconds)
        times = [start + timedelta(seconds=float(s)) for s in offsets]
        # Propagate all times in one vectorised call instead of a Python loop.
        positions = self._satellite(elements).at(self._ts.from_datetimes(times))
        latitudes, longitudes = wgs84.latlon_of(positions)
        return [
            TrackPoint(time=t, latitude_deg=float(lat), longitude_deg=float(lon))
            for t, lat, lon in zip(times, latitudes.degrees, longitudes.degrees, strict=True)
        ]
