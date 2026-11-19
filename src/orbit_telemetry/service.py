"""The telemetry service: keeps orbital data fresh and recomputes every satellite's state.

`update()` is the unit of work: refresh elements that are due, then compute positions and
step the simulated subsystems. A background loop calls it every `tick_seconds`; tests
call it directly with a fixed clock and a fake data source.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from orbit_telemetry.celestrak import CelesTrakError, ElementsSource
from orbit_telemetry.config import Settings
from orbit_telemetry.metrics import Metrics
from orbit_telemetry.orbit import (
    OrbitalElements,
    Propagator,
    coverage_half_angle_deg,
    orbit_class,
    parse_omm,
)
from orbit_telemetry.schemas import Position, Power, Telemetry, Thermal
from orbit_telemetry.subsystems import PowerBands, SubsystemSimulator
from orbit_telemetry.sun import beta_angle_deg, in_eclipse, sun_unit_vector

log = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


class TelemetryService:
    def __init__(
        self,
        settings: Settings,
        source: ElementsSource,
        metrics: Metrics,
        propagator: Propagator | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.settings = settings
        self.source = source
        self.metrics = metrics
        self.propagator = propagator or Propagator()
        self.clock = clock
        self.bands = PowerBands()

        self.elements: dict[int, OrbitalElements] = {}
        self.fetched_at: dict[int, datetime] = {}
        self.snapshots: dict[int, Telemetry] = {}
        self._simulators = {nid: SubsystemSimulator() for nid in settings.norad_ids}
        self._last_tick: datetime | None = None

    # -- readiness ---------------------------------------------------------------

    @property
    def ready_count(self) -> int:
        return len(self.snapshots)

    @property
    def ready(self) -> bool:
        """Ready to serve when every configured satellite has a computed snapshot."""
        return self.ready_count == len(self.settings.norad_ids)

    def orbital_data_ok(self, now: datetime) -> bool:
        return self.ready and all(
            (now - fetched).total_seconds() < self.settings.stale_after_seconds
            for fetched in self.fetched_at.values()
        )

    # -- work ----------------------------------------------------------------------

    async def refresh_elements(self, now: datetime) -> None:
        """Fetch elements that are missing or older than the refresh interval."""
        for norad_id in self.settings.norad_ids:
            last = self.fetched_at.get(norad_id)
            if last and (now - last).total_seconds() < self.settings.orbit_refresh_seconds:
                continue
            try:
                elements = parse_omm(await self.source.fetch(norad_id))
            except (CelesTrakError, KeyError, ValueError) as exc:
                # Keep serving the previous elements; staleness is visible in metrics.
                self.metrics.fetch_failures.labels(norad_id=str(norad_id)).inc()
                log.warning(
                    "orbital data fetch failed", extra={"norad_id": norad_id, "error": str(exc)}
                )
                continue
            self.elements[norad_id] = elements
            self.fetched_at[norad_id] = now
            log.info(
                "orbital data refreshed",
                extra={"norad_id": norad_id, "epoch": elements.epoch.isoformat()},
            )

    def tick(self, now: datetime) -> None:
        """Recompute position and step simulated subsystems for every satellite."""
        dt = (now - self._last_tick).total_seconds() if self._last_tick else 0.0
        self._last_tick = now
        sun = sun_unit_vector(now)

        for norad_id, elements in self.elements.items():
            state = self.propagator.state(elements, now)
            sunlit = not in_eclipse(state.position_km, sun)
            beta = beta_angle_deg(state.position_km, state.velocity_km_s, sun)
            reading = self._simulators[norad_id].step(dt, sunlit)
            age = (now - self.fetched_at[norad_id]).total_seconds()

            snapshot = Telemetry(
                norad_id=norad_id,
                name=elements.name,
                intl_designator=elements.intl_designator,
                orbit_class=orbit_class(elements.inclination_deg, state.altitude_km),
                inclination_deg=round(elements.inclination_deg, 2),
                period_minutes=round(elements.period_minutes, 2),
                beta_angle_deg=round(beta, 1),
                coverage_half_angle_deg=round(coverage_half_angle_deg(state.altitude_km), 2),
                elements_epoch=elements.epoch,
                data_fetched_at=self.fetched_at[norad_id],
                data_age_seconds=round(age, 1),
                data_stale=age >= self.settings.stale_after_seconds,
                position=Position(
                    latitude_deg=round(state.latitude_deg, 4),
                    longitude_deg=round(state.longitude_deg, 4),
                    altitude_km=round(state.altitude_km, 1),
                    speed_km_s=round(state.speed_km_s, 3),
                ),
                power=Power(
                    sunlit=sunlit,
                    battery_voltage_v=reading.battery_voltage_v,
                    state_of_charge_pct=reading.state_of_charge_pct,
                    solar_array_current_a=reading.solar_array_current_a,
                    bands=self.bands,
                ),
                thermal=Thermal(
                    core_temperature_c=reading.core_temperature_c,
                    target_temperature_c=reading.target_temperature_c,
                ),
                updated_at=now,
            )
            self.snapshots[norad_id] = snapshot
            self._export_metrics(snapshot, age)

    def _export_metrics(self, s: Telemetry, age: float) -> None:
        labels = {"norad_id": str(s.norad_id), "name": s.name}
        m = self.metrics
        m.altitude.labels(**labels).set(s.position.altitude_km)
        m.sunlit.labels(**labels).set(1 if s.power.sunlit else 0)
        m.battery_voltage.labels(**labels).set(s.power.battery_voltage_v)
        m.state_of_charge.labels(**labels).set(s.power.state_of_charge_pct)
        m.solar_current.labels(**labels).set(s.power.solar_array_current_a)
        m.temperature.labels(**labels).set(s.thermal.core_temperature_c)
        m.orbital_data_age.labels(**labels).set(age)

    async def update(self) -> None:
        now = self.clock()
        await self.refresh_elements(now)
        self.tick(now)

    async def run_forever(self) -> None:
        """Background loop. One failed iteration is logged and never stops the loop."""
        while True:
            try:
                await self.update()
            except Exception:
                log.exception("telemetry update failed")
            await asyncio.sleep(self.settings.tick_seconds)
