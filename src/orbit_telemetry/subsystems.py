"""Simulated spacecraft subsystems: electrical power (EPS) and thermal (TCS).

These values are SIMULATED, driven by the real orbit: the battery charges while the
satellite is in sunlight and drains in Earth's shadow, and the temperature drifts towards
a warmer or colder equilibrium. The model is deliberately simple and deterministic, so
it is easy to test and the Grafana sawtooth matches each satellite's real orbital period.
"""

import math
from dataclasses import dataclass

from pydantic import BaseModel


class PowerBands(BaseModel):
    """Voltage thresholds, exposed by the API so the page's band bar is data-driven."""

    critical_v: float = 24.0
    nominal_min_v: float = 26.0
    nominal_max_v: float = 29.0
    overvoltage_v: float = 32.0


@dataclass(frozen=True)
class SubsystemConfig:
    charge_pct_per_s: float = 0.0075  # about +25% over a 56-minute daylight pass
    discharge_pct_per_s: float = 0.012  # about -26% over a 36-minute eclipse
    soc_min_pct: float = 20.0  # flight software would shed load before this
    soc_max_pct: float = 100.0
    bus_v_at_empty: float = 26.0
    bus_v_per_pct: float = 0.026  # 75% charge -> 27.95 V on a nominal 28 V bus
    solar_array_current_a: float = 3.24
    temp_sunlit_c: float = 22.0
    temp_eclipse_c: float = 8.0
    temp_target_c: float = 18.0
    thermal_time_constant_s: float = 900.0
    max_step_s: float = 300.0  # cap a long pause so values cannot jump unrealistically


@dataclass(frozen=True)
class SubsystemReading:
    battery_voltage_v: float
    state_of_charge_pct: float
    solar_array_current_a: float
    core_temperature_c: float
    target_temperature_c: float


class SubsystemSimulator:
    def __init__(
        self,
        config: SubsystemConfig | None = None,
        state_of_charge_pct: float = 75.0,
        temperature_c: float = 18.0,
    ) -> None:
        self.config = config or SubsystemConfig()
        self._soc = state_of_charge_pct
        self._temp = temperature_c
        self._sunlit = True

    def step(self, dt_seconds: float, sunlit: bool) -> SubsystemReading:
        """Advance the simulation by dt_seconds with the given illumination."""
        cfg = self.config
        dt = min(max(dt_seconds, 0.0), cfg.max_step_s)
        rate = cfg.charge_pct_per_s if sunlit else -cfg.discharge_pct_per_s
        self._soc = min(cfg.soc_max_pct, max(cfg.soc_min_pct, self._soc + rate * dt))

        # First-order thermal lag: move a fraction of the way towards equilibrium.
        equilibrium = cfg.temp_sunlit_c if sunlit else cfg.temp_eclipse_c
        self._temp += (equilibrium - self._temp) * (1 - math.exp(-dt / cfg.thermal_time_constant_s))
        self._sunlit = sunlit
        return self.reading()

    def reading(self) -> SubsystemReading:
        cfg = self.config
        return SubsystemReading(
            battery_voltage_v=round(cfg.bus_v_at_empty + cfg.bus_v_per_pct * self._soc, 2),
            state_of_charge_pct=round(self._soc, 1),
            solar_array_current_a=cfg.solar_array_current_a if self._sunlit else 0.0,
            core_temperature_c=round(self._temp, 1),
            target_temperature_c=cfg.temp_target_c,
        )
