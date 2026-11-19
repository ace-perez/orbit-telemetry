"""Runtime configuration, read from environment variables.

Every setting has a safe default so the app runs with no configuration, and every
setting can be overridden per environment (Compose, Helm values) without code changes.
This is the "config in the environment" factor of the Twelve-Factor App.
"""

from pydantic import Field
from pydantic_settings import BaseSettings

from orbit_telemetry import __version__


class Settings(BaseSettings):
    # Shown in /api/v1/info and the page header. CI overrides it with the git tag.
    app_version: str = __version__
    environment: str = "local"

    # Where orbital elements come from. Integration tests point this at a stub server.
    celestrak_base_url: str = "https://celestrak.org"

    # Comma-separated NORAD catalogue numbers: ISS, HST, Sentinel-2A, NOAA 19, Landsat 9.
    satellites: str = "25544,20580,40697,33591,49260"

    # CelesTrak updates data about every 2 hours and blocks clients that poll faster.
    # The minimum of 10 minutes stops a misconfiguration from hammering it.
    orbit_refresh_seconds: int = Field(default=7200, ge=600)

    # How often positions and simulated subsystems are recomputed.
    tick_seconds: float = Field(default=5.0, gt=0)

    # Orbital data older than this is reported as stale (and alerted on in Phase 7).
    stale_after_seconds: int = Field(default=21600, gt=0)

    # Failure injection for the rollback demo: fraction of /api requests that return 500.
    failure_rate: float = Field(default=0.0, ge=0.0, le=1.0)

    log_level: str = "INFO"
    host: str = "0.0.0.0"  # inside a container the app must listen on all interfaces
    port: int = 8000

    @property
    def norad_ids(self) -> list[int]:
        return [int(part) for part in self.satellites.split(",") if part.strip()]
