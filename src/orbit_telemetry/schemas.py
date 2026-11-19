"""Response models. FastAPI uses them for validation and the OpenAPI docs at /docs.

Every field the page shows comes from one of these models: no invented readouts.
"""

from datetime import datetime

from pydantic import BaseModel

from orbit_telemetry.subsystems import PowerBands


class Position(BaseModel):
    latitude_deg: float
    longitude_deg: float
    altitude_km: float
    speed_km_s: float
    frame: str = "WGS-84 geodetic"


class Power(BaseModel):
    sunlit: bool
    battery_voltage_v: float
    state_of_charge_pct: float
    solar_array_current_a: float
    bands: PowerBands


class Thermal(BaseModel):
    core_temperature_c: float
    target_temperature_c: float


class Telemetry(BaseModel):
    norad_id: int
    name: str
    intl_designator: str
    orbit_class: str
    inclination_deg: float
    period_minutes: float
    beta_angle_deg: float
    coverage_half_angle_deg: float
    elements_epoch: datetime
    data_fetched_at: datetime
    data_age_seconds: float
    data_stale: bool
    position: Position
    power: Power
    thermal: Thermal
    simulated_fields: list[str] = ["power", "thermal"]
    updated_at: datetime


class SatelliteSummary(BaseModel):
    norad_id: int
    name: str
    orbit_class: str
    inclination_deg: float
    altitude_km: float
    sunlit: bool


class TrackPoint(BaseModel):
    time: datetime
    latitude_deg: float
    longitude_deg: float


class Track(BaseModel):
    norad_id: int
    orbits: int
    step_seconds: int
    points: list[TrackPoint]


class Sun(BaseModel):
    time: datetime
    subsolar_latitude_deg: float
    subsolar_longitude_deg: float


class Info(BaseModel):
    version: str
    environment: str
    propagator: str = "SGP4"
    data_source: str = "Real orbits from CelesTrak, simulated subsystems"
    satellites_tracked: int
    satellites_ready: int
    orbital_data_ok: bool
    refresh_interval_seconds: int
    tick_seconds: float
